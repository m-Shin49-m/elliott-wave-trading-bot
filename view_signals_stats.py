#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для просмотра статистики по сигналам
"""

import csv
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def format_time(timestamp_str):
    """Форматирование времени"""
    try:
        if len(timestamp_str) == 13:
            ts = int(timestamp_str) / 1000
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        return timestamp_str
    except:
        return timestamp_str

def analyze_signals():
    """Анализ сигналов"""
    csv_path = Path(__file__).parent / "signals_history.csv"
    if not csv_path.exists():
        print("❌ Файл signals_history.csv не найден")
        return
    
    signals = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            signals.append(row)
    
    if not signals:
        print("❌ Нет сигналов в истории")
        return
    
    # Статистика
    total = len(signals)
    opened = [s for s in signals if s.get('status', '').strip() == 'opened']
    closed_sl = [s for s in signals if s.get('status', '').strip() == 'closed_sl']
    closed_tp3 = [s for s in signals if s.get('status', '').strip() == 'closed_tp3']
    cancelled = [s for s in signals if s.get('status', '').strip() == 'cancelled']
    
    tp1_hit = [s for s in signals if s.get('tp1_hit', '').strip() == '1']
    tp2_hit = [s for s in signals if s.get('tp2_hit', '').strip() == '1']
    tp3_hit = [s for s in signals if s.get('tp3_hit', '').strip() == '1']
    sl_hit = [s for s in signals if s.get('sl_hit', '').strip() == '1']
    
    partial_close = [s for s in signals if s.get('partial_close_tp1', '').strip() == '1']
    sl_moved = [s for s in signals if s.get('sl_moved_to_breakeven', '').strip() == '1']
    
    print("=" * 80)
    print("📊 СТАТИСТИКА ПО СИГНАЛАМ")
    print("=" * 80)
    print(f"\nВсего сигналов: {total}")
    print(f"  🟢 Открытых: {len(opened)}")
    print(f"  🔴 Закрыто по SL: {len(closed_sl)} ({len(closed_sl)/total*100:.1f}%)")
    print(f"  🎯 Закрыто по TP3: {len(closed_tp3)} ({len(closed_tp3)/total*100:.1f}%)")
    print(f"  ⚠️  Отменено: {len(cancelled)}")
    
    print(f"\n📈 Достижение уровней:")
    print(f"  ✅ TP1 достигнут: {len(tp1_hit)} ({len(tp1_hit)/total*100:.1f}%)")
    print(f"  ✅ TP2 достигнут: {len(tp2_hit)} ({len(tp2_hit)/total*100:.1f}%)")
    print(f"  🎯 TP3 достигнут: {len(tp3_hit)} ({len(tp3_hit)/total*100:.1f}%)")
    print(f"  ❌ SL сработал: {len(sl_hit)} ({len(sl_hit)/total*100:.1f}%)")
    
    print(f"\n💼 Управление позициями:")
    print(f"  💰 Частичное закрытие на TP1: {len(partial_close)}")
    print(f"  🛡️  SL перемещен в безубыток: {len(sl_moved)}")
    
    # Win Rate
    win_rate = len(tp1_hit) / total * 100 if total > 0 else 0
    loss_rate = len(closed_sl) / total * 100 if total > 0 else 0
    print(f"\n📊 Win Rate:")
    print(f"  ✅ Успешных (TP1+): {win_rate:.1f}%")
    print(f"  ❌ Убыточных (SL): {loss_rate:.1f}%")
    
    # Последние сигналы
    print(f"\n📋 Последние 10 сигналов:")
    print("-" * 80)
    recent = sorted(signals, key=lambda x: int(x.get('time', 0)), reverse=True)[:10]
    for sig in recent:
        time_str = format_time(sig.get('time', ''))
        direction = sig.get('direction', '?')
        entry = sig.get('entry', '?')
        status = sig.get('status', '?')
        tp1_h = "✅" if sig.get('tp1_hit', '').strip() == '1' else "⏳"
        tp2_h = "✅" if sig.get('tp2_hit', '').strip() == '1' else "⏳"
        tp3_h = "✅" if sig.get('tp3_hit', '').strip() == '1' else "⏳"
        sl_h = "❌" if sig.get('sl_hit', '').strip() == '1' else "⏳"
        
        status_emoji = {
            'opened': '🟢',
            'closed_sl': '🔴',
            'closed_tp3': '🎯',
            'cancelled': '⚠️'
        }.get(status, '❓')
        
        print(f"{status_emoji} {time_str} | {direction:4s} | Entry: {entry:8s} | "
              f"TP1:{tp1_h} TP2:{tp2_h} TP3:{tp3_h} SL:{sl_h} | {status}")
    
    print("\n" + "=" * 80)
    print("💡 Для просмотра в реальном времени: http://127.0.0.1:5000")
    print("=" * 80)

if __name__ == "__main__":
    analyze_signals()



