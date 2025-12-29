# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import math
from typing import List, Dict, Optional, Tuple

import ccxt  # type: ignore

try:
    # Local config import
    import elliott_wave_bot.config as config
except Exception:
    # Fallback if run from inside the same folder
    import config  # type: ignore


class ElliottWaveAnalyzer:
    # Общий exchange и кэш ETH-тренда для снижения нагрузки на Binance
    _shared_exchange = None
    _eth_trend_cache: Dict[str, Tuple[str, float]] = {}

    def __init__(self, logger, timeframe: Optional[str] = None, exchange=None):
        self.logger = logger
        if exchange is not None:
            self.exchange = exchange
        else:
            if ElliottWaveAnalyzer._shared_exchange is None:
                ElliottWaveAnalyzer._shared_exchange = ccxt.binance({
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                    "timeout": 20000,
                })
            self.exchange = ElliottWaveAnalyzer._shared_exchange

        self.pair = config.PAIR
        self.timeframe = timeframe if timeframe else config.TIMEFRAME
        self.pivot_len = int(config.PIVOT_LEN)
        self.min_wave_size_pct = float(config.MIN_WAVE_SIZE)
        self.quality_threshold = int(config.QUALITY_THRESHOLD)
        self.strict_rules = bool(config.STRICT_RULES)
        self.confirm_signals = bool(config.CONFIRM_SIGNALS)
        self.confirm_pivot = bool(config.CONFIRM_PIVOT)
        self.max_distance = int(config.MAX_DISTANCE)

        self.use_atr_targets = bool(config.USE_ATR_TARGETS)
        self.atr_len = int(config.ATR_LEN)
        self.atr_sl_mult = float(config.ATR_SL_MULT)
        self.atr_tp1_mult = float(config.ATR_TP1_MULT)
        self.atr_tp2_mult = float(config.ATR_TP2_MULT)
        self.atr_tp3_mult = float(config.ATR_TP3_MULT)
        self.use_dynamic_min_wave = bool(getattr(config, "USE_DYNAMIC_MIN_WAVE_SIZE", False))
        self.dynamic_min_wave_atr_mult = float(getattr(config, "DYNAMIC_MIN_WAVE_ATR_MULT", 1.5))
        self.min_volume_ratio = float(getattr(config, "MIN_VOLUME_RATIO", 0.7))
        self.volume_recent = int(getattr(config, "VOLUME_RECENT", 5))
        self.volume_window = int(getattr(config, "VOLUME_WINDOW", 50))
        self.max_spread_pct = float(getattr(config, "MAX_SPREAD_PCT", 2.0))
        self.avax_settings = getattr(config, "AVAX_SETTINGS", None)
        self.last_reject_reason: str = "init"
        self.last_reject_details: Dict = {}

    def _reject(self, reason: str, details: Optional[Dict] = None) -> None:
        self.last_reject_reason = reason
        self.last_reject_details = details or {}

    # ------------ Public API ------------
    def get_historical_data(self, limit: int = 500) -> List[Dict]:
        # Попытка получить данные из кэша
        try:
            from utils_cache import get_cache
            cache = get_cache()
            cached_data = cache.get(self.pair, self.timeframe, limit)
            if cached_data is not None:
                return cached_data
        except Exception:
            # Если кэш недоступен, продолжаем без него
            pass
        
        symbol = self._to_ccxt_symbol(self.pair)
        # load_markets() один раз, иначе при каждом новом экземпляре ccxt может дергать exchangeInfo
        try:
            if not getattr(self.exchange, "markets", None):
                self.exchange.load_markets()
        except Exception:
            pass
        candles = self.exchange.fetch_ohlcv(symbol, timeframe=self.timeframe, limit=limit)
        if not candles:
            self._reject("no_candles")
            return []
        # Convert to dicts
        bars = [{"time": c[0], "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in candles]
        # Optionally ensure last bar is confirmed (closed)
        if self.confirm_signals:
            now_ms = int(time.time() * 1000)
            tf_ms = self._timeframe_to_ms(self.timeframe)
            if len(bars) >= 1 and (now_ms - bars[-1]["time"]) < tf_ms:
                bars = bars[:-1]
        
        # Сохраняем в кэш
        try:
            from utils_cache import get_cache
            cache = get_cache()
            cache.set(self.pair, self.timeframe, limit, bars)
        except Exception:
            # Если кэш недоступен, продолжаем без него
            pass
        
        return bars

    def find_pivots(self, bars: List[Dict]) -> List[Dict]:
        if len(bars) < (2 * self.pivot_len + 1):
            return []

        raw_pivots: List[Dict] = []
        for i in range(self.pivot_len, len(bars) - self.pivot_len):
            is_high = True
            is_low = True
            price_i_high = bars[i]["high"]
            price_i_low = bars[i]["low"]
            for j in range(i - self.pivot_len, i + self.pivot_len + 1):
                if bars[j]["high"] > price_i_high:
                    is_high = False
                if bars[j]["low"] < price_i_low:
                    is_low = False
                if not is_high and not is_low:
                    break
            if is_high:
                raw_pivots.append({"index": i, "time": bars[i]["time"], "price": price_i_high, "type": "high"})
            if is_low:
                raw_pivots.append({"index": i, "time": bars[i]["time"], "price": price_i_low, "type": "low"})

        if not raw_pivots:
            return []

        # Sort by index (time)
        raw_pivots.sort(key=lambda p: p["index"])

        # Build ZigZag with alternation and min wave size filtering
        zigzag: List[Dict] = []
        for p in raw_pivots:
            if not zigzag:
                zigzag.append(p)
                continue
            last = zigzag[-1]
            if p["type"] == last["type"]:
                # Replace if more extreme in same direction
                if p["type"] == "high" and p["price"] > last["price"]:
                    zigzag[-1] = p
                elif p["type"] == "low" and p["price"] < last["price"]:
                    zigzag[-1] = p
            else:
                # Only add if move is large enough
                change_pct = abs((p["price"] - last["price"]) / last["price"]) * 100.0
                if change_pct >= self.min_wave_size_pct:
                    zigzag.append(p)

        if self.confirm_pivot and len(zigzag) > 0:
            # Ensure last pivot is confirmed by having at least pivot_len bars after it
            last_idx = zigzag[-1]["index"]
            if (len(bars) - 1) - last_idx < self.pivot_len:
                # Drop the last unconfirmed pivot
                zigzag = zigzag[:-1]

        return zigzag

    def get_signal(self, bars: List[Dict]) -> Optional[Dict]:
        if len(bars) < max(100, 2 * self.atr_len + 10):
            self._reject("not_enough_bars", {"bars": len(bars)})
            return None
        # Optional market quality filters
        ok, details = self._market_quality_ok(bars)
        if not ok:
            self._reject("market_quality", details)
            return None

        # Optionally adjust min wave size using ATR
        if self.use_dynamic_min_wave:
            dyn_min = self._dynamic_min_wave_pct(bars)
            if dyn_min is not None and dyn_min > 0:
                old = self.min_wave_size_pct
                self.min_wave_size_pct = dyn_min
                pivots = self.find_pivots(bars)
                # restore for safety
                self.min_wave_size_pct = old
            else:
                pivots = self.find_pivots(bars)
        else:
            pivots = self.find_pivots(bars)
        if len(pivots) < 6:
            self._reject("not_enough_pivots", {"pivots": len(pivots)})
            return None

        atr = self._compute_atr(bars, self.atr_len)
        last_atr = atr[-1] if atr else None
        result = self._check_wave(pivots, bars, last_atr)
        if not result:
            self._reject("no_wave")
            return None
        # AVAX-specific context and adjustments
        if self._is_avax_pair():
            # Time filter
            if not self._is_good_time_for_avax():
                self._reject("avax_bad_time")
                return None
            # Unlocks filter
            if self._should_block_unlock_window():
                self._reject("avax_unlock_window")
                return None
            # ETH correlation adjustment
            delta_quality, eth_trend = self._eth_alignment_adjustment(direction=result["direction"])
            result["quality"] = int(max(0, min(100, result["quality"] + delta_quality)))
            # Category
            result["category"] = self._category_from_quality(result["quality"])
            # Context
            result["context"] = self._build_avax_context(bars, eth_trend)
        else:
            result["category"] = self._category_from_quality(result["quality"])
        self._reject("ok")
        return result

    # ------------ Internals ------------
    def _check_wave(self, pivots: List[Dict], bars: List[Dict], last_atr: Optional[float]) -> Optional[Dict]:
        """
        Try to detect a 1-2-3-4-5 impulse using last 6 alternating pivots.
        Rules and scoring per spec.
        """
        best: Optional[Dict] = None
        tf_ms = self._timeframe_to_ms(self.timeframe)
        last_bar_index = len(bars) - 1

        # Scan windows of 6 pivots for a completed 5th wave
        for i in range(len(pivots) - 5):
            window = pivots[i:i + 6]
            types = [p["type"] for p in window]
            prices = [p["price"] for p in window]
            idxs = [p["index"] for p in window]

            # Require alternation
            if any(types[j] == types[j + 1] for j in range(5)):
                continue

            # Bullish candidate: low-high-low-high-low-high
            if types == ["low", "high", "low", "high", "low", "high"]:
                # waves: 1:0->1, 2:1->2, 3:2->3, 4:3->4, 5:4->5
                w1 = prices[1] - prices[0]
                w2 = prices[1] - prices[2]
                w3 = prices[3] - prices[2]
                w4 = prices[3] - prices[4]
                w5 = prices[5] - prices[4]
                if min(w1, w3, w5) <= 0 or min(w2, w4) <= 0:
                    continue

                if not self._basic_rules_ok(is_bull=True, w1=w1, w2=w2, w3=w3, w4=w4, w5=w5, p1=prices[1], p4=prices[4], p2=prices[2], p0=prices[0]):
                    continue
                if self.strict_rules and not self._strict_rules_ok(is_bull=True, w1=w1, w2=w2, w3=w3, w4=w4, p1=prices[1], p4=prices[4], p2=prices[2], p0=prices[0], p5=prices[5]):
                    continue

                # Max distance in bars from last pivot to current
                if (last_bar_index - idxs[-1]) > self.max_distance:
                    continue

                quality = self._quality_score(is_bull=True, w1=w1, w2=w2, w3=w3, w4=w4, w5=w5)
                if self.strict_rules:
                    quality += 5

                if quality < self.quality_threshold:
                    continue

                # Targets and SL
                entry = bars[-1]["close"]
                targets, sl = self._targets_and_sl(is_bull=True, entry=entry, w1=w1, p4=prices[4], last_atr=last_atr)

                candidate = {
                    "direction": "BUY",
                    "quality": int(max(0, min(100, round(quality)))),
                    "entry": entry,
                    "tp1": targets[0],
                    "tp2": targets[1],
                    "tp3": targets[2],
                    "sl": sl,
                    "wave_points": [{"index": idxs[j], "price": prices[j], "type": types[j]} for j in range(6)],
                    "wave4_price": prices[4],
                    "time": bars[-1]["time"],
                }
                best = candidate

            # Bearish candidate: high-low-high-low-high-low
            if types == ["high", "low", "high", "low", "high", "low"]:
                w1 = prices[0] - prices[1]
                w2 = prices[2] - prices[1]
                w3 = prices[2] - prices[3]
                w4 = prices[4] - prices[3]
                w5 = prices[4] - prices[5]
                if min(w1, w3, w5) <= 0 or min(w2, w4) <= 0:
                    continue

                if not self._basic_rules_ok(is_bull=False, w1=w1, w2=w2, w3=w3, w4=w4, w5=w5, p1=prices[1], p4=prices[4], p2=prices[2], p0=prices[0]):
                    continue
                if self.strict_rules and not self._strict_rules_ok(is_bull=False, w1=w1, w2=w2, w3=w3, w4=w4, p1=prices[1], p4=prices[4], p2=prices[2], p0=prices[0], p5=prices[5]):
                    continue

                if (last_bar_index - idxs[-1]) > self.max_distance:
                    continue

                quality = self._quality_score(is_bull=False, w1=w1, w2=w2, w3=w3, w4=w4, w5=w5)
                if self.strict_rules:
                    quality += 5
                if quality < self.quality_threshold:
                    continue

                entry = bars[-1]["close"]
                targets, sl = self._targets_and_sl(is_bull=False, entry=entry, w1=w1, p4=prices[4], last_atr=last_atr)

                candidate = {
                    "direction": "SELL",
                    "quality": int(max(0, min(100, round(quality)))),
                    "entry": entry,
                    "tp1": targets[0],
                    "tp2": targets[1],
                    "tp3": targets[2],
                    "sl": sl,
                    "wave_points": [{"index": idxs[j], "price": prices[j], "type": types[j]} for j in range(6)],
                    "wave4_price": prices[4],
                    "time": bars[-1]["time"],
                }
                best = candidate

        return best

    # ------------ Helper methods ------------
    def _basic_rules_ok(self, is_bull: bool, w1: float, w2: float, w3: float, w4: float, w5: float,
                        p1: float, p4: float, p2: float, p0: float) -> bool:
        # Wave 2 no more than 120% of wave 1
        if w2 > 1.2 * w1:
            return False
        # Wave 3 not shorter than 80% of wave 1
        if w3 < 0.8 * w1:
            return False
        # Wave 5 not "returns too much": require it to be at least 30% of wave1
        if w5 < 0.3 * w1:
            return False
        return True

    def _strict_rules_ok(self, is_bull: bool, w1: float, w2: float, w3: float, w4: float,
                         p1: float, p4: float, p2: float, p0: float, p5: float) -> bool:
        # Wave 2 <= 100% of wave 1 (no full retrace)
        if w2 > w1:
            return False
        # Wave 3 not shorter than waves 1 and 5
        w5_len = abs(p5 - p4)
        if w3 < w1 or w3 < w5_len:
            return False
        # Wave 4 does not enter wave 1 price area
        if is_bull:
            # wave1: p0->p1, wave4 low should be above wave1 top
            if p4 <= p1:
                return False
        else:
            # bearish: wave4 high should be below wave1 bottom
            if p4 >= p1:
                return False
        return True

    def _quality_score(self, is_bull: bool, w1: float, w2: float, w3: float, w4: float, w5: float) -> float:
        score = 40.0
        # retracement ratio of wave 2 relative to wave 1
        r2 = w2 / w1 if w1 > 0 else 0.0
        if 0.30 <= r2 <= 0.70:
            score += 15
        if 0.382 <= r2 <= 0.618:
            score += 10
        # wave 3 extensions
        if w3 >= 1.30 * w1:
            score += 15
        if w3 >= 1.618 * w1:
            score += 10
        # wave 3 greater than waves 1 and 5 (interpreting spec)
        if w3 > w1 and w3 > w5:
            score += 10
        return max(0.0, min(100.0, score))

    def _targets_and_sl(self, is_bull: bool, entry: float, w1: float, p4: float, last_atr: Optional[float]) -> Tuple[Tuple[float, float, float], float]:
        if self.use_atr_targets and last_atr and last_atr > 0:
            tp1 = entry + (self.atr_tp1_mult * last_atr) * (1 if is_bull else -1)
            tp2 = entry + (self.atr_tp2_mult * last_atr) * (1 if is_bull else -1)
            tp3 = entry + (self.atr_tp3_mult * last_atr) * (1 if is_bull else -1)
            sl = entry - (self.atr_sl_mult * last_atr) * (1 if is_bull else -1)
            return (round(tp1, 6), round(tp2, 6), round(tp3, 6)), round(sl, 6)
        else:
            if self._is_avax_pair():
                # AVAX percent-based targets
                if is_bull:
                    tp1 = entry * 1.10
                    tp2 = entry * 1.20
                    tp3 = entry * 1.35
                    # SL = min(8% ниже entry, entry - ATR * 2.8)
                    atr_stop = (last_atr * float(self.avax_settings.get("stop_loss_atr_mult", 2.8))) if last_atr else 0.0
                    sl = min(entry * 0.92, entry - atr_stop)
                else:
                    tp1 = entry * 0.90
                    tp2 = entry * 0.80
                    tp3 = entry * 0.65
                    atr_stop = (last_atr * float(self.avax_settings.get("stop_loss_atr_mult", 2.8))) if last_atr else 0.0
                    sl = max(entry * 1.08, entry + atr_stop)
            else:
                # Fib-style targets based on wave1 length from current price
                tp1 = entry + (0.618 * w1) * (1 if is_bull else -1)
                tp2 = entry + (1.000 * w1) * (1 if is_bull else -1)
                tp3 = entry + (1.618 * w1) * (1 if is_bull else -1)
                # SL 2% from wave4 pivot, with guard to keep SL on the correct side of entry
                if is_bull:
                    sl = p4 * (1.0 - 0.02)
                    if sl >= entry:
                        sl = entry * (1.0 - 0.02)
                else:
                    sl = p4 * (1.0 + 0.02)
                    if sl <= entry:
                        sl = entry * (1.0 + 0.02)
            return (round(tp1, 6), round(tp2, 6), round(tp3, 6)), round(sl, 6)

    def _compute_atr(self, bars: List[Dict], period: int) -> List[float]:
        if len(bars) < period + 1:
            return []
        trs: List[float] = []
        for i in range(1, len(bars)):
            high = bars[i]["high"]
            low = bars[i]["low"]
            prev_close = bars[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        atr: List[float] = []
        # Simple moving average ATR
        for i in range(len(trs)):
            if i + 1 < period:
                atr.append(0.0)
            else:
                window = trs[i + 1 - period:i + 1]
                atr.append(sum(window) / float(period))
        return atr

    def _to_ccxt_symbol(self, pair: str) -> str:
        # Convert "AVAXUSDT" -> "AVAX/USDT"
        if "/" in pair:
            return pair
        # Try split ending quote assets
        known_quotes = ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB", "EUR", "TRY", "TUSD", "FDUSD"]
        for q in known_quotes:
            if pair.endswith(q):
                base = pair[:-len(q)]
                return f"{base}/{q}"
        # Fallback: insert slash before last 4 chars
        return f"{pair[:-4]}/{pair[-4:]}"

    def _timeframe_to_ms(self, tf: str) -> int:
        num = int(''.join([ch for ch in tf if ch.isdigit()]) or "1")
        unit = ''.join([ch for ch in tf if ch.isalpha()]) or "m"
        if unit == "m":
            return num * 60 * 1000
        if unit == "h":
            return num * 60 * 60 * 1000
        if unit == "d":
            return num * 24 * 60 * 60 * 1000
        return num * 60 * 1000

    def _market_quality_ok(self, bars: List[Dict]) -> Tuple[bool, Dict]:
        # Volume filter
        if len(bars) < max(self.volume_window, self.volume_recent) + 1:
            return True, {"note": "insufficient_for_quality_window"}
        recent = bars[-self.volume_recent:]
        window = bars[-self.volume_window:]
        avg_recent_vol = sum(b["volume"] for b in recent) / float(self.volume_recent)
        avg_window_vol = sum(b["volume"] for b in window) / float(self.volume_window)
        if avg_window_vol > 0 and (avg_recent_vol / avg_window_vol) < self.min_volume_ratio:
            return False, {"volume_ratio": float(avg_recent_vol / avg_window_vol), "min_ratio": self.min_volume_ratio}
        # AVAX: абсолютный объем в USDT (quote volume) по последним volume_recent барам
        try:
            if self._is_avax_pair() and self.avax_settings:
                min_qv = float(self.avax_settings.get("min_volume_usdt", 0))
                if min_qv > 0:
                    quote_vol = sum(float(b["close"]) * float(b["volume"]) for b in recent)
                    if quote_vol < min_qv:
                        return False, {"quote_vol_usdt": float(quote_vol), "min_quote_vol_usdt": float(min_qv)}
        except Exception:
            pass
        # Spread filter on the last bar
        last = bars[-1]
        spread_pct = (last["high"] - last["low"]) / max(1e-12, last["close"]) * 100.0
        if spread_pct > self.max_spread_pct:
            return False, {"spread_pct": float(spread_pct), "max_spread_pct": self.max_spread_pct}
        return True, {}

    def _dynamic_min_wave_pct(self, bars: List[Dict]) -> Optional[float]:
        atrs = self._compute_atr(bars, self.atr_len)
        if not atrs:
            return None
        last_atr = atrs[-1]
        last_close = bars[-1]["close"]
        if last_close <= 0:
            return None
        pct = (last_atr * self.dynamic_min_wave_atr_mult) / last_close * 100.0
        return pct

    # ---------- AVAX helpers ----------
    def _is_avax_pair(self) -> bool:
        sym = self._to_ccxt_symbol(self.pair).upper()
        return sym.startswith("AVAX/")

    def _determine_trend(self, bars: List[Dict]) -> str:
        if len(bars) < 20:
            return "FLAT"
        close = [b["close"] for b in bars]
        ma_fast = sum(close[-10:]) / 10.0
        ma_slow = sum(close[-20:]) / 20.0
        if ma_fast > ma_slow * 1.002:
            return "UP"
        if ma_fast < ma_slow * 0.998:
            return "DOWN"
        return "FLAT"

    def _eth_alignment_adjustment(self, direction: str) -> Tuple[int, str]:
        try:
            tf = self.timeframe
            now = time.time()
            cached = ElliottWaveAnalyzer._eth_trend_cache.get(tf)
            if cached and (now - cached[1]) < 300:
                trend = cached[0]
            else:
                try:
                    if not getattr(self.exchange, "markets", None):
                        self.exchange.load_markets()
                except Exception:
                    pass
                eth_candles = self.exchange.fetch_ohlcv("ETH/USDT", timeframe=tf, limit=200)
                eth_bars = [{"time": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]} for c in eth_candles]
                trend = self._determine_trend(eth_bars)
                ElliottWaveAnalyzer._eth_trend_cache[tf] = (trend, now)
            if direction == "BUY" and trend == "DOWN":
                return -30, trend
            if direction == "BUY" and trend == "UP":
                return +20, trend
            if direction == "SELL" and trend == "UP":
                return -30, trend
            if direction == "SELL" and trend == "DOWN":
                return +20, trend
            return 0, trend
        except Exception:
            return 0, "UNKNOWN"

    def _should_block_unlock_window(self) -> bool:
        try:
            if not self.avax_settings or not self.avax_settings.get("check_token_unlocks", True):
                return False
            upcoming_unlocks = ["2024-09-22", "2024-12-22", "2025-03-22"]
            now_days = time.time() / 86400.0
            for d in upcoming_unlocks:
                # very simple date parse (YYYY-MM-DD)
                y, m, d2 = [int(x) for x in d.split("-")]
                import datetime as _dt
                target = _dt.datetime(y, m, d2, 0, 0, 0, tzinfo=_dt.timezone.utc).timestamp() / 86400.0
                if abs(target - now_days) <= 7:
                    return True
            return False
        except Exception:
            return False

    def _is_good_time_for_avax(self) -> bool:
        try:
            import datetime as _dt
            hour_utc = _dt.datetime.now(tz=_dt.timezone.utc).hour
            avoid = (self.avax_settings or {}).get("avoid_hours", [(0, 8)])
            for a, b in avoid:
                if a <= hour_utc < b:
                    return False
            # Weekend filter
            if (self.avax_settings or {}).get("avoid_weekends", False):
                wd = _dt.datetime.now(tz=_dt.timezone.utc).weekday()
                if wd >= 5:
                    return False
            return True
        except Exception:
            return True

    def _category_from_quality(self, q: int) -> str:
        if q >= getattr(config, "CATEGORY_A_MIN", 85):
            return "A"
        if q >= getattr(config, "CATEGORY_B_MIN", 70):
            return "B"
        if q >= getattr(config, "CATEGORY_C_MIN", 60):
            return "C"
        return "D"

    def _build_avax_context(self, bars: List[Dict], eth_trend: str) -> Dict:
        # Approx recent quote volume (USDT)
        recent = bars[-self.volume_recent:] if len(bars) >= self.volume_recent else bars
        vol_usdt = sum(b["close"] * b["volume"] for b in recent)
        # Session hint
        import datetime as _dt
        hour_utc = _dt.datetime.now(tz=_dt.timezone.utc).hour
        session = "NY" if 13 <= hour_utc <= 21 else ("EU" if 7 <= hour_utc < 13 else "ASIA")
        # Days to next unlock (coarse)
        days_to_unlock = "-"
        try:
            upcoming_unlocks = ["2024-12-22", "2025-03-22"]
            now = _dt.datetime.now(tz=_dt.timezone.utc)
            diffs = []
            for ds in upcoming_unlocks:
                y, m, d2 = [int(x) for x in ds.split("-")]
                t = _dt.datetime(y, m, d2, tzinfo=_dt.timezone.utc)
                diffs.append((t - now).days)
            if diffs:
                # choose nearest future
                future = [d for d in diffs if d >= 0]
                if future:
                    days_to_unlock = min(future)
        except Exception:
            pass
        return {
            "eth_trend": eth_trend,
            "recent_volume_usdt": int(vol_usdt),
            "session": session,
            "days_to_unlock": days_to_unlock,
        }


