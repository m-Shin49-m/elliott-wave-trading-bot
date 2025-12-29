#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_update_model.py

Автоматическое обновление вероятностной модели.
Можно вызывать из bot.py или как отдельный скрипт.
"""

import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Optional

try:
    import elliott_wave_bot.config as config
except Exception:
    import config  # type: ignore


def should_update_model(
    model_path: str,
    min_age_hours: int = 24,
    min_new_signals: int = 10
) -> tuple[bool, str]:
    """
    Проверяет, нужно ли обновлять модель.
    
    Returns:
        (should_update, reason)
    """
    model_file = Path(model_path)
    
    # Если модели нет - нужно создать
    if not model_file.exists():
        return True, "Модель не существует"
    
    # Проверяем возраст модели
    model_age = time.time() - model_file.stat().st_mtime
    model_age_hours = model_age / 3600
    
    if model_age_hours >= min_age_hours:
        return True, f"Модель устарела ({model_age_hours:.1f} часов)"
    
    # Проверяем количество новых сигналов с момента последнего обновления
    try:
        csv_path = Path(__file__).parent / "signals_history.csv"
        if csv_path.exists():
            import csv
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                signals = list(reader)
            
            if signals:
                last_signal_ts = int(signals[-1]["time"]) / 1000
                model_ts = model_file.stat().st_mtime
                
                # Считаем сигналы после обновления модели
                new_signals = sum(
                    1 for s in signals
                    if int(s["time"]) / 1000 > model_ts
                )
                
                if new_signals >= min_new_signals:
                    return True, f"Накопилось {new_signals} новых сигналов"
    except Exception:
        pass
    
    return False, "Обновление не требуется"


def update_model(
    logger=None,
    pair: Optional[str] = None,
    entry_tf: Optional[str] = None,
    trend_tf: Optional[str] = None,
    bars: int = 1500,
    horizon: int = 96
) -> bool:
    """
    Обновляет вероятностную модель.
    
    Returns:
        True если успешно, False если ошибка
    """
    if logger:
        logger.info("🔄 Начинаю автоматическое обновление вероятностной модели...")
    
    try:
        base_dir = Path(__file__).parent
        build_script = base_dir / "build_prob_model.py"
        
        if not build_script.exists():
            if logger:
                logger.error("build_prob_model.py не найден!")
            return False
        
        # Параметры из config или переданные
        pair = pair or getattr(config, "PAIR", "AVAX/USDT")
        entry_tf = entry_tf or getattr(config, "MTF_ENTRY_TF", "15m")
        trend_tf = trend_tf or getattr(config, "MTF_TREND_TF", "1h")
        
        # Запускаем build_prob_model.py
        cmd = [
            sys.executable,
            str(build_script),
            "--pair", pair,
            "--entry_tf", entry_tf,
            "--trend_tf", trend_tf,
            "--bars", str(bars),
            "--horizon", str(horizon)
        ]
        
        if logger:
            logger.info(f"Выполняю: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=600  # 10 минут максимум
        )
        
        if result.returncode == 0:
            if logger:
                logger.info("✅ Вероятностная модель успешно обновлена!")
                if result.stdout:
                    logger.info(f"Вывод: {result.stdout.strip()}")
            return True
        else:
            if logger:
                logger.error(f"❌ Ошибка обновления модели: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("❌ Таймаут при обновлении модели (>10 минут)")
        return False
    except Exception as e:
        if logger:
            logger.error(f"❌ Исключение при обновлении модели: {e}")
        return False


def main():
    """Запуск как отдельный скрипт"""
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logger = logging.getLogger("auto_update_model")
    
    model_path = str(getattr(config, "PROB_MODEL_PATH", "prob_model.json"))
    model_path = os.path.join(os.path.dirname(__file__), model_path)
    
    should, reason = should_update_model(model_path)
    
    if should:
        logger.info(f"Причина обновления: {reason}")
        success = update_model(logger)
        if success:
            logger.info("✅ Модель обновлена успешно")
            sys.exit(0)
        else:
            logger.error("❌ Не удалось обновить модель")
            sys.exit(1)
    else:
        logger.info(f"ℹ️  {reason}")
        sys.exit(0)


if __name__ == "__main__":
    main()
















