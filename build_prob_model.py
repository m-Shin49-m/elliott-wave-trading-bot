# -*- coding: utf-8 -*-
"""
build_prob_model.py

Строит prob_model.json — эмпирические вероятности достижения TP/SL по истории.

Важно:
- Это НЕ прогноз будущего. Это статистика по прошлым похожим сетапам.
- Модель зависит от настроек в config.py (фильтры, качество, и т.д.).

Пример:
  python build_prob_model.py --pair AVAX/USDT --entry_tf 15m --trend_tf 1h --bars 1500 --horizon 96
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import ccxt  # type: ignore

try:
    import elliott_wave_bot.config as config
    from elliott_wave_bot.elliott_wave import ElliottWaveAnalyzer
    from elliott_wave_bot.liquidity_zones import LiquidityZones
    import elliott_wave_bot.bot as bot
except Exception:
    import config  # type: ignore
    from elliott_wave import ElliottWaveAnalyzer  # type: ignore
    from liquidity_zones import LiquidityZones  # type: ignore
    import bot  # type: ignore


class _Logger:
    def info(self, *a, **k):  # noqa: D401
        pass

    def error(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


def _to_bars(ohlcv) -> List[Dict[str, Any]]:
    return [
        {
            "time": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in ohlcv
    ]


def _bucket_quality(q: int) -> str:
    if q < 50:
        return "<50"
    if q < 60:
        return "50-59"
    if q < 70:
        return "60-69"
    if q < 80:
        return "70-79"
    return "80+"


def _resolve_trend(bars_1h: List[Dict[str, Any]]) -> str:
    return bot._determine_trend_from_bars(bars_1h)


def _simulate_outcome(
    *,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    future_bars: List[Dict[str, Any]],
) -> Tuple[bool, bool, bool, bool, float]:
    """
    Возвращает (tp1_before_sl, tp2_before_sl, tp3_before_sl, sl_before_tp1, r)

    Консервативно: если на одной свече могли быть и TP и SL — считаем, что SL сработал раньше.
    r: -1 если SL раньше TP1, 3/2/1 если достигнут максимальный TP до SL, иначе 0.
    """
    tp1_hit = tp2_hit = tp3_hit = False
    sl_before_tp1 = False

    for b in future_bars:
        h = float(b["high"])
        l = float(b["low"])

        if direction == "BUY":
            # SL first (conservative)
            if l <= sl and (not tp1_hit):
                sl_before_tp1 = True
                break
            if (not tp1_hit) and h >= tp1:
                tp1_hit = True
            if tp1_hit and (not tp2_hit) and h >= tp2:
                tp2_hit = True
            if tp2_hit and (not tp3_hit) and h >= tp3:
                tp3_hit = True
            # if SL occurs after TP1, we don't count it as sl_before_tp1
            if l <= sl and tp1_hit:
                break
        else:
            if h >= sl and (not tp1_hit):
                sl_before_tp1 = True
                break
            if (not tp1_hit) and l <= tp1:
                tp1_hit = True
            if tp1_hit and (not tp2_hit) and l <= tp2:
                tp2_hit = True
            if tp2_hit and (not tp3_hit) and l <= tp3:
                tp3_hit = True
            if h >= sl and tp1_hit:
                break

    tp1_before_sl = tp1_hit and (not sl_before_tp1)
    tp2_before_sl = tp2_hit and (not sl_before_tp1)
    tp3_before_sl = tp3_hit and (not sl_before_tp1)

    if sl_before_tp1:
        return False, False, False, True, -1.0
    if tp3_before_sl:
        return True, True, True, False, 3.0
    if tp2_before_sl:
        return True, True, False, False, 2.0
    if tp1_before_sl:
        return True, False, False, False, 1.0
    return False, False, False, False, 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default=str(getattr(config, "PAIR", "AVAX/USDT")))
    ap.add_argument("--entry_tf", default=str(getattr(config, "MTF_ENTRY_TF", "15m")))
    ap.add_argument("--trend_tf", default=str(getattr(config, "MTF_TREND_TF", "1h")))
    ap.add_argument("--bars", type=int, default=1500, help="Сколько баров entry_tf загрузить")
    ap.add_argument("--horizon", type=int, default=96, help="Сколько баров вперёд смотреть (entry_tf). 96=24ч для 15m")
    ap.add_argument("--relaxed", action="store_true", help="Строить модель без market_quality/time фильтров (больше N)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), str(getattr(config, "PROB_MODEL_PATH", "prob_model.json"))))
    args = ap.parse_args()

    logger = _Logger()

    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}, "timeout": 20000})
    # Загружаем историю
    o15 = ex.fetch_ohlcv(args.pair, timeframe=args.entry_tf, limit=min(1000, args.bars))
    bars_entry = _to_bars(o15)
    # Попытка докачать больше, если нужно (через since назад)
    while len(bars_entry) < args.bars and len(bars_entry) >= 2:
        oldest = bars_entry[0]["time"]
        chunk = ex.fetch_ohlcv(args.pair, timeframe=args.entry_tf, limit=1000, since=oldest - 1000 * 60 * 1000)
        if not chunk:
            break
        older = _to_bars(chunk)
        # защищаемся от зацикливания
        if older and older[-1]["time"] >= bars_entry[0]["time"]:
            break
        bars_entry = older + bars_entry
        bars_entry = bars_entry[-args.bars :]

    o1h = ex.fetch_ohlcv(args.pair, timeframe=args.trend_tf, limit=1000)
    bars_trend_all = _to_bars(o1h)

    # индекс 1h по времени для быстрых срезов
    trend_times = [b["time"] for b in bars_trend_all]

    def trend_slice(ts_ms: int) -> List[Dict[str, Any]]:
        # берём все 1h бары, которые <= ts_ms
        idx = 0
        for i, t in enumerate(trend_times):
            if t <= ts_ms:
                idx = i
            else:
                break
        return bars_trend_all[: idx + 1]

    lz = LiquidityZones(logger)

    buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {"n": 0, "tp1": 0, "tp2": 0, "tp3": 0, "sl": 0, "r_sum": 0.0})

    warmup = max(200, 2 * int(getattr(config, "PIVOT_LEN", 5)) + 20)
    for i in range(warmup, len(bars_entry) - args.horizon - 1):
        window = bars_entry[: i + 1]
        ts = window[-1]["time"]
        trend_bars = trend_slice(ts)
        trend = _resolve_trend(trend_bars)

        analyzer = ElliottWaveAnalyzer(logger=logger, timeframe=args.entry_tf)
        analyzer.pair = args.pair
        if args.relaxed:
            try:
                analyzer.min_volume_ratio = 0.0
                analyzer.max_spread_pct = 999.0
                if getattr(analyzer, "avax_settings", None) and isinstance(analyzer.avax_settings, dict):
                    analyzer.avax_settings = dict(analyzer.avax_settings)
                    analyzer.avax_settings["min_volume_usdt"] = 0
                    analyzer.avax_settings["avoid_hours"] = []
                    analyzer.avax_settings["avoid_weekends"] = False
                    analyzer.avax_settings["check_token_unlocks"] = False
            except Exception:
                pass
        sig = analyzer.get_signal(window)
        setup = None
        if sig:
            sig["setup"] = "ELLIOTT"
        else:
            # sweep fallback
            buy_ok, buy_ctx = lz.evaluate(direction="BUY", bars=window)
            sell_ok, sell_ctx = lz.evaluate(direction="SELL", bars=window)
            sweep_sig = None
            if buy_ctx.get("swept") == "sell":
                sweep_sig = bot._build_sweep_signal(window, "BUY", buy_ctx, trend)
            elif sell_ctx.get("swept") == "buy":
                sweep_sig = bot._build_sweep_signal(window, "SELL", sell_ctx, trend)
            if sweep_sig:
                sig = sweep_sig
                sig["setup"] = "SWEEP"

        if not sig:
            continue

        setup = str(sig.get("setup") or "UNKNOWN").upper()
        direction = str(sig.get("direction") or "UNKNOWN").upper()
        quality = int(sig.get("quality") or 0)
        q_bucket = _bucket_quality(quality)

        entry = float(sig["entry"])
        sl = float(sig["sl"])
        tp1 = float(sig["tp1"])
        tp2 = float(sig["tp2"])
        tp3 = float(sig["tp3"])

        future = bars_entry[i + 1 : i + 1 + args.horizon]
        hit1, hit2, hit3, hit_sl, r = _simulate_outcome(
            direction=direction, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3, future_bars=future
        )

        def add(key_trend: str) -> None:
            key = f"{setup}|{direction}|{key_trend}|{q_bucket}"
            b = buckets[key]
            b["n"] += 1
            b["tp1"] += 1 if hit1 else 0
            b["tp2"] += 1 if hit2 else 0
            b["tp3"] += 1 if hit3 else 0
            # sl = SL раньше TP1
            b["sl"] += 1 if hit_sl else 0
            b["r_sum"] += float(r)

        add(trend)
        add("ANY")

    out = {"generated_at": int(time.time() * 1000), "pair": args.pair, "entry_tf": args.entry_tf, "trend_tf": args.trend_tf, "buckets": {}}
    for k, b in buckets.items():
        n = int(b["n"])
        if n <= 0:
            continue
        out["buckets"][k] = {
            "n": n,
            "p_tp1": b["tp1"] / n,
            "p_tp2": b["tp2"] / n,
            "p_tp3": b["tp3"] / n,
            "p_sl": b["sl"] / n,
            "avg_r": b["r_sum"] / n,
        }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK: model saved to {args.out}, buckets={len(out['buckets'])}")


if __name__ == "__main__":
    main()


