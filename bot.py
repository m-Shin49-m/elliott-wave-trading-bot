# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Tuple
import csv
from pathlib import Path
from collections import Counter

# Cross-platform file locking
try:
    import msvcrt  # Windows
    _USE_MSVCRT = True
except ImportError:
    import fcntl  # Linux/Unix
    _USE_MSVCRT = False

# Prefer python-telegram-bot 13.15, but provide a minimal fallback for Python 3.13+
try:
    from telegram import Bot, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
    _HAS_TELEGRAM_LIB = True
except Exception:
    # Minimal fallback using direct Telegram HTTP API via requests
    class ParseMode:  # type: ignore
        HTML = "HTML"
    
    class InlineKeyboardButton:  # type: ignore
        def __init__(self, text: str, callback_data: str):
            self.text = text
            self.callback_data = callback_data
    
    class InlineKeyboardMarkup:  # type: ignore
        def __init__(self, keyboard):
            self.keyboard = keyboard
    
    _HAS_TELEGRAM_LIB = False

    class Bot:  # type: ignore
        def __init__(self, token: str):
            self._token = token

        def send_message(self, chat_id: str, text: str, parse_mode: Optional[str] = None, 
                        disable_web_page_preview: bool = True, reply_markup: Optional[Dict] = None):
            import requests
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode or "HTML",
                "disable_web_page_preview": disable_web_page_preview,
            }
            if reply_markup:
                data["reply_markup"] = reply_markup
            # Send JSON to ensure UTF-8 correctness in Telegram
            resp = requests.post(url, json=data, timeout=20)
            resp.raise_for_status()
            return resp.json()

try:
    import elliott_wave_bot.config as config
    from elliott_wave_bot.elliott_wave import ElliottWaveAnalyzer
    from elliott_wave_bot.liquidity_zones import LiquidityZones
    from elliott_wave_bot.prob_model import load_model as _load_prob_model, estimate as _estimate_prob
    from elliott_wave_bot.news import build_snapshot as _build_news_snapshot
except Exception:
    import config  # type: ignore
    from elliott_wave import ElliottWaveAnalyzer  # type: ignore
    from liquidity_zones import LiquidityZones  # type: ignore
    from prob_model import load_model as _load_prob_model, estimate as _estimate_prob  # type: ignore
    from news import build_snapshot as _build_news_snapshot  # type: ignore


# ------------- Logging -------------
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("elliott_bot")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File
    base_dir = os.path.dirname(__file__)
    fh = logging.FileHandler(os.path.join(base_dir, "elliott_bot.log"), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


# ------------- Bot helpers -------------
_LOCK_FH = None
def acquire_single_instance(lock_name: str = "elliott_bot.lock") -> bool:
    """
    Prevent multiple concurrent instances via file lock (cross-platform).
    """
    global _LOCK_FH
    try:
        lock_path = os.path.join(os.path.dirname(__file__), lock_name)
        _LOCK_FH = open(lock_path, "w")
        if _USE_MSVCRT:
            # Windows: lock 1 byte non-blocking
            msvcrt.locking(_LOCK_FH.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            # Linux/Unix: non-blocking exclusive lock
            fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (IOError, OSError, BlockingIOError):
        return False
    except Exception:
        return False

def timeframe_sleep_seconds(tf: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(tf, 3600)

def multi_timeframes_sleep_seconds(tfs) -> int:
    # Prefer fast polling override if configured
    fast = int(getattr(config, "FAST_POLL_SECONDS", 0) or 0)
    if fast > 0:
        return fast
    seconds = [timeframe_sleep_seconds(tf) for tf in tfs]
    return min(seconds) if seconds else 3600


def format_signal_message(pair: str, timeframe: str, signal: Dict) -> str:
    direction = signal["direction"]
    emoji = "🟢" if direction == "BUY" else "🔴"
    arrow = "🟩 BUY" if direction == "BUY" else "🟥 SELL"
    wave_points = signal.get("wave_points", [])
    category = signal.get("category")
    context = signal.get("context", {})
    lz_ctx = signal.get("lz_context", {})

    def fmt_price(x: float) -> str:
        # Adapt decimals
        return f"{x:.6f}".rstrip("0").rstrip(".")

    # Basic pivot info (indices not interesting to user, show prices)
    pivots_lines = []
    for idx, wp in enumerate(wave_points):
        pivots_lines.append(f"  {idx}: {wp['type']} @ {fmt_price(wp['price'])}")
    pivots_block = "\n".join(pivots_lines)

    msg = (
        f"{emoji} <b>Elliott Wave Signal</b>\n"
        f"• Пара: <b>{pair}</b>\n"
        f"• Таймфрейм: <b>{timeframe}</b>\n"
        f"• Направление: <b>{arrow}</b>\n"
        f"• Качество паттерна: <b>{signal['quality']}%</b>{('  Категория: <b>'+category+'</b>') if category else ''}\n"
        f"• Цена входа: <b>{fmt_price(signal['entry'])}</b>\n"
        f"• TP1: <b>{fmt_price(signal['tp1'])}</b>\n"
        f"• TP2: <b>{fmt_price(signal['tp2'])}</b>\n"
        f"• TP3: <b>{fmt_price(signal['tp3'])}</b>\n"
        f"• Stop Loss: <b>{fmt_price(signal['sl'])}</b>\n"
        f"\n"
        f"Пивоты:\n{pivots_block}\n"
        f"\n"
        f"⏱ Время: <i>{datetime.fromtimestamp(signal['time']/1000, datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>\n"
    )
    # AVAX context block
    if context:
        eth_tr = context.get("eth_trend")
        days_unlock = context.get("days_to_unlock", "-")
        vol_usdt = context.get("recent_volume_usdt")
        session = context.get("session")
        eth_line = "🟢 В тренде с ETH" if eth_tr == "UP" else ("🔴 Против тренда ETH" if eth_tr == "DOWN" else "⚪ ETH: FLAT/UNKNOWN")
        vol_line = f"{(vol_usdt/1_000_000):.0f}M$" if isinstance(vol_usdt, int) else "-"
        msg += (
            "\n"
            "📌 <b>AVAX КОНТЕКСТ</b>:\n"
            f"├─ {eth_line}\n"
            f"├─ 🔒 До разблокировки: {days_unlock} дней\n"
            f"├─ 📊 Объем: {vol_line}\n"
            f"└─ 🕒 Сессия: {session}\n"
        )
    # Liquidity zones context
    if lz_ctx:
        swept = lz_ctx.get("swept")
        lvl = lz_ctx.get("level_price")
        vsp = lz_ctx.get("volume_spike")
        swept_line = "None"
        if swept == "buy":
            swept_line = f"Взята ликвидность сверху (sell-side), lvl={fmt_price(lvl) if lvl else '-'}"
        elif swept == "sell":
            swept_line = f"Взята ликвидность снизу (buy-side), lvl={fmt_price(lvl) if lvl else '-'}"
        msg += (
            "\n"
            "💧 <b>Liquidity</b>:\n"
            f"├─ Sweep: {swept_line}\n"
            f"└─ Volume spike: {'Yes' if vsp else 'No'}\n"
        )
    return msg


def send_telegram_message(bot: Bot, chat_id: str, text: str, logger: logging.Logger, 
                         reply_markup: Optional[Dict] = None) -> None:
    mode = getattr(config, "MODE", "auto").lower()
    # Добавляем "Бот #2" ко всем сообщениям
    if "Бот #2" not in text:
        text = f"🤖 <b>Бот #2</b>\n\n{text}"
    if mode == "dry":
        logger.info(f"(dry) Telegram message:\n{text}")
        return
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, 
                        disable_web_page_preview=True, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def create_signal_keyboard(signal_time: str) -> Optional[Dict]:
    """Создает клавиатуру с кнопками для сигнала"""
    try:
        if _HAS_TELEGRAM_LIB:
            keyboard = [
                [
                    InlineKeyboardButton("✅ В позиции", callback_data=f"in_position_{signal_time}"),
                    InlineKeyboardButton("⏭️ Пропустить", callback_data=f"skip_{signal_time}")
                ]
            ]
            return InlineKeyboardMarkup(keyboard).to_dict()
        else:
            # Fallback для прямого API
            return {
                "inline_keyboard": [[
                    {"text": "✅ В позиции", "callback_data": f"in_position_{signal_time}"},
                    {"text": "⏭️ Пропустить", "callback_data": f"skip_{signal_time}"}
                ]]
            }
    except Exception:
        return None

def _write_history(row: Dict, logger: logging.Logger) -> None:
    """
    Append signal rows into CSV in the bot folder (stable path regardless of working directory).
    """
    try:
        base_dir = os.path.dirname(__file__)
        path = Path(base_dir) / str(getattr(config, "HISTORY_CSV", "signals_history.csv"))
        file_exists = path.exists()
            # Расширенные поля для отслеживания TP/SL
        fieldnames = ["time","pair","timeframe","direction","quality","entry","tp1","tp2","tp3","sl","status",
                     "tp1_hit","tp2_hit","tp3_hit","sl_hit","close_price","close_time",
                     "partial_close_tp1","sl_moved_to_breakeven","new_sl","user_action"]
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            # Заполняем отсутствующие поля пустыми значениями
            for field in fieldnames:
                if field not in row:
                    row[field] = ""
            writer.writerow(row)
    except Exception as e:
        logger.error(f"History write failed: {e}")


def _get_current_price(pair: str, logger: logging.Logger) -> Optional[float]:
    """
    Получить текущую цену пары через exchange.
    """
    try:
        analyzer = ElliottWaveAnalyzer(logger=logger)
        # Преобразуем пару в формат CCXT (AVAX/USDT -> AVAX/USDT)
        symbol = pair.replace("/", "")
        # Пробуем получить тикер
        ticker = analyzer.exchange.fetch_ticker(pair)
        return float(ticker.get("last", ticker.get("close", 0)))
    except Exception as e:
        logger.error(f"Failed to get current price for {pair}: {e}")
        return None


def _check_tp_sl_signals(logger: logging.Logger, bot: Optional[Bot] = None, chat_id: Optional[str] = None) -> None:
    """
    Проверяет открытые сигналы на срабатывание TP/SL и обновляет их статус.
    """
    try:
        base_dir = os.path.dirname(__file__)
        path = Path(base_dir) / str(getattr(config, "HISTORY_CSV", "signals_history.csv"))
        if not path.exists():
            return
        
        # Получаем текущую цену
        current_price = _get_current_price(config.PAIR, logger)
        if current_price is None:
            return
        
        # Читаем все сигналы
        signals = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                signals.append(row)
        
        # Обновляем открытые сигналы
        updated = False
        updates = []
        
        for signal in signals:
            status = signal.get("status", "").strip()
            if status != "opened":
                continue
            
            direction = signal.get("direction", "").strip()
            entry = signal.get("entry", "").strip()
            tp1 = signal.get("tp1", "").strip()
            tp2 = signal.get("tp2", "").strip()
            tp3 = signal.get("tp3", "").strip()
            sl = signal.get("sl", "").strip()
            
            if not entry or not tp1 or not sl:
                continue
            
            try:
                entry_f = float(entry)
                tp1_f = float(tp1)
                tp2_f = float(tp2) if tp2 else None
                tp3_f = float(tp3) if tp3 else None
                sl_f = float(sl)
            except (ValueError, TypeError):
                continue
            
            # Проверяем срабатывание уровней
            tp1_hit = signal.get("tp1_hit", "").strip() == "1"
            tp2_hit = signal.get("tp2_hit", "").strip() == "1"
            tp3_hit = signal.get("tp3_hit", "").strip() == "1"
            sl_hit = signal.get("sl_hit", "").strip() == "1"
            partial_close_tp1 = signal.get("partial_close_tp1", "").strip() == "1"
            sl_moved_to_breakeven = signal.get("sl_moved_to_breakeven", "").strip() == "1"
            new_sl = signal.get("new_sl", "").strip()
            
            new_tp1_hit = tp1_hit
            new_tp2_hit = tp2_hit
            new_tp3_hit = tp3_hit
            new_sl_hit = sl_hit
            new_status = status
            new_partial_close_tp1 = partial_close_tp1
            new_sl_moved_to_breakeven = sl_moved_to_breakeven
            new_sl_value = new_sl if new_sl else sl
            
            if direction == "BUY":
                # Для BUY: цена должна подняться до TP или упасть до SL
                # Проверяем SL первым (приоритет)
                if not sl_hit and current_price <= sl_f:
                    new_sl_hit = True
                    new_status = "closed_sl"
                else:
                    # Проверяем TP уровни независимо (не elif, чтобы можно было достичь TP2/TP3 даже если цена упала после TP1)
                    if not tp1_hit and current_price >= tp1_f:
                        new_tp1_hit = True
                        # Частичное закрытие на TP1 (50% позиции)
                        if not partial_close_tp1:
                            new_partial_close_tp1 = True
                        # Перемещение SL в безубыток после TP1
                        if not sl_moved_to_breakeven:
                            new_sl_moved_to_breakeven = True
                            # Новый SL = Entry (безубыток)
                            new_sl_value = str(entry_f)
                            sl_f = entry_f  # Обновляем для дальнейших проверок
                    if tp1_hit and tp2_f and not tp2_hit and current_price >= tp2_f:
                        new_tp2_hit = True
                    if tp2_hit and tp3_f and not tp3_hit and current_price >= tp3_f:
                        new_tp3_hit = True
                        new_status = "closed_tp3"
            elif direction == "SELL":
                # Для SELL: цена должна упасть до TP или подняться до SL
                # Проверяем SL первым (приоритет)
                if not sl_hit and current_price >= sl_f:
                    new_sl_hit = True
                    new_status = "closed_sl"
                else:
                    # Проверяем TP уровни независимо (не elif, чтобы можно было достичь TP2/TP3 даже если цена поднялась после TP1)
                    if not tp1_hit and current_price <= tp1_f:
                        new_tp1_hit = True
                        # Частичное закрытие на TP1 (50% позиции)
                        if not partial_close_tp1:
                            new_partial_close_tp1 = True
                        # Перемещение SL в безубыток после TP1
                        if not sl_moved_to_breakeven:
                            new_sl_moved_to_breakeven = True
                            # Новый SL = Entry (безубыток)
                            new_sl_value = str(entry_f)
                            sl_f = entry_f  # Обновляем для дальнейших проверок
                    if tp1_hit and tp2_f and not tp2_hit and current_price <= tp2_f:
                        new_tp2_hit = True
                    if tp2_hit and tp3_f and not tp3_hit and current_price <= tp3_f:
                        new_tp3_hit = True
                        new_status = "closed_tp3"
            
            # Если что-то изменилось, обновляем
            if (new_tp1_hit != tp1_hit or new_tp2_hit != tp2_hit or 
                new_tp3_hit != tp3_hit or new_sl_hit != sl_hit or new_status != status or
                new_partial_close_tp1 != partial_close_tp1 or new_sl_moved_to_breakeven != sl_moved_to_breakeven or
                new_sl_value != new_sl):
                
                signal["tp1_hit"] = "1" if new_tp1_hit else "0"
                signal["tp2_hit"] = "1" if new_tp2_hit else "0"
                signal["tp3_hit"] = "1" if new_tp3_hit else "0"
                signal["sl_hit"] = "1" if new_sl_hit else "0"
                signal["status"] = new_status
                signal["partial_close_tp1"] = "1" if new_partial_close_tp1 else "0"
                signal["sl_moved_to_breakeven"] = "1" if new_sl_moved_to_breakeven else "0"
                signal["new_sl"] = new_sl_value
                
                if new_status.startswith("closed"):
                    signal["close_price"] = str(current_price)
                    signal["close_time"] = str(int(time.time() * 1000))
                
                # Проверяем есть ли реальные изменения для уведомлений
                has_notification_changes = (
                    (new_tp1_hit and not tp1_hit) or
                    (new_tp2_hit and not tp2_hit) or
                    (new_tp3_hit and not tp3_hit) or
                    (new_sl_hit and not sl_hit) or
                    (new_status.startswith("closed") and not status.startswith("closed")) or
                    (new_partial_close_tp1 and not partial_close_tp1) or
                    (new_sl_moved_to_breakeven and not sl_moved_to_breakeven)
                )
                
                # Добавляем в updates только если есть изменения для уведомлений
                if has_notification_changes:
                    updates.append({
                        "signal": signal,
                        "tp1_hit": new_tp1_hit and not tp1_hit,
                        "tp2_hit": new_tp2_hit and not tp2_hit,
                        "tp3_hit": new_tp3_hit and not tp3_hit,
                        "sl_hit": new_sl_hit and not sl_hit,
                        "closed": new_status.startswith("closed") and not status.startswith("closed"),
                        "partial_close": new_partial_close_tp1 and not partial_close_tp1,
                        "sl_moved": new_sl_moved_to_breakeven and not sl_moved_to_breakeven
                    })
                
                updated = True
        
        # Если были обновления, перезаписываем файл
        if updated:
            # Создаем резервную копию
            backup_path = path.with_suffix(".csv.backup")
            try:
                import shutil
                shutil.copy2(path, backup_path)
            except Exception:
                pass
            
            # Перезаписываем файл с обновленными данными
            fieldnames = ["time","pair","timeframe","direction","quality","entry","tp1","tp2","tp3","sl","status",
                         "tp1_hit","tp2_hit","tp3_hit","sl_hit","close_price","close_time",
                         "partial_close_tp1","sl_moved_to_breakeven","new_sl","user_action"]
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for signal in signals:
                    # Заполняем отсутствующие поля
                    for field in fieldnames:
                        if field not in signal:
                            signal[field] = ""
                    writer.writerow(signal)
            
            # Отправляем уведомления в Telegram только для сигналов "в позиции" и только если есть реальные изменения
            # ВАЖНО: Отслеживание ведется для ВСЕХ сигналов, но уведомления только для "в позиции"
            if bot and chat_id:
                for update_info in updates:
                    sig = update_info["signal"]
                    # Проверяем выбор пользователя - отправляем уведомления только если "в позиции"
                    user_action = sig.get("user_action", "").strip()
                    if user_action != "in_position":
                        # Пропускаем уведомления, но отслеживание продолжается для статистики
                        logger.debug(f"Signal {sig.get('time', '?')} skipped (user_action={user_action}), but tracking continues")
                        continue
                    
                    # Проверяем, есть ли реальные изменения
                    has_changes = (
                        update_info["tp1_hit"] or 
                        update_info["tp2_hit"] or 
                        update_info["tp3_hit"] or 
                        update_info["sl_hit"] or 
                        update_info["closed"] or
                        update_info.get("partial_close", False) or
                        update_info.get("sl_moved", False)
                    )
                    
                    if not has_changes:
                        continue  # Пропускаем если нет изменений
                    
                    direction_ru = "ЛОНГ" if sig.get("direction") == "BUY" else "ШОРТ"
                    time_str = sig.get("time", "")
                    try:
                        if len(time_str) == 13:
                            dt = datetime.fromtimestamp(int(time_str) / 1000)
                            time_str = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                    
                    msg_parts = [f"📊 <b>Обновление сигнала</b>"]
                    msg_parts.append(f"• Время сигнала: {time_str}")
                    msg_parts.append(f"• Направление: {direction_ru}")
                    msg_parts.append(f"• Вход: {sig.get('entry', '?')}")
                    msg_parts.append(f"• Текущая цена: {current_price:.6f}")
                    
                    if update_info["tp1_hit"]:
                        msg_parts.append(f"✅ <b>TP1 достигнут!</b> ({sig.get('tp1', '?')})")
                        if update_info.get("partial_close"):
                            msg_parts.append(f"💰 <b>Частичное закрытие 50%</b> позиции на TP1")
                        if update_info.get("sl_moved"):
                            new_sl_val = sig.get("new_sl", sig.get("entry", "?"))
                            msg_parts.append(f"🛡️ <b>SL перемещен в безубыток</b> ({new_sl_val})")
                    if update_info["tp2_hit"]:
                        msg_parts.append(f"✅ <b>TP2 достигнут!</b> ({sig.get('tp2', '?')})")
                    if update_info["tp3_hit"]:
                        msg_parts.append(f"🎯 <b>TP3 достигнут!</b> ({sig.get('tp3', '?')})")
                    if update_info["sl_hit"]:
                        sl_used = sig.get("new_sl") or sig.get("sl", "?")
                        msg_parts.append(f"❌ <b>Stop Loss сработал!</b> ({sl_used})")
                    if update_info["closed"]:
                        close_price = sig.get("close_price", current_price)
                        msg_parts.append(f"🔒 <b>Позиция закрыта</b> на цене {close_price}")
                    
                    msg = "\n".join(msg_parts)
                    send_telegram_message(bot, chat_id, msg, logger)
                    logger.info(f"TP/SL update sent for signal {time_str}")
    
    except Exception as e:
        logger.error(f"TP/SL check failed: {e}")


def check_elliott_wave(analyzer: ElliottWaveAnalyzer, logger: logging.Logger) -> Optional[Dict]:
    try:
        bars = analyzer.get_historical_data(limit=300)
        if not bars:
            return None
        signal = analyzer.get_signal(bars)
        return signal
    except Exception as e:
        logger.error(f"Elliott check failed: {e}")
        return None

def check_multi_timeframes(pair: str, tfs, logger: logging.Logger) -> Dict[str, Optional[Dict]]:
    results: Dict[str, Optional[Dict]] = {}
    for tf in tfs:
        try:
            analyzer = ElliottWaveAnalyzer(logger=logger, timeframe=tf)
            bars = analyzer.get_historical_data(limit=300)
            results[tf] = analyzer.get_signal(bars) if bars else None
        except Exception as e:
            logger.error(f"MTF check failed for {tf}: {e}")
            results[tf] = None
    return results

def check_multi_timeframes_with_reasons(pair: str, tfs, logger: logging.Logger) -> Tuple[Dict[str, Optional[Dict]], Dict[str, Dict]]:
    """
    Same as check_multi_timeframes(), but also returns per-TF reject reasons from the analyzer.
    Uses a shared ccxt exchange instance to reduce Binance load.
    """
    results: Dict[str, Optional[Dict]] = {}
    reasons: Dict[str, Dict] = {}
    shared_ex = None
    for tf in tfs:
        try:
            analyzer = ElliottWaveAnalyzer(logger=logger, timeframe=tf, exchange=shared_ex)
            shared_ex = analyzer.exchange
            bars = analyzer.get_historical_data(limit=300)
            sig = analyzer.get_signal(bars) if bars else None
            results[tf] = sig
            reasons[tf] = {"reason": getattr(analyzer, "last_reject_reason", "unknown"),
                           "details": getattr(analyzer, "last_reject_details", {})}
        except Exception as e:
            logger.error(f"MTF check failed for {tf}: {e}")
            results[tf] = None
            reasons[tf] = {"reason": "exception", "details": {"error": str(e)}}
    return results, reasons

def _format_reason(tf: str, info: Dict) -> str:
    r = info.get("reason", "-")
    d = info.get("details") or {}
    # Human-readable (RU) mappings
    def _trend_ru(t: str) -> str:
        return {"UP": "ВВЕРХ", "DOWN": "ВНИЗ", "FLAT": "ФЛЭТ", "UNKNOWN": "НЕИЗВЕСТНО"}.get(str(t), str(t))

    def _reason_ru(code: str) -> str:
        m = {
            "ok": "ок",
            "trend": "тренд",
            "market_quality": "фильтр рынка",
            "no_wave": "нет паттерна (1-2-3-4-5)",
            "not_enough_pivots": "мало пивотов",
            "not_enough_bars": "мало свечей",
            "avax_bad_time": "вне торгового времени",
            "avax_unlock_window": "окно разблокировок",
            "exception": "ошибка",
            "sweep_setup": "сетап свип+возврат",
            "trend_blocked": "запрещено трендом",
            "liquidity_blocked": "заблокировано ликвидностью",
            "below_quality": "ниже порога качества",
            "deduped": "антидубль",
            "no_entry_signal": "нет входного сигнала",
        }
        return m.get(code, code)

    if r == "market_quality":
        if "volume_ratio" in d:
            try:
                return f"{tf}: {_reason_ru(r)} vol_ratio={float(d.get('volume_ratio')):.2f} ≤ min={d.get('min_ratio')}"
            except Exception:
                return f"{tf}: {_reason_ru(r)} (volume_ratio)"
        if "quote_vol_usdt" in d:
            try:
                return f"{tf}: {_reason_ru(r)} qv={int(float(d.get('quote_vol_usdt')))} ≤ min={int(float(d.get('min_quote_vol_usdt')))}"
            except Exception:
                return f"{tf}: {_reason_ru(r)} (quote_vol)"
        if "spread_pct" in d:
            try:
                return f"{tf}: {_reason_ru(r)} spread={float(d.get('spread_pct')):.2f}% ≥ max={d.get('max_spread_pct')}"
            except Exception:
                return f"{tf}: {_reason_ru(r)} (spread)"
        return f"{tf}: {_reason_ru(r)}"
    if r == "no_wave":
        return f"{tf}: {_reason_ru(r)}"
    if r == "not_enough_pivots":
        return f"{tf}: {_reason_ru(r)}"
    if r == "avax_bad_time":
        return f"{tf}: {_reason_ru(r)}"
    if r == "avax_unlock_window":
        return f"{tf}: {_reason_ru(r)}"
    if r == "not_enough_bars":
        return f"{tf}: {_reason_ru(r)}"
    if r == "exception":
        return f"{tf}: {_reason_ru(r)}"
    if r == "ok":
        return f"{tf}: {_reason_ru(r)}"
    if r == "trend":
        return f"{tf}: {_reason_ru(r)}={_trend_ru(d.get('trend','-'))}"
    if r == "sweep_setup":
        return f"{tf}: {_reason_ru(r)}"
    if r == "trend_blocked":
        return f"{tf}: {_reason_ru(r)}"
    if r == "liquidity_blocked":
        return f"{tf}: {_reason_ru(r)}"
    if r == "below_quality":
        return f"{tf}: {_reason_ru(r)}"
    if r == "deduped":
        return f"{tf}: {_reason_ru(r)}"
    if r == "no_entry_signal":
        return f"{tf}: {_reason_ru(r)}"
    return f"{tf}: {_reason_ru(r)}"

def _tf_to_minutes(tf: str) -> int:
    num = int(''.join([c for c in tf if c.isdigit()]) or "1")
    unit = ''.join([c for c in tf if c.isalpha()]) or "m"
    if unit == "m":
        return num
    if unit == "h":
        return num * 60
    if unit == "d":
        return num * 1440
    return num


def _determine_trend_from_bars(bars) -> str:
    """
    Очень простой фильтр направления (как у людей): SMA10 vs SMA20.
    Возвращает: UP / DOWN / FLAT
    """
    try:
        if not bars or len(bars) < 25:
            return "FLAT"
        close = [float(b["close"]) for b in bars]
        ma_fast = sum(close[-10:]) / 10.0
        ma_slow = sum(close[-20:]) / 20.0
        if ma_fast > ma_slow * 1.002:
            return "UP"
        if ma_fast < ma_slow * 0.998:
            return "DOWN"
        return "FLAT"
    except Exception:
        return "FLAT"


def _compute_atr(bars, period: int) -> List[float]:
    """ATR (SMA) по OHLCV-словарям, без зависимостей."""
    try:
        if not bars or len(bars) < period + 1:
            return []
        trs: List[float] = []
        for i in range(1, len(bars)):
            high = float(bars[i]["high"])
            low = float(bars[i]["low"])
            prev_close = float(bars[i - 1]["close"])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        atr: List[float] = []
        for i in range(len(trs)):
            if i + 1 < period:
                atr.append(0.0)
            else:
                window = trs[i + 1 - period:i + 1]
                atr.append(sum(window) / float(period))
        return atr
    except Exception:
        return []


def _build_sweep_signal(bars_entry: List[Dict], direction: str, lz_context: Dict, trend: str) -> Dict:
    """
    Сигнал по сетапу Sweep+Return (ликвидность), с TP/SL по ATR.
    direction: BUY/SELL
    """
    last = bars_entry[-1]
    entry = float(last["close"])
    atr_len = int(getattr(config, "SWEEP_ATR_LEN", 14))
    atrs = _compute_atr(bars_entry, atr_len)
    last_atr = float(atrs[-1]) if atrs else 0.0
    # fallback если ATR не посчитался
    if last_atr <= 0:
        last_atr = entry * 0.003  # ~0.3%

    sl_mult = float(getattr(config, "SWEEP_SL_ATR_MULT", 0.8))
    tp1_mult = float(getattr(config, "SWEEP_TP1_ATR_MULT", 1.0))
    tp2_mult = float(getattr(config, "SWEEP_TP2_ATR_MULT", 2.0))
    tp3_mult = float(getattr(config, "SWEEP_TP3_ATR_MULT", 3.0))

    if direction == "BUY":
        sl = float(last["low"]) - (sl_mult * last_atr)
        tp1 = entry + tp1_mult * last_atr
        tp2 = entry + tp2_mult * last_atr
        tp3 = entry + tp3_mult * last_atr
    else:
        sl = float(last["high"]) + (sl_mult * last_atr)
        tp1 = entry - tp1_mult * last_atr
        tp2 = entry - tp2_mult * last_atr
        tp3 = entry - tp3_mult * last_atr

    # Cap SL distance by % of entry (high-vol protection)
    try:
        max_sl_pct = float(getattr(config, "SWEEP_MAX_SL_PCT", 2.0))
        if max_sl_pct > 0:
            max_dist = entry * (max_sl_pct / 100.0)
            if direction == "BUY":
                sl = max(sl, entry - max_dist)
            else:
                sl = min(sl, entry + max_dist)
    except Exception:
        pass

    # quality: базово 60, бонус за совпадение с трендом и volume spike
    q = 60
    if (direction == "BUY" and trend == "UP") or (direction == "SELL" and trend == "DOWN"):
        q += 10
    if bool(lz_context.get("volume_spike")):
        q += 5
    q = int(max(0, min(100, q)))

    level = lz_context.get("level_price")
    lvl_i = int(round(float(level) * 1e6)) if isinstance(level, (int, float)) else 0

    return {
        "setup": "SWEEP",
        "direction": direction,
        "quality": q,
        "entry": entry,
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "sl": float(sl),
        "time": int(last["time"]),
        # fingerprints / context
        "wave_points": [],
        "wave4_price": None,
        "lz_context": lz_context,
        "sweep_fp": f"{lz_context.get('swept')}@{lvl_i}",
    }

def aggregate_signals(mtfs: Dict[str, Optional[Dict]], logger: logging.Logger) -> Optional[Dict]:
    # Require all provided TF signals to exist and agree in direction
    available = {tf: sig for tf, sig in mtfs.items() if sig}
    if not available:
        return None
    directions = {sig["direction"] for sig in available.values()}
    if len(directions) != 1:
        return None
    direction = next(iter(directions))
    # Entry is smallest TF
    sorted_tfs = sorted(available.keys(), key=_tf_to_minutes)
    entry_tf = sorted_tfs[0]
    entry_sig = available[entry_tf]
    # Weighted quality
    weights = getattr(config, "QUALITY_WEIGHTS", {})
    if not weights:
        weights = {tf: 1.0 for tf in available.keys()}
    total_w = 0.0
    weighted_q = 0.0
    for tf, sig in available.items():
        w = float(weights.get(tf, 1.0))
        total_w += w
        weighted_q += w * float(sig.get("quality", 0))
    agg_quality = int(round(weighted_q / total_w)) if total_w > 0 else 0
    return {
        "direction": direction,
        "quality": agg_quality,
        "entry": entry_sig["entry"],
        "tp1": entry_sig["tp1"],
        "tp2": entry_sig["tp2"],
        "tp3": entry_sig["tp3"],
        "sl": entry_sig["sl"],
        "wave4_price": entry_sig.get("wave4_price"),
        "time": entry_sig["time"],
        "entry_tf": entry_tf,
        "mtf": available,
    }


def main():
    # Single-instance guard
    if os.name == "nt" and not acquire_single_instance():
        print("Another Elliott Wave Bot instance is already running. Exiting.")
        return

    logger = setup_logging()
    logger.info("Starting Elliott Wave Bot")

    if not getattr(config, "TELEGRAM_TOKEN", "") or not getattr(config, "TELEGRAM_CHAT_ID", ""):
        logger.error("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID не заданы. Добавь их в переменные окружения и перезапусти.")
        logger.error("Пример PowerShell:  setx TELEGRAM_TOKEN \"123:abc\"  &&  setx TELEGRAM_CHAT_ID \"123456\"")
        return

    bot = Bot(token=config.TELEGRAM_TOKEN)
    analyzer = ElliottWaveAnalyzer(logger=logger)

    # Start message
    try:
        send_telegram_message(bot, config.TELEGRAM_CHAT_ID, "✅ Бот #2 запущен", logger)
        logger.info("Start message sent to Telegram")
    except Exception as e:
        logger.error(f"Failed to send start message: {e}")

    if getattr(config, "ENABLE_MULTI_TF", False):
        sleep_secs = multi_timeframes_sleep_seconds(getattr(config, "MULTI_TIMEFRAMES", ["15m", "1h", "4h", "1d"]))
        logger.info(f"MTF mode ON. Loop interval: {sleep_secs} seconds for TFs {getattr(config, 'MULTI_TIMEFRAMES', [])}")
    else:
        sleep_secs = timeframe_sleep_seconds(config.TIMEFRAME)
        logger.info(f"Loop interval for timeframe {config.TIMEFRAME}: {sleep_secs} seconds")

    # Dedupe control: configurable
    DEDUPE_SECONDS = int(getattr(config, "DEDUP_SECONDS", 7200))
    last_signal_key: Optional[str] = None
    last_signal_time: Optional[float] = None
    last_agg_key: Optional[str] = None
    last_agg_time: Optional[float] = None
    active_signals = []  # track for cancellation: dicts with direction, wave4, tf tag

    # Telegram status about "why no signals"
    status_enabled = bool(getattr(config, "STATUS_TELEGRAM_ENABLED", True))
    status_interval = int(getattr(config, "STATUS_INTERVAL_SECONDS", 3600))
    status_last_sent = 0.0
    status_include_per_tf = bool(getattr(config, "STATUS_INCLUDE_PER_TF", True))
    status_max_lines = int(getattr(config, "STATUS_MAX_LINES", 12))
    reason_counters = Counter()
    last_reasons_snapshot: Dict[str, Dict] = {}
    # Hourly (status) stats
    setup_counters = Counter()
    trend_counters = Counter()
    sent_quality_sum = 0.0
    sent_quality_count = 0

    # Probabilistic model cache (loaded once, auto-updated periodically)
    prob_model = None
    prob_model_last_update = 0.0
    prob_model_update_interval = float(getattr(config, "PROB_MODEL_AUTO_UPDATE_HOURS", 24.0)) * 3600  # по умолчанию раз в 24 часа
    prob_model_min_new_signals = int(getattr(config, "PROB_MODEL_MIN_NEW_SIGNALS", 10))  # минимум новых сигналов для обновления
    
    def _try_update_prob_model():
        """Попытка автоматического обновления вероятностной модели"""
        nonlocal prob_model, prob_model_last_update
        try:
            if not bool(getattr(config, "PROB_MODEL_ENABLED", False)):
                return
            if not bool(getattr(config, "PROB_MODEL_AUTO_UPDATE", True)):
                return
            
            now_ts = time.time()
            # Проверяем интервал
            if (now_ts - prob_model_last_update) < prob_model_update_interval:
                return
            
            # Импортируем функцию обновления
            try:
                from auto_update_model import should_update_model, update_model
                model_path = str(getattr(config, "PROB_MODEL_PATH", "prob_model.json"))
                model_path = os.path.join(os.path.dirname(__file__), model_path)
                
                should, reason = should_update_model(
                    model_path,
                    min_age_hours=int(prob_model_update_interval / 3600),
                    min_new_signals=prob_model_min_new_signals
                )
                
                if should:
                    logger.info(f"🔄 Автообновление модели: {reason}")
                    if update_model(logger):
                        prob_model_last_update = now_ts
                        # Перезагружаем модель
                        prob_model = _load_prob_model(model_path)
                        logger.info("✅ Модель перезагружена после обновления")
            except ImportError:
                logger.warning("auto_update_model.py не найден, автообновление отключено")
            except Exception as e:
                logger.error(f"Ошибка автообновления модели: {e}")
        except Exception:
            pass  # Игнорируем ошибки автообновления
    
    try:
        if bool(getattr(config, "PROB_MODEL_ENABLED", False)):
            model_path = str(getattr(config, "PROB_MODEL_PATH", "prob_model.json"))
            prob_model = _load_prob_model(os.path.join(os.path.dirname(__file__), model_path))
            prob_model_last_update = time.time()
    except Exception:
        prob_model = None

    while True:
        try:
            
            if getattr(config, "ENABLE_MULTI_TF", False):
                policy = str(getattr(config, "MTF_POLICY", "strict_align") or "strict_align").lower()
                if policy == "strict_align":
                    # Старое поведение: требуем Elliott на обоих TF и совпадение направления
                    tfs = getattr(config, "MULTI_TIMEFRAMES", ["1h", "4h"])
                    mtf_results, mtf_reasons = check_multi_timeframes_with_reasons(config.PAIR, tfs, logger)
                    last_reasons_snapshot = mtf_reasons
                    for tf, info in mtf_reasons.items():
                        reason_counters[f"{tf}:{info.get('reason','-')}"] += 1
                    agg = aggregate_signals(mtf_results, logger)
                    if not agg:
                        logger.info("MTF: no aligned signal")
                        reason_counters["mtf:no_aligned_signal"] += 1
                    else:
                        # Liquidity filter on entry TF bars
                        lz_ok = True
                        lz_context = {}
                        try:
                            if getattr(config, "LIQUIDITY_FILTER_ENABLED", True):
                                entry_tf = agg.get("entry_tf") or tfs[0]
                                an_entry = ElliottWaveAnalyzer(logger=logger, timeframe=entry_tf)
                                lookback = int(getattr(config, "LZ_LOOKBACK_BARS", 200))
                                entry_bars = an_entry.get_historical_data(limit=lookback)
                                lz = LiquidityZones(logger)
                                lz_ok, lz_context = lz.evaluate(direction=agg["direction"], bars=entry_bars)
                        except Exception as e:
                            logger.error(f"LZ filter error: {e}")
                            lz_ok = True
                        if not lz_ok:
                            logger.info("Liquidity filter blocked MTF signal")
                            reason_counters["liquidity_blocked"] += 1
                            continue
                        agg["lz_context"] = lz_context
                        dir_key = agg["direction"]
                        fp_parts = []
                        for tf in sorted([k for k in mtf_results.keys() if mtf_results.get(k)], key=_tf_to_minutes):
                            sig = mtf_results.get(tf) or {}
                            wp = sig.get("wave_points", [])
                            if wp:
                                fp = "-".join([f"{p['type']}@{int(round(p['price']*1e6))}" for p in wp])
                                fp_parts.append(f"{tf}:{fp}")
                        agg_key = f"{config.PAIR}|MTF|{dir_key}|{'|'.join(fp_parts)}|{agg['quality']}"
                        now_ts = time.time()
                        allowed = True
                        dedupe_window = getattr(config, "DEDUPE_SECONDS_AGG", 7200)
                        if last_agg_key == agg_key and last_agg_time is not None and (now_ts - last_agg_time) < dedupe_window:
                            allowed = False
                        if allowed:
                            # Quality filter (user prefers quality 65+)
                            agg_quality = float(agg.get('quality', 0))
                            if agg_quality < 65:
                                logger.info(f"MTF signal skipped: quality {agg_quality} < 65")
                                continue
                            
                            emoji = "🟢" if agg["direction"] == "BUY" else "🔴"
                            header = f"{emoji} <b>MTF Elliott Signal</b> ({'/'.join(tfs)})"
                            parts = [
                                header,
                                f"• Пара: <b>{config.PAIR}</b>",
                                f"• Направление: <b>{'BUY' if agg['direction']=='BUY' else 'SELL'}</b>",
                                f"• Сводное качество: <b>{agg['quality']}%</b>",
                                f"• Цена входа ({agg.get('entry_tf','entry')}): <b>{agg['entry']:.6f}</b>",
                                f"• TP1: <b>{agg['tp1']:.6f}</b>  TP2: <b>{agg['tp2']:.6f}</b>  TP3: <b>{agg['tp3']:.6f}</b>",
                                f"• SL: <b>{agg['sl']:.6f}</b>",
                            ]
                            # Per-TF qualities dynamically
                            q_parts = []
                            for tf in sorted([k for k in mtf_results.keys() if mtf_results.get(k)], key=_tf_to_minutes):
                                q_parts.append(f"{tf}={(mtf_results.get(tf) or {}).get('quality','-')}")
                            parts.append("• Качества: " + " | ".join(q_parts))
                            msg = "\n".join(parts)
                            signal_time = str(int(agg["time"]))
                            keyboard = create_signal_keyboard(signal_time)
                            send_telegram_message(bot, config.TELEGRAM_CHAT_ID, msg, logger, reply_markup=keyboard)
                            last_agg_key = agg_key
                            last_agg_time = now_ts
                            logger.info("MTF signal sent")
                            # History CSV
                            _write_history({
                                "time": int(agg["time"]),
                                "pair": config.PAIR,
                                "timeframe": f"MTF({ '/'.join(tfs) })",
                                "direction": agg["direction"],
                                "quality": agg["quality"],
                                "entry": agg["entry"],
                                "tp1": agg["tp1"], "tp2": agg["tp2"], "tp3": agg["tp3"],
                                "sl": agg["sl"], "status": "opened",
                                "tp1_hit": "0", "tp2_hit": "0", "tp3_hit": "0", "sl_hit": "0",
                                "close_price": "", "close_time": "",
                                "partial_close_tp1": "0", "sl_moved_to_breakeven": "0", "new_sl": "",
                                "user_action": ""
                            }, logger)
                            # Track cancellation if enabled
                            if getattr(config, "CANCEL_ON_WAVE4_BREACH", True) and agg.get("wave4_price") is not None:
                                active_signals.append({"direction": agg["direction"], "wave4": float(agg["wave4_price"]), "tf": "15m"})
                else:
                    # Новое поведение (как человек): 1h фильтр направления, 15m триггер входа
                    entry_tf = str(getattr(config, "MTF_ENTRY_TF", "15m"))
                    trend_tf = str(getattr(config, "MTF_TREND_TF", "1h"))
                    allow_against = bool(getattr(config, "MTF_ALLOW_AGAINST_TREND", False))
                    against_penalty = int(getattr(config, "MTF_AGAINST_TREND_PENALTY", 20))
                    lz_mode = str(getattr(config, "LIQUIDITY_FILTER_MODE", "block") or "block").lower()
                    lz_penalty = int(getattr(config, "LZ_SCORE_PENALTY", 15))

                    # shared exchange to reduce load
                    shared_ex = None
                    # trend
                    an_trend = ElliottWaveAnalyzer(logger=logger, timeframe=trend_tf, exchange=shared_ex)
                    shared_ex = an_trend.exchange
                    bars_trend = an_trend.get_historical_data(limit=300)
                    trend = _determine_trend_from_bars(bars_trend)
                    trend_reason = "ok" if bars_trend else "no_bars"
                    trend_counters[f"trend:{trend}"] += 1
                    last_reasons_snapshot = {
                        entry_tf: {"reason": "pending", "details": {}},
                        trend_tf: {"reason": "trend", "details": {"trend": trend, "note": trend_reason}},
                    }

                    # entry signal
                    an_entry = ElliottWaveAnalyzer(logger=logger, timeframe=entry_tf, exchange=shared_ex)
                    shared_ex = an_entry.exchange
                    bars_entry = an_entry.get_historical_data(limit=300)
                    sig = an_entry.get_signal(bars_entry) if bars_entry else None
                    entry_reason = getattr(an_entry, "last_reject_reason", "unknown")
                    entry_details = getattr(an_entry, "last_reject_details", {})
                    last_reasons_snapshot[entry_tf] = {"reason": entry_reason, "details": entry_details}
                    reason_counters[f"{entry_tf}:{entry_reason}"] += 1

                    # If Elliott didn't produce a signal, try SWEEP+RETURN (AVAX-friendly)
                    if not sig:
                        sweep_enabled = bool(getattr(config, "ENABLE_SWEEP_SETUP", True))
                        allow_on_mq = bool(getattr(config, "SWEEP_ALLOW_ON_MARKET_QUALITY_REJECT", True))
                        mq_penalty = int(getattr(config, "SWEEP_MARKET_QUALITY_PENALTY", 10) or 0)
                        is_mq_reject = entry_reason == "market_quality"
                        can_try_sweep = sweep_enabled and bool(bars_entry) and (not is_mq_reject or allow_on_mq)

                        if can_try_sweep:
                            try:
                                lz = LiquidityZones(logger)
                                buy_ok, buy_ctx = lz.evaluate(direction="BUY", bars=bars_entry)
                                sell_ok, sell_ctx = lz.evaluate(direction="SELL", bars=bars_entry)

                                sweep_sig = None
                                sweep_ctx: Dict = {}
                                if buy_ctx.get("swept") == "sell":
                                    sweep_ctx = buy_ctx
                                    sweep_sig = _build_sweep_signal(
                                        bars_entry, direction="BUY", lz_context=sweep_ctx, trend=trend
                                    )
                                elif sell_ctx.get("swept") == "buy":
                                    sweep_ctx = sell_ctx
                                    sweep_sig = _build_sweep_signal(
                                        bars_entry, direction="SELL", lz_context=sweep_ctx, trend=trend
                                    )

                                if sweep_sig:
                                    sig = sweep_sig
                                    entry_reason = "sweep_setup"
                                    # Если Elliott отфильтрован по market_quality, всё равно разрешаем SWEEP,
                                    # но добавляем штраф (контекст «грязного» рынка).
                                    if is_mq_reject and mq_penalty:
                                        base_sq = int(sig.get("quality") or 0)
                                        sig["quality"] = max(0, min(100, base_sq - mq_penalty))
                                        sig["mq_penalty"] = mq_penalty
                                    last_reasons_snapshot[entry_tf] = {"reason": entry_reason, "details": sweep_ctx}
                                    reason_counters[f"{entry_tf}:sweep_setup"] += 1
                                else:
                                    logger.info("MTF(trend_filter): no entry signal")
                                    reason_counters["mtf:no_entry_signal"] += 1
                                    continue
                            except Exception as e:
                                logger.error(f"Sweep setup error: {e}")
                                logger.info("MTF(trend_filter): no entry signal")
                                reason_counters["mtf:no_entry_signal"] += 1
                                continue
                        else:
                            logger.info("MTF(trend_filter): no entry signal")
                            reason_counters["mtf:no_entry_signal"] += 1
                            continue

                    # mark setup for message (after Elliott or Sweep)
                    sig["setup"] = sig.get("setup") or ("SWEEP" if entry_reason == "sweep_setup" else "ELLIOTT")

                    direction = sig.get("direction")
                    setup = str(sig.get("setup") or "ELLIOTT")
                    # trend filter (ослаблено): либо блокируем, либо штрафуем качество
                    against_trend = False
                    if direction == "BUY" and trend == "DOWN":
                        against_trend = True
                    if direction == "SELL" and trend == "UP":
                        against_trend = True
                    if against_trend and not allow_against:
                        logger.info("MTF(trend_filter): blocked by trend")
                        reason_counters["mtf:trend_blocked"] += 1
                        last_reasons_snapshot["mtf"] = {"reason": "trend_blocked", "details": {"trend": trend, "direction": direction}}
                        continue

                    # Liquidity evaluation on entry bars
                    lz_ok = True
                    lz_context = {}
                    try:
                        if getattr(config, "LIQUIDITY_FILTER_ENABLED", True):
                            lz = LiquidityZones(logger)
                            lz_ok, lz_context = lz.evaluate(direction=direction, bars=bars_entry)
                    except Exception as e:
                        logger.error(f"LZ filter error: {e}")
                        lz_ok = True
                        lz_context = {}

                    base_q = int(sig.get("quality", 0) or 0)
                    adj_q = base_q
                    if against_trend and allow_against:
                        if setup == "SWEEP":
                            effective_against_penalty = int(getattr(config, "SWEEP_AGAINST_TREND_PENALTY", against_penalty) or against_penalty)
                        else:
                            effective_against_penalty = against_penalty
                        adj_q = max(0, min(100, adj_q - effective_against_penalty))
                        sig["quality"] = adj_q
                        sig["trend_penalty"] = effective_against_penalty
                        reason_counters["mtf:against_trend_penalty"] += 1
                    if getattr(config, "LIQUIDITY_FILTER_ENABLED", True) and not lz_ok:
                        if lz_mode == "block":
                            reason_counters["liquidity_blocked"] += 1
                            last_reasons_snapshot["mtf"] = {"reason": "liquidity_blocked", "details": lz_context}
                            continue
                        # score mode
                        adj_q = max(0, min(100, base_q - lz_penalty))
                        sig["quality"] = adj_q
                        sig["lz_context"] = lz_context
                        sig["lz_penalty"] = lz_penalty
                        reason_counters["liquidity_penalty"] += 1
                    else:
                        sig["lz_context"] = lz_context

                    # Bonus if liquidity sweep matches direction (score-mode friendly)
                    try:
                        if getattr(config, "LIQUIDITY_FILTER_ENABLED", True) and lz_context:
                            desired = "sell" if direction == "BUY" else "buy"
                            if lz_context.get("swept") == desired:
                                bonus = int(getattr(config, "LZ_SCORE_BONUS", 10))
                                if bonus:
                                    adj_q = max(0, min(100, adj_q + bonus))
                                    sig["quality"] = adj_q
                                    sig["lz_bonus"] = bonus
                                    reason_counters["liquidity_bonus"] += 1
                    except Exception:
                        pass

                    # Do not send ultra-low quality signals after penalties/bonuses
                    if setup == "SWEEP":
                        min_send_q = int(getattr(config, "SWEEP_MIN_SEND_QUALITY", 0) or 0)
                    else:
                        min_send_q = int(getattr(config, "MIN_SEND_QUALITY", 0) or 0)
                    if min_send_q and adj_q < min_send_q:
                        reason_counters["mtf:below_quality"] += 1
                        continue

                    # Dedupe key based on pivots (entry TF)
                    wp = sig.get("wave_points", [])
                    pivot_fingerprint = (
                        "-".join([f"{p['type']}@{int(round(p['price']*1e6))}" for p in wp])
                        if wp
                        else str(sig.get("sweep_fp") or "no_wp")
                    )
                    mtf_key = f"{config.PAIR}|MTF_TREND|{trend_tf}->{entry_tf}|{trend}|{direction}|{setup}|{pivot_fingerprint}|{adj_q}"
                    now_ts = time.time()
                    dedupe_window = getattr(config, "DEDUPE_SECONDS_AGG", 7200)
                    if last_agg_key == mtf_key and last_agg_time is not None and (now_ts - last_agg_time) < dedupe_window:
                        reason_counters["mtf:deduped"] += 1
                        continue

                    # Build message
                    def _dir_ru(d: str) -> str:
                        return "ЛОНГ (BUY)" if d == "BUY" else ("ШОРТ (SELL)" if d == "SELL" else str(d))

                    def _trend_ru(t: str) -> str:
                        return {"UP": "ВВЕРХ", "DOWN": "ВНИЗ", "FLAT": "ФЛЭТ"}.get(t, str(t))

                    def _setup_ru(s: str) -> str:
                        return {"SWEEP": "СВИП+ВОЗВРАТ", "ELLIOTT": "ЭЛЛИОТТ"}.get(s, str(s))

                    emoji = "🟢" if direction == "BUY" else "🔴"
                    header = f"{emoji} <b>MTF Сигнал</b> [{_setup_ru(setup)}] (тренд {trend_tf}={_trend_ru(trend)}, вход {entry_tf})"
                    parts = [
                        header,
                        f"• Пара: <b>{config.PAIR}</b>",
                        f"• Направление: <b>{_dir_ru(direction)}</b>",
                        f"• Качество: <b>{adj_q}%</b>"
                        + (f" (Trend -{int(sig.get('trend_penalty') or against_penalty)})" if (against_trend and allow_against) else "")
                        + (f" (MQ -{int(sig.get('mq_penalty') or 0)})" if int(sig.get("mq_penalty") or 0) else "")
                        + (f" (LZ -{lz_penalty})" if (not lz_ok and lz_mode == "score") else ""),
                        f"• Вход ({entry_tf}): <b>{float(sig['entry']):.6f}</b>",
                        f"• Цели: TP1 <b>{float(sig['tp1']):.6f}</b> | TP2 <b>{float(sig['tp2']):.6f}</b> | TP3 <b>{float(sig['tp3']):.6f}</b>",
                        f"• Стоп (SL): <b>{float(sig['sl']):.6f}</b>",
                    ]
                    # Interpretations (as requested)
                    try:
                        if setup == "SWEEP" and direction == "BUY":
                            if not against_trend:
                                parts.append("• Интерпретация: первый шанс на отскок (sweep+возврат).")
                            else:
                                parts.append("• Интерпретация: первый шанс на отскок, но контртренд — осторожно.")
                        if setup == "ELLIOTT" and direction == "BUY" and trend == "UP":
                            parts.append("• Интерпретация: ближе к подтверждённому движению (реже, но сильнее).")
                    except Exception:
                        pass
                    if lz_context:
                        swept = lz_context.get("swept")
                        swept_ru = {"sell": "снизу (стопы лонгов)", "buy": "сверху (стопы шортов)"}.get(swept, str(swept))
                        parts.append(
                            f"• Ликвидность: свип={swept_ru} | уровень={lz_context.get('level_price')} | объёмный всплеск={'Да' if lz_context.get('volume_spike') else 'Нет'}"
                        )
                    msg = "\n".join(parts)

                    # --- Math probabilities (empirical) ---
                    try:
                        if not prob_model:
                            parts.append("• Матем. оценка: модель не построена (запусти build_prob_model.py).")
                        else:
                            est = _estimate_prob(
                                prob_model,
                                setup=setup,
                                direction=direction,
                                trend=trend,
                                quality=int(adj_q),
                            )
                            if est:
                                parts.append(
                                    f"• Матем. оценка (история N={est.n}): "
                                    f"P(TP1 до SL)={est.p_tp1:.0%} | P(TP2 до SL)={est.p_tp2:.0%} | P(TP3 до SL)={est.p_tp3:.0%} | "
                                    f"P(SL до TP1)={est.p_sl:.0%} | AvgR={est.avg_r:.2f}"
                                    + ("  ⚠️ мало данных" if est.n < 25 else "")
                                )
                            else:
                                parts.append("• Матем. оценка: нет статистики для этого типа сигнала (пока).")
                    except Exception:
                        pass

                    # --- News snapshot (RSS) ---
                    try:
                        if bool(getattr(config, "NEWS_ENABLED", False)):
                            snap = _build_news_snapshot(
                                rss_urls=list(getattr(config, "NEWS_RSS_URLS", [])),
                                lookback_hours=int(getattr(config, "NEWS_LOOKBACK_HOURS", 24)),
                                max_items=int(getattr(config, "NEWS_MAX_HEADLINES", 3)),
                                timeout=int(getattr(config, "NEWS_TIMEOUT_SECONDS", 10)),
                                strict_keywords=list(getattr(config, "NEWS_STRICT_KEYWORDS", [])),
                                fallback_keywords=list(getattr(config, "NEWS_FALLBACK_KEYWORDS", [])),
                                pos_keywords=list(getattr(config, "NEWS_POSITIVE_KEYWORDS", [])),
                                neg_keywords=list(getattr(config, "NEWS_NEGATIVE_KEYWORDS", [])),
                            )
                            if snap.items:
                                scope_ru = {"AVAX": "AVAX", "MACRO": "макро", "NONE": "нет"}.get(getattr(snap, "scope", "MACRO"), "макро")
                                parts.append(f"• Новости (24ч, {scope_ru}): {snap.label} (score={snap.score})")
                                for it in snap.items:
                                    parts.append(f"  - {it.title}")
                    except Exception:
                        pass

                    msg = "\n".join(parts)
                    # --- Probabilistic filters (skip noisy signals) ---
                    allow_signal = True
                    reject_reason = ""
                    q_bucket = "<50"
                    try:
                        q_int = int(adj_q)
                        if q_int >= 80:
                            q_bucket = "80+"
                        elif q_int >= 70:
                            q_bucket = "70-79"
                        elif q_int >= 60:
                            q_bucket = "60-69"
                        elif q_int >= 50:
                            q_bucket = "50-59"
                    except Exception:
                        pass

                    # Skip known weak buckets
                    weak_buckets = {
                        ("ELLIOTT", "SELL", "FLAT", "60-69"),
                        ("SWEEP", "BUY", "UP", "70-79"),
                        ("ELLIOTT", "SELL", "UP", "60-69"),
                    }
                    if (setup, direction, trend, q_bucket) in weak_buckets:
                        allow_signal = False
                        reject_reason = f"weak_bucket:{setup}|{direction}|{trend}|{q_bucket}"

                    # Probability-based filter if stats exist
                    try:
                        est = _estimate_prob(
                            prob_model,
                            setup=setup,
                            direction=direction,
                            trend=trend,
                            quality=int(adj_q),
                        ) if prob_model else None
                        if est:
                            # Stricter filters for high quality signals (80+)
                            if est.p_sl >= est.p_tp1:  # Changed: >= instead of >
                                allow_signal = False
                                reject_reason = f"p_sl{est.p_sl:.2f}>=p_tp1{est.p_tp1:.2f}"
                            elif est.p_sl > 0.45:  # Skip if SL probability > 45% (ослаблено с 40%)
                                allow_signal = False
                                reject_reason = f"p_sl_too_high_{est.p_sl:.2f}"
                            elif est.p_tp1 < 0.55:  # Skip if TP1 probability < 55% (ослаблено с 60%)
                                allow_signal = False
                                reject_reason = f"p_tp1_too_low_{est.p_tp1:.2f}"
                            elif est.n < 20:
                                allow_signal = False
                                reject_reason = f"low_stats_n={est.n}"
                    except Exception:
                        pass

                    # Minimal quality gate (user prefers quality 65+)
                    if allow_signal and float(adj_q) < 65:
                        allow_signal = False
                        reject_reason = f"low_quality_{adj_q}_need_65+"

                    if not allow_signal:
                        logger.info(f"MTF(trend_filter) signal skipped due to filter: {reject_reason}")
                        continue

                    signal_time = str(int(sig["time"]))
                    keyboard = create_signal_keyboard(signal_time)
                    send_telegram_message(bot, config.TELEGRAM_CHAT_ID, msg, logger, reply_markup=keyboard)
                    last_agg_key = mtf_key
                    last_agg_time = now_ts
                    logger.info("MTF(trend_filter) signal sent")
                    setup_counters[f"setup:{setup}"] += 1
                    try:
                        sent_quality_sum += float(adj_q)
                        sent_quality_count += 1
                    except Exception:
                        pass

                    _write_history({
                        "time": int(sig["time"]),
                        "pair": config.PAIR,
                        "timeframe": f"MTF(trend {trend_tf} -> entry {entry_tf})[{setup}]",
                        "direction": direction,
                        "quality": adj_q,
                        "entry": sig.get("entry"),
                        "tp1": sig.get("tp1"), "tp2": sig.get("tp2"), "tp3": sig.get("tp3"),
                        "sl": sig.get("sl"), "status": "opened",
                        "tp1_hit": "0", "tp2_hit": "0", "tp3_hit": "0", "sl_hit": "0",
                        "close_price": "", "close_time": "",
                        "partial_close_tp1": "0", "sl_moved_to_breakeven": "0", "new_sl": "",
                        "user_action": ""
                    }, logger)

                    if getattr(config, "CANCEL_ON_WAVE4_BREACH", True) and sig.get("wave4_price") is not None:
                        active_signals.append({"direction": direction, "wave4": float(sig["wave4_price"]), "tf": entry_tf})
            else:
                signal = check_elliott_wave(analyzer, logger)
                if signal:
                    # Liquidity filter for single TF
                    lz_ok = True
                    lz_context = {}
                    try:
                        if getattr(config, "LIQUIDITY_FILTER_ENABLED", True):
                            lz = LiquidityZones(logger)
                            lookback = int(getattr(config, "LZ_LOOKBACK_BARS", 200))
                            bars = analyzer.get_historical_data(limit=lookback)
                            lz_ok, lz_context = lz.evaluate(direction=signal["direction"], bars=bars)
                    except Exception as e:
                        logger.error(f"LZ filter error: {e}")
                        lz_ok = True
                    if not lz_ok:
                        logger.info("Liquidity filter blocked single-TF signal")
                        raise Exception("Liquidity filter blocked")
                    signal["lz_context"] = lz_context
                    # Build a key to avoid duplicates
                    wp = signal.get("wave_points", [])
                    pivot_fingerprint = "-".join([f"{p['type']}@{int(round(p['price']*1e6))}" for p in wp])
                    sig_key = f"{config.PAIR}|{config.TIMEFRAME}|{signal['direction']}|{pivot_fingerprint}|{signal['quality']}"
                    now_ts = time.time()

                    allowed = True
                    if last_signal_key == sig_key and last_signal_time is not None:
                        if (now_ts - last_signal_time) < DEDUPE_SECONDS:
                            allowed = False

                    if allowed:
                        text = format_signal_message(config.PAIR, config.TIMEFRAME, signal)
                        signal_time = str(int(signal["time"]))
                        keyboard = create_signal_keyboard(signal_time)
                        send_telegram_message(bot, config.TELEGRAM_CHAT_ID, text, logger, reply_markup=keyboard)
                        last_signal_key = sig_key
                        last_signal_time = now_ts
                        logger.info(f"Signal sent: {sig_key}")
                        _write_history({
                            "time": int(signal["time"]),
                            "pair": config.PAIR,
                            "timeframe": config.TIMEFRAME,
                            "direction": signal["direction"],
                            "quality": signal["quality"],
                            "entry": signal["entry"],
                            "tp1": signal["tp1"], "tp2": signal["tp2"], "tp3": signal["tp3"],
                            "sl": signal["sl"], "status": "opened",
                            "tp1_hit": "0", "tp2_hit": "0", "tp3_hit": "0", "sl_hit": "0",
                            "close_price": "", "close_time": "",
                            "partial_close_tp1": "0", "sl_moved_to_breakeven": "0", "new_sl": "",
                            "user_action": ""
                        }, logger)
                        if getattr(config, "CANCEL_ON_WAVE4_BREACH", True) and signal.get("wave4_price") is not None:
                            active_signals.append({"direction": signal["direction"], "wave4": float(signal["wave4_price"]), "tf": config.TIMEFRAME})
                else:
                    logger.info("No valid Elliott pattern found")
                    # store last single-TF reason for status
                    last_reasons_snapshot = {str(getattr(config, "TIMEFRAME", "tf")): {"reason": getattr(analyzer, "last_reject_reason", "unknown"),
                                                                                       "details": getattr(analyzer, "last_reject_details", {})}}
                    reason_counters[f"single:{getattr(analyzer,'last_reject_reason','unknown')}"] += 1

            # Periodic status to Telegram (non-spam)
            if status_enabled:
                now_ts = time.time()
                if (now_ts - status_last_sent) >= status_interval:
                    status_last_sent = now_ts
                    lines = []
                    lines.append("📊 <b>Статус бота</b>")
                    lines.append(f"• Пара: <b>{config.PAIR}</b>")
                    if getattr(config, "ENABLE_MULTI_TF", False):
                        lines.append(f"• Режим: <b>MTF</b> ({', '.join(getattr(config, 'MULTI_TIMEFRAMES', []))})")
                    else:
                        lines.append(f"• Таймфрейм: <b>{config.TIMEFRAME}</b>")
                    lines.append(f"• Период опроса: <b>{sleep_secs}s</b>")

                    if reason_counters:
                        lines.append("• Причины (за интервал):")
                        def _reason_ru_key(key: str) -> str:
                            # key examples:
                            #  - "15m:no_wave"
                            #  - "mtf:deduped"
                            #  - "liquidity_bonus"
                            try:
                                if ":" in key:
                                    a, b = key.split(":", 1)
                                    # map common reasons
                                    m = {
                                        "no_wave": "нет паттерна (1-2-3-4-5)",
                                        "market_quality": "фильтр рынка",
                                        "not_enough_pivots": "мало пивотов",
                                        "not_enough_bars": "мало свечей",
                                        "avax_bad_time": "вне торгового времени",
                                        "sweep_setup": "сетап свип+возврат",
                                        "ok": "ок",
                                        "deduped": "антидубль",
                                        "no_entry_signal": "нет входного сигнала",
                                        "trend_blocked": "запрещено трендом",
                                        "below_quality": "ниже порога качества",
                                        "against_trend_penalty": "штраф против тренда",
                                    }
                                    if a == "mtf":
                                        return f"MTF:{m.get(b,b)}"
                                    return f"{a}:{m.get(b,b)}"
                                # non tf-scoped keys
                                m2 = {
                                    "liquidity_bonus": "бонус ликвидности",
                                    "liquidity_penalty": "штраф ликвидности",
                                    "liquidity_blocked": "заблокировано ликвидностью",
                                }
                                return m2.get(key, key)
                            except Exception:
                                return key

                        for k, v in reason_counters.most_common(6):
                            lines.append(f"  - {_reason_ru_key(k)}: {v}")

                    # Extra summary (hourly)
                    if trend_counters:
                        parts = []
                        for k, v in trend_counters.most_common():
                            t = k.split(":", 1)[1]
                            t_ru = {"UP": "ВВЕРХ", "DOWN": "ВНИЗ", "FLAT": "ФЛЭТ"}.get(t, t)
                            parts.append(f"{t_ru}={v}")
                        if parts:
                            lines.append("• Тренд (1h, за интервал): " + " | ".join(parts))
                    if setup_counters:
                        parts = []
                        for k, v in setup_counters.most_common():
                            s = k.split(":", 1)[1]
                            s_ru = {"SWEEP": "СВИП+ВОЗВРАТ", "ELLIOTT": "ЭЛЛИОТТ"}.get(s, s)
                            parts.append(f"{s_ru}={v}")
                        if parts:
                            lines.append("• Сетапы (отправлено): " + " | ".join(parts))
                    if sent_quality_count > 0:
                        avg_q = sent_quality_sum / float(sent_quality_count)
                        lines.append(f"• Среднее качество (отправлено): {avg_q:.1f}% (n={sent_quality_count})")
                    # Penalties summary
                    pen_tr = int(reason_counters.get("mtf:against_trend_penalty", 0))
                    pen_lz = int(reason_counters.get("liquidity_penalty", 0))
                    if pen_tr or pen_lz:
                        lines.append(f"• Штрафы: Тренд={pen_tr} | Ликвидность={pen_lz}")

                    if status_include_per_tf and last_reasons_snapshot:
                        lines.append("• Последняя проверка:")
                        for tf in sorted(last_reasons_snapshot.keys(), key=_tf_to_minutes):
                            lines.append("  - " + _format_reason(tf, last_reasons_snapshot[tf]))

                    msg = "\n".join(lines[:status_max_lines])
                    send_telegram_message(bot, config.TELEGRAM_CHAT_ID, msg, logger)
                    logger.info("Status message sent to Telegram")
                    reason_counters.clear()
                    setup_counters.clear()
                    trend_counters.clear()
                    sent_quality_sum = 0.0
                    sent_quality_count = 0
            # Cancellation check based on wave4 breach
            if getattr(config, "CANCEL_ON_WAVE4_BREACH", True) and active_signals:
                try:
                    # Use 15m if present, else current TIMEFRAME
                    check_tf = "15m" if getattr(config, "ENABLE_MULTI_TF", False) else config.TIMEFRAME
                    check_an = ElliottWaveAnalyzer(logger=logger, timeframe=check_tf)
                    bars = check_an.get_historical_data(limit=5)
                    if bars:
                        current_close = bars[-1]["close"]
                        still_active = []
                        for s in active_signals:
                            wave4 = s["wave4"]
                            if s["direction"] == "BUY" and current_close < wave4:
                                send_telegram_message(bot, config.TELEGRAM_CHAT_ID, "❌ СИГНАЛ ОТМЕНЕН! Цена пробила уровень волны 4.", logger)
                                _write_history({"time": int(time.time()*1000), "pair": config.PAIR, "timeframe": s["tf"], "direction": s["direction"], "status": "cancelled"}, logger)
                            elif s["direction"] == "SELL" and current_close > wave4:
                                send_telegram_message(bot, config.TELEGRAM_CHAT_ID, "❌ СИГНАЛ ОТМЕНЕН! Цена пробила уровень волны 4.", logger)
                                _write_history({"time": int(time.time()*1000), "pair": config.PAIR, "timeframe": s["tf"], "direction": s["direction"], "status": "cancelled"}, logger)
                            else:
                                still_active.append(s)
                        active_signals = still_active
                except Exception as e:
                    logger.error(f"Cancel check error: {e}")
        except Exception as e:
            logger.error(f"Main loop error: {e}")

        # Периодическая проверка обновления модели (раз в час)
        try:
            _try_update_prob_model()
        except Exception:
            pass  # Игнорируем ошибки автообновления
        
        # Проверка TP/SL для открытых сигналов (каждую итерацию)
        try:
            _check_tp_sl_signals(logger, bot, config.TELEGRAM_CHAT_ID)
        except Exception as e:
            logger.error(f"TP/SL check error: {e}")

        time.sleep(sleep_secs)


if __name__ == "__main__":
    main()
