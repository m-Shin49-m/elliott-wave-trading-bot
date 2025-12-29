#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_data_stats.py

Показывает статистику по накопленным данным:
- Сколько сигналов в истории
- Распределение по типам (ELLIOTT/SWEEP)
- Распределение по направлениям (BUY/SELL)
- Распределение по качеству
- Рекомендации по обновлению модели
"""

import csv
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

def main():
    csv_path = Path(__file__).parent / "signals_history.csv"
    
    if not csv_path.exists():
        print("❌ Файл signals_history.csv не найден!")
        print("   Бот должен сначала отправить хотя бы один сигнал.")
        return
    
    signals = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            signals.append(row)
    
    if not signals:
        print("📊 История сигналов пуста")
        return
    
    print("=" * 60)
    print("📊 СТАТИСТИКА НАКОПЛЕННЫХ ДАННЫХ")
    print("=" * 60)
    print()
    
    # Общая статистика
    total = len(signals)
    print(f"📈 Всего сигналов: {total}")
    
    # Временной диапазон
    if signals:
        first_ts = int(signals[0]["time"]) / 1000
        last_ts = int(signals[-1]["time"]) / 1000
        first_date = datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d %H:%M:%S")
        last_date = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")
        print(f"📅 Первый сигнал: {first_date}")
        print(f"📅 Последний сигнал: {last_date}")
        days = (last_ts - first_ts) / 86400
        print(f"⏱  Период: {days:.1f} дней")
    print()
    
    # Распределение по типам сетапов
    setups = Counter()
    for s in signals:
        tf = s.get("timeframe", "")
        if "ELLIOTT" in tf:
            setups["ELLIOTT"] += 1
        elif "SWEEP" in tf:
            setups["SWEEP"] += 1
        else:
            setups["OTHER"] += 1
    
    print("🔧 Распределение по типам сетапов:")
    for setup, count in setups.most_common():
        pct = (count / total) * 100
        print(f"   {setup:10s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    # Распределение по направлениям
    directions = Counter(s.get("direction", "UNKNOWN") for s in signals)
    print("📊 Распределение по направлениям:")
    for direction, count in directions.most_common():
        pct = (count / total) * 100
        emoji = "🟢" if direction == "BUY" else "🔴" if direction == "SELL" else "⚪"
        print(f"   {emoji} {direction:4s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    # Распределение по качеству
    qualities = []
    for s in signals:
        q_str = s.get("quality", "").strip()
        if q_str:
            try:
                qualities.append(int(q_str))
            except (ValueError, TypeError):
                pass
    
    if qualities:
        avg_q = sum(qualities) / len(qualities)
        min_q = min(qualities)
        max_q = max(qualities)
        print("⭐ Распределение по качеству:")
        print(f"   Среднее: {avg_q:.1f}%")
        print(f"   Минимум: {min_q}%")
        print(f"   Максимум: {max_q}%")
        
        # Категории
        cat_a = sum(1 for q in qualities if q >= 85)
        cat_b = sum(1 for q in qualities if 70 <= q < 85)
        cat_c = sum(1 for q in qualities if 60 <= q < 70)
        cat_low = sum(1 for q in qualities if q < 60)
        
        print(f"   Категория A (85+): {cat_a} ({cat_a/len(qualities)*100:.1f}%)")
        print(f"   Категория B (70-84): {cat_b} ({cat_b/len(qualities)*100:.1f}%)")
        print(f"   Категория C (60-69): {cat_c} ({cat_c/len(qualities)*100:.1f}%)")
        print(f"   Низкое (<60): {cat_low} ({cat_low/len(qualities)*100:.1f}%)")
    print()
    
    # Статусы
    statuses = Counter(s.get("status", "unknown") for s in signals)
    print("📋 Статусы сигналов:")
    for status, count in statuses.most_common():
        pct = (count / total) * 100
        print(f"   {status:10s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    # Рекомендации
    print("=" * 60)
    print("💡 РЕКОМЕНДАЦИИ")
    print("=" * 60)
    print()
    
    if total < 50:
        print(f"⚠️  Мало данных для статистики: {total} сигналов")
        print(f"   Рекомендуется накопить минимум 50-100 сигналов")
        print(f"   Осталось: {50 - total} сигналов до минимума")
    elif total < 100:
        print(f"✅ Хорошо: {total} сигналов накоплено")
        print(f"   Для более точной модели рекомендуется 100+ сигналов")
        print(f"   Осталось: {100 - total} сигналов до оптимального уровня")
    else:
        print(f"🎉 Отлично: {total} сигналов накоплено!")
        print(f"   Достаточно данных для надежной вероятностной модели")
    
    print()
    print("🔄 Для обновления вероятностной модели выполните:")
    print("   ./update_prob_model.sh")
    print()
    print("📈 Модель будет перестроена на основе исторических данных Binance")
    print("   и покажет вероятности достижения TP/SL для похожих сетапов.")
    print()

if __name__ == "__main__":
    main()
















