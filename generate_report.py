#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация отчета по всем сделкам
"""

import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def generate_report():
    """Генерация полного отчета по сделкам"""
    csv_path = Path(__file__).parent / "signals_history.csv"
    if not csv_path.exists():
        print("❌ Файл не найден")
        return
    
    signals = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            signals.append(row)
    
    if not signals:
        print("❌ Нет сигналов")
        return
    
    print("=" * 80)
    print("📊 ОТЧЕТ ПО ВСЕМ СДЕЛКАМ")
    print("=" * 80)
    
    total = len(signals)
    opened = [s for s in signals if s.get('status', '').strip() == 'opened']
    closed_sl = [s for s in signals if s.get('status', '').strip() == 'closed_sl']
    closed_tp3 = [s for s in signals if s.get('status', '').strip() == 'closed_tp3']
    
    # Статистика по TP/SL
    tp1_hit = [s for s in signals if s.get('tp1_hit', '').strip() == '1']
    tp2_hit = [s for s in signals if s.get('tp2_hit', '').strip() == '1']
    tp3_hit = [s for s in signals if s.get('tp3_hit', '').strip() == '1']
    sl_hit = [s for s in signals if s.get('sl_hit', '').strip() == '1']
    
    # Статистика по направлениям
    buy_signals = [s for s in signals if s.get('direction', '').strip() == 'BUY']
    sell_signals = [s for s in signals if s.get('direction', '').strip() == 'SELL']
    
    # Статистика по качеству
    quality_stats = defaultdict(int)
    for s in signals:
        q = int(s.get('quality', 0) or 0)
        if q >= 85:
            quality_stats['A'] += 1
        elif q >= 70:
            quality_stats['B'] += 1
        elif q >= 60:
            quality_stats['C'] += 1
        else:
            quality_stats['Low'] += 1
    
    print(f"\n📈 ОБЩАЯ СТАТИСТИКА:")
    print(f"  Всего сигналов: {total}")
    print(f"  Открытых: {len(opened)} ({len(opened)/total*100:.1f}%)")
    print(f"  Закрытых: {len(closed_sl) + len(closed_tp3)} ({(len(closed_sl) + len(closed_tp3))/total*100:.1f}%)")
    
    print(f"\n📊 ПО НАПРАВЛЕНИЯМ:")
    print(f"  BUY: {len(buy_signals)} ({len(buy_signals)/total*100:.1f}%)")
    print(f"  SELL: {len(sell_signals)} ({len(sell_signals)/total*100:.1f}%)")
    
    print(f"\n✅ ДОСТИЖЕНИЕ УРОВНЕЙ:")
    print(f"  TP1 достигнут: {len(tp1_hit)} ({len(tp1_hit)/total*100:.1f}%)")
    print(f"  TP2 достигнут: {len(tp2_hit)} ({len(tp2_hit)/total*100:.1f}%)")
    print(f"  TP3 достигнут: {len(tp3_hit)} ({len(tp3_hit)/total*100:.1f}%)")
    print(f"  SL сработал: {len(sl_hit)} ({len(sl_hit)/total*100:.1f}%)")
    
    print(f"\n🎯 РЕЗУЛЬТАТЫ СДЕЛОК:")
    print(f"  Закрыто по TP3: {len(closed_tp3)} ({len(closed_tp3)/total*100:.1f}%)")
    print(f"  Закрыто по SL: {len(closed_sl)} ({len(closed_sl)/total*100:.1f}%)")
    
    # Win Rate
    successful = len(tp1_hit)  # Сигналы достигшие хотя бы TP1
    win_rate = (successful / total * 100) if total > 0 else 0
    loss_rate = (len(closed_sl) / total * 100) if total > 0 else 0
    
    print(f"\n📊 WIN RATE:")
    print(f"  Успешных (TP1+): {successful} ({win_rate:.1f}%)")
    print(f"  Убыточных (SL): {len(closed_sl)} ({loss_rate:.1f}%)")
    print(f"  Соотношение Win/Loss: {successful}/{len(closed_sl)} = {successful/len(closed_sl) if len(closed_sl) > 0 else 'N/A'}")
    
    print(f"\n⭐ ПО КАЧЕСТВУ:")
    print(f"  Категория A (≥85): {quality_stats['A']}")
    print(f"  Категория B (70-84): {quality_stats['B']}")
    print(f"  Категория C (60-69): {quality_stats['C']}")
    print(f"  Низкое (<60): {quality_stats['Low']}")
    
    # Детальная статистика по закрытым сделкам
    print(f"\n📋 ДЕТАЛЬНАЯ СТАТИСТИКА ПО ЗАКРЫТЫМ СДЕЛКАМ:")
    print("-" * 80)
    
    closed = [s for s in signals if s.get('status', '').startswith('closed')]
    if closed:
        # Группируем по результату
        tp3_closed = [s for s in closed if s.get('status') == 'closed_tp3']
        sl_closed = [s for s in closed if s.get('status') == 'closed_sl']
        
        print(f"  Закрыто по TP3: {len(tp3_closed)}")
        for sig in tp3_closed[:5]:
            time_str = sig.get('time', '')[:10]
            direction = sig.get('direction', '?')
            entry = sig.get('entry', '?')
            close_price = sig.get('close_price', '?')
            print(f"    {time_str} | {direction} | Entry: {entry} | Закрыто: {close_price}")
        
        print(f"\n  Закрыто по SL: {len(sl_closed)}")
        for sig in sl_closed[:5]:
            time_str = sig.get('time', '')[:10]
            direction = sig.get('direction', '?')
            entry = sig.get('entry', '?')
            sl = sig.get('sl', '?')
            print(f"    {time_str} | {direction} | Entry: {entry} | SL: {sl}")
    
    # Статистика по достижению TP
    print(f"\n📈 СТАТИСТИКА ПО ДОСТИЖЕНИЮ TP:")
    print("-" * 80)
    print(f"  Достигли TP1: {len(tp1_hit)}")
    print(f"  Достигли TP2: {len(tp2_hit)}")
    print(f"  Достигли TP3: {len(tp3_hit)}")
    print(f"  Из достигших TP1, достигли TP2: {len(tp2_hit)} ({len(tp2_hit)/len(tp1_hit)*100 if len(tp1_hit) > 0 else 0:.1f}%)")
    print(f"  Из достигших TP2, достигли TP3: {len(tp3_hit)} ({len(tp3_hit)/len(tp2_hit)*100 if len(tp2_hit) > 0 else 0:.1f}%)")
    
    print("\n" + "=" * 80)
    print("💡 Все сигналы отслеживаются автоматически для статистики")
    print("📱 Уведомления в Telegram приходят только для сигналов 'В позиции'")
    print("=" * 80)

if __name__ == "__main__":
    generate_report()



