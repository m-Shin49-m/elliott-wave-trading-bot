# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List, Tuple, Optional

try:
    import elliott_wave_bot.config as config
except Exception:
    import config  # type: ignore


class LiquidityZones:
    def __init__(self, logger):
        self.logger = logger
        self.lookback = int(getattr(config, "LZ_LOOKBACK_BARS", 200))
        self.swing_len = int(getattr(config, "LZ_SWING_LEN", 3))
        self.equal_tol_pct = float(getattr(config, "LZ_EQUAL_TOL_PCT", 0.10))
        self.min_touches = int(getattr(config, "LZ_MIN_TOUCHES", 2))
        self.sweep_retrace_pct = float(getattr(config, "LZ_SWEEP_RETRACE_PCT", 0.20))
        self.vol_spike_mult = float(getattr(config, "LZ_VOLUME_SPIKE_MULT", 1.8))
        self.require_sweep = bool(getattr(config, "LZ_REQUIRE_SWEEP", True))
        self.require_volume_spike = bool(getattr(config, "LZ_REQUIRE_VOLUME_SPIKE", False))

    def evaluate(self, direction: str, bars: List[Dict]) -> Tuple[bool, Dict]:
        """
        Returns (passed, context)
        Context includes: 'swept': 'buy'/'sell'/None, 'volume_spike': bool,
        'level_price': float or None, 'entry_tf': optional
        """
        ctx: Dict = {"swept": None, "volume_spike": False, "level_price": None}
        if len(bars) < max(50, self.lookback):
            return True, ctx

        recent = bars[-self.lookback:]
        # volume spike on last bar
        vol_ok = self._volume_spike_ok(recent)
        ctx["volume_spike"] = vol_ok

        # equal highs/lows levels
        swing_highs, swing_lows = self._swings(recent, self.swing_len)
        equal_highs = self._cluster_levels(swing_highs, is_high=True)
        equal_lows = self._cluster_levels(swing_lows, is_high=False)

        # sweep detection on last closed bar
        last = recent[-1]
        swept_side, level_price = self._detect_sweep(last, equal_highs, equal_lows)
        ctx["swept"] = swept_side
        ctx["level_price"] = level_price

        # decision by direction
        passed = True
        if self.require_sweep:
            if direction == "BUY" and swept_side != "sell":  # want liquidity taken below
                passed = False
            if direction == "SELL" and swept_side != "buy":  # want liquidity taken above
                passed = False
        if self.require_volume_spike and not vol_ok:
            passed = False
        return passed, ctx

    def _volume_spike_ok(self, bars: List[Dict]) -> bool:
        if len(bars) < 25:
            return False
        last_vol = float(bars[-1]["volume"])
        sma = sum(float(b["volume"]) for b in bars[-21:-1]) / 20.0
        return sma > 0 and last_vol >= self.vol_spike_mult * sma

    def _swings(self, bars: List[Dict], swing_len: int) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        highs: List[Tuple[int, float]] = []
        lows: List[Tuple[int, float]] = []
        for i in range(swing_len, len(bars) - swing_len):
            is_high = True
            is_low = True
            h = bars[i]["high"]
            l = bars[i]["low"]
            for j in range(i - swing_len, i + swing_len + 1):
                if bars[j]["high"] > h:
                    is_high = False
                if bars[j]["low"] < l:
                    is_low = False
                if not is_high and not is_low:
                    break
            if is_high:
                highs.append((i, float(h)))
            if is_low:
                lows.append((i, float(l)))
        return highs, lows

    def _cluster_levels(self, swings: List[Tuple[int, float]], is_high: bool) -> List[float]:
        if not swings:
            return []
        # cluster prices by tolerance
        swings_sorted = sorted(swings, key=lambda x: x[1], reverse=is_high)
        clusters: List[List[float]] = []
        for _, price in swings_sorted:
            placed = False
            for c in clusters:
                ref = sum(c) / len(c)
                if abs((price - ref) / ref) * 100.0 <= self.equal_tol_pct:
                    c.append(price)
                    placed = True
                    break
            if not placed:
                clusters.append([price])
        # take clusters with touches >= min_touches -> level = average price
        levels: List[float] = [round(sum(c) / len(c), 8) for c in clusters if len(c) >= self.min_touches]
        return levels

    def _detect_sweep(self, last: Dict, equal_highs: List[float], equal_lows: List[float]) -> Tuple[Optional[str], Optional[float]]:
        h = float(last["high"])
        l = float(last["low"])
        c = float(last["close"])
        # swept above highs?
        for lvl in equal_highs:
            if h > lvl and c < lvl:
                # require retrace inside by threshold
                rng = max(1e-12, h - l)
                retr = (h - c) / rng * 100.0
                if retr >= self.sweep_retrace_pct:
                    return "buy", lvl
        # swept below lows?
        for lvl in equal_lows:
            if l < lvl and c > lvl:
                rng = max(1e-12, h - l)
                retr = (c - l) / rng * 100.0
                if retr >= self.sweep_retrace_pct:
                    return "sell", lvl
        return None, None





