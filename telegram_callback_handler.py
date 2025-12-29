#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обработчик callback от кнопок Telegram
Запускается отдельно для обработки нажатий на кнопки
"""

import os
import sys
import csv
import logging
from pathlib import Path
from typing import Dict

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
    _HAS_TELEGRAM_LIB = True
except Exception:
    print("❌ Требуется python-telegram-bot для обработки callback")
    print("Установите: pip install python-telegram-bot")
    sys.exit(1)

try:
    import elliott_wave_bot.config as config
except Exception:
    import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def update_signal_action(signal_time: str, action: str) -> bool:
    """Обновить действие пользователя для сигнала"""
    try:
        base_dir = Path(__file__).parent
        csv_path = base_dir / str(getattr(config, "HISTORY_CSV", "signals_history.csv"))
        
        if not csv_path.exists():
            return False
        
        # Читаем все сигналы
        signals = []
        with csv_path.open('r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                signals.append(row)
        
        # Обновляем нужный сигнал
        updated = False
        for signal in signals:
            if signal.get('time', '').strip() == signal_time:
                signal['user_action'] = action
                updated = True
                break
        
        if not updated:
            return False
        
        # Сохраняем обратно
        fieldnames = ["time","pair","timeframe","direction","quality","entry","tp1","tp2","tp3","sl","status",
                     "tp1_hit","tp2_hit","tp3_hit","sl_hit","close_price","close_time",
                     "partial_close_tp1","sl_moved_to_breakeven","new_sl","user_action"]
        
        with csv_path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for signal in signals:
                # Заполняем отсутствующие поля
                for field in fieldnames:
                    if field not in signal:
                        signal[field] = ""
                writer.writerow(signal)
        
        return True
    except Exception as e:
        logger.error(f"Failed to update signal action: {e}")
        return False


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"Callback received: {callback_data}")
    
    if callback_data.startswith("in_position_"):
        signal_time = callback_data.replace("in_position_", "")
        if update_signal_action(signal_time, "in_position"):
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ Сигнал добавлен в отслеживание. Обновления TP/SL будут приходить.")
        else:
            await query.message.reply_text("❌ Ошибка обновления сигнала")
    
    elif callback_data.startswith("skip_"):
        signal_time = callback_data.replace("skip_", "")
        if update_signal_action(signal_time, "skip"):
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("⏭️ Сигнал пропущен. Обновления не будут приходить.")
        else:
            await query.message.reply_text("❌ Ошибка обновления сигнала")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    await update.message.reply_text(
        "🤖 Бот #2 - Обработчик кнопок\n\n"
        "Нажимайте кнопки под сигналами:\n"
        "✅ В позиции - получать обновления TP/SL\n"
        "⏭️ Пропустить - не получать обновления"
    )


def main():
    """Запуск обработчика callback"""
    token = config.TELEGRAM_TOKEN
    if not token:
        logger.error("TELEGRAM_TOKEN не установлен")
        sys.exit(1)
    
    application = Application.builder().token(token).build()
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Запуск обработчика callback...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()



