#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для очистки и организации сигналов
"""

import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def cleanup_signals():
    """Очистка и организация сигналов"""
    csv_path = Path(__file__).parent / "signals_history.csv"
    if not csv_path.exists():
        print("❌ Файл не найден")
        return
    
    # Читаем сигналы
    signals = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            signals.append(row)
    
    print(f"📊 Всего сигналов: {len(signals)}")
    
    # 1. Закрываем старые открытые сигналы (>72 часа)
    updated = False
    now_ts = datetime.now().timestamp()
    
    for signal in signals:
        if signal.get('status', '').strip() != 'opened':
            continue
        
        try:
            time_str = signal.get('time', '')
            if len(time_str) == 13:
                signal_ts = int(time_str) / 1000
                age_hours = (now_ts - signal_ts) / 3600
                
                if age_hours > 72:  # Старше 72 часов
                    signal['status'] = 'closed_timeout'
                    signal['close_time'] = str(int(now_ts * 1000))
                    updated = True
                    print(f"  ⏰ Закрыт старый сигнал: {time_str[:10]} ({age_hours:.1f}ч)")
        except:
            pass
    
    # 2. Удаляем точные дубликаты (одинаковое время + направление + entry)
    seen = {}
    unique_signals = []
    duplicates_removed = 0
    
    for signal in signals:
        key = (
            signal.get('time', ''),
            signal.get('direction', ''),
            signal.get('entry', '')
        )
        if key in seen:
            duplicates_removed += 1
            continue
        seen[key] = True
        unique_signals.append(signal)
    
    if duplicates_removed > 0:
        print(f"  🗑️  Удалено дубликатов: {duplicates_removed}")
        updated = True
        signals = unique_signals
    
    # 3. Сохраняем если были изменения
    if updated:
        backup_path = csv_path.with_suffix('.csv.backup')
        import shutil
        shutil.copy2(csv_path, backup_path)
        print(f"  💾 Создана резервная копия: {backup_path.name}")
        
        # Сохраняем обновленные данные
        fieldnames = list(signals[0].keys()) if signals else []
        with csv_path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for signal in signals:
                writer.writerow(signal)
        
        print(f"  ✅ Файл обновлен")
    else:
        print("  ✅ Изменений не требуется")
    
    # Статистика после очистки
    opened = [s for s in signals if s.get('status', '').strip() == 'opened']
    print(f"\n📊 После очистки:")
    print(f"  Открытых: {len(opened)}")
    print(f"  Всего: {len(signals)}")

if __name__ == "__main__":
    cleanup_signals()



