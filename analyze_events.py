#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализ событий по сигналам - что произошло и что это значит
"""

import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def analyze_recent_events():
    """Анализ последних событий"""
    csv_path = Path(__file__).parent / "signals_history.csv"
    if not csv_path.exists():
        print("❌ Файл не найден")
        return
    
    signals = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            signals.append(row)
    
    print("=" * 80)
    print("📊 АНАЛИЗ СОБЫТИЙ ПО СИГНАЛАМ")
    print("=" * 80)
    
    # Группируем по типам событий
    events = {
        "tp1_reached": [],
        "tp2_reached": [],
        "tp3_reached": [],
        "sl_hit": [],
        "partial_close": [],
        "sl_moved": [],
        "closed": []
    }
    
    for sig in signals:
        time_str = sig.get('time', '')
        try:
            if len(time_str) == 13:
                dt = datetime.fromtimestamp(int(time_str) / 1000)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            pass
        
        direction = sig.get('direction', '')
        entry = sig.get('entry', '')
        status = sig.get('status', '')
        
        # TP1 достигнут
        if sig.get('tp1_hit', '').strip() == '1':
            events["tp1_reached"].append({
                "time": time_str,
                "direction": direction,
                "entry": entry,
                "tp1": sig.get('tp1', ''),
                "partial": sig.get('partial_close_tp1', '').strip() == '1',
                "sl_moved": sig.get('sl_moved_to_breakeven', '').strip() == '1'
            })
        
        # TP2 достигнут
        if sig.get('tp2_hit', '').strip() == '1':
            events["tp2_reached"].append({
                "time": time_str,
                "direction": direction,
                "entry": entry,
                "tp2": sig.get('tp2', '')
            })
        
        # TP3 достигнут
        if sig.get('tp3_hit', '').strip() == '1':
            events["tp3_reached"].append({
                "time": time_str,
                "direction": direction,
                "entry": entry,
                "tp3": sig.get('tp3', ''),
                "closed": status == 'closed_tp3'
            })
        
        # SL сработал
        if sig.get('sl_hit', '').strip() == '1':
            events["sl_hit"].append({
                "time": time_str,
                "direction": direction,
                "entry": entry,
                "sl": sig.get('sl', ''),
                "close_price": sig.get('close_price', '')
            })
        
        # Закрытые позиции
        if status.startswith('closed'):
            events["closed"].append({
                "time": time_str,
                "direction": direction,
                "entry": entry,
                "status": status,
                "close_price": sig.get('close_price', '')
            })
    
    # Выводим статистику
    print(f"\n📈 СТАТИСТИКА СОБЫТИЙ:")
    print(f"  ✅ TP1 достигнут: {len(events['tp1_reached'])}")
    print(f"  ✅ TP2 достигнут: {len(events['tp2_reached'])}")
    print(f"  🎯 TP3 достигнут: {len(events['tp3_reached'])}")
    print(f"  ❌ SL сработал: {len(events['sl_hit'])}")
    print(f"  💰 Частичное закрытие: {len([e for e in events['tp1_reached'] if e['partial']])}")
    print(f"  🛡️  SL в безубыток: {len([e for e in events['tp1_reached'] if e['sl_moved']])}")
    print(f"  🔒 Закрыто позиций: {len(events['closed'])}")
    
    # Последние события
    print(f"\n🕐 ПОСЛЕДНИЕ СОБЫТИЯ (последние 10):")
    print("-" * 80)
    
    all_recent = []
    for event_type, event_list in events.items():
        for event in event_list:
            event['type'] = event_type
            all_recent.append(event)
    
    # Сортируем по времени (новые первые)
    all_recent.sort(key=lambda x: x.get('time', ''), reverse=True)
    
    for event in all_recent[:10]:
        event_type = event['type']
        direction_ru = "ЛОНГ" if event.get('direction') == 'BUY' else "ШОРТ"
        
        if event_type == 'tp1_reached':
            emoji = "✅"
            text = f"TP1 достигнут"
            if event.get('partial'):
                text += " + Частичное закрытие 50%"
            if event.get('sl_moved'):
                text += " + SL в безубыток"
        elif event_type == 'tp2_reached':
            emoji = "✅"
            text = f"TP2 достигнут"
        elif event_type == 'tp3_reached':
            emoji = "🎯"
            text = f"TP3 достигнут"
            if event.get('closed'):
                text += " (позиция закрыта)"
        elif event_type == 'sl_hit':
            emoji = "❌"
            text = f"Stop Loss сработал"
        else:
            emoji = "📊"
            text = event_type
        
        print(f"{emoji} {event.get('time', '?')} | {direction_ru:4s} | Entry: {event.get('entry', '?'):8s} | {text}")
    
    # Объяснение типов сообщений
    print(f"\n📖 ЧТО ЗНАЧАТ СООБЩЕНИЯ:")
    print("-" * 80)
    print("✅ TP1 достигнут - Первая цель достигнута, можно фиксировать прибыль")
    print("   💰 Частичное закрытие 50% - Половина позиции закрыта на TP1")
    print("   🛡️ SL в безубыток - Стоп перемещен на уровень входа (защита)")
    print("✅ TP2 достигнут - Вторая цель достигнута, хорошая прибыль")
    print("🎯 TP3 достигнут - Все цели достигнуты, максимальная прибыль")
    print("❌ Stop Loss сработал - Цена достигла стоп-лосса, позиция закрыта с убытком")
    print("🔒 Позиция закрыта - Позиция полностью закрыта (TP3 или SL)")
    
    print(f"\n💡 РЕКОМЕНДАЦИИ:")
    print("-" * 80)
    print("1. TP1 достигнут - можно закрыть часть позиции (50% уже закрыто)")
    print("2. TP2 достигнут - можно закрыть еще часть или держать до TP3")
    print("3. TP3 достигнут - позиция закрыта автоматически, максимальная прибыль")
    print("4. SL сработал - позиция закрыта с убытком, это нормально (риск)")
    print("5. После TP1 SL в безубыток - теперь позиция защищена от убытков")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    analyze_recent_events()



