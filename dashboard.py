# -*- coding: utf-8 -*-
"""
Веб-дашборд для мониторинга Elliott Wave Bot
"""

from __future__ import annotations

import os
import sys
import json
import csv
import logging
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

try:
    import config
except ImportError:
    import elliott_wave_bot.config as config

app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Пути
BASE_DIR = Path(__file__).parent
HISTORY_CSV = BASE_DIR / getattr(config, "HISTORY_CSV", "signals_history.csv")
BOT_LOG = BASE_DIR / "elliott_bot.log"

# Кэш для оптимизации
_signals_cache: Optional[List[Dict]] = None
_signals_cache_time: float = 0
CACHE_TTL_SECONDS = 30  # Кэш на 30 секунд


def load_signals_history() -> List[Dict]:
    """Загрузить историю сигналов из CSV с кэшированием."""
    global _signals_cache, _signals_cache_time
    
    # Проверяем кэш
    current_time = time.time()
    if _signals_cache is not None and (current_time - _signals_cache_time) < CACHE_TTL_SECONDS:
        return _signals_cache
    
    signals = []
    if not HISTORY_CSV.exists():
        _signals_cache = signals
        _signals_cache_time = current_time
        return signals
    
    try:
        with open(HISTORY_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Очищаем пустые значения и нормализуем
                cleaned_row = {}
                for k, v in row.items():
                    cleaned_row[k] = v.strip() if v and v.strip() else ""
                signals.append(cleaned_row)
        
        # Обновляем кэш
        _signals_cache = signals
        _signals_cache_time = current_time
    except Exception as e:
        logger.error(f"Ошибка загрузки истории: {e}")
    
    return signals


def calculate_statistics(signals: List[Dict]) -> Dict:
    """Рассчитать статистику по сигналам."""
    if not signals:
        return {
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "avg_quality": 0,
            "signals_by_category": {"A": 0, "B": 0, "C": 0},
            "signals_by_timeframe": {},
            "recent_signals": []
        }
    
    stats = {
        "total_signals": len(signals),
        "buy_signals": sum(1 for s in signals if s.get("direction") == "BUY"),
        "sell_signals": sum(1 for s in signals if s.get("direction") == "SELL"),
        "avg_quality": 0,
        "signals_by_category": {"A": 0, "B": 0, "C": 0},
        "signals_by_timeframe": defaultdict(int),
        "recent_signals": []
    }
    
    # Среднее качество (безопасное преобразование)
    qualities = []
    for s in signals:
        q_str = s.get("quality", "").strip()
        if q_str:
            try:
                qualities.append(int(q_str))
            except (ValueError, TypeError):
                pass
    if qualities:
        stats["avg_quality"] = sum(qualities) / len(qualities)
    
    # Категории (безопасное преобразование)
    for signal in signals:
        q_str = signal.get("quality", "").strip()
        quality = 0
        if q_str:
            try:
                quality = int(q_str)
            except (ValueError, TypeError):
                quality = 0
        
        if quality >= getattr(config, "CATEGORY_A_MIN", 85):
            stats["signals_by_category"]["A"] += 1
        elif quality >= getattr(config, "CATEGORY_B_MIN", 70):
            stats["signals_by_category"]["B"] += 1
        elif quality >= getattr(config, "CATEGORY_C_MIN", 60):
            stats["signals_by_category"]["C"] += 1
        
        # Таймфреймы
        tf = signal.get("timeframe", "unknown")
        stats["signals_by_timeframe"][tf] += 1
    
    # Последние сигналы (последние 10)
    recent = sorted(signals, key=lambda x: x.get("time", ""), reverse=True)[:10]
    stats["recent_signals"] = recent
    
    return stats


def get_bot_status() -> Dict:
    """Получить статус бота."""
    status = {
        "running": False,
        "last_log_time": None,
        "log_size": 0,
        "uptime": None
    }
    
    # Проверка лог-файла
    if BOT_LOG.exists():
        status["log_size"] = BOT_LOG.stat().st_size
        try:
            # Оптимизация: читаем только последние 100 строк вместо всего файла
            # Используем tail для больших файлов
            import subprocess
            try:
                # Пробуем использовать tail для эффективного чтения последних строк
                result = subprocess.run(
                    ['tail', '-n', '100', str(BOT_LOG)],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if lines:
                        last_line = lines[-1].strip()
                        if last_line:
                            status["running"] = True
                            if "[INFO]" in last_line or "[ERROR]" in last_line:
                                status["last_log_time"] = datetime.now().isoformat()
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                # Fallback: читаем файл с конца (только последние 50KB)
                try:
                    with open(BOT_LOG, 'rb') as f:
                        # Перемещаемся к концу файла
                        f.seek(0, 2)  # Конец файла
                        file_size = f.tell()
                        # Читаем последние 50KB
                        read_size = min(50000, file_size)
                        f.seek(max(0, file_size - read_size))
                        content = f.read().decode('utf-8', errors='ignore')
                        lines = content.split('\n')
                        if lines:
                            last_line = lines[-1].strip()
                            if last_line:
                                status["running"] = True
                                if "[INFO]" in last_line or "[ERROR]" in last_line:
                                    status["last_log_time"] = datetime.now().isoformat()
                except Exception as e:
                    logger.error(f"Ошибка чтения лога: {e}")
        except Exception as e:
            logger.error(f"Ошибка чтения лога: {e}")
    
    return status


@app.route('/')
def index():
    """Главная страница дашборда."""
    return render_template('dashboard.html')


@app.route('/api/statistics')
def api_statistics():
    """API: Статистика по сигналам."""
    signals = load_signals_history()
    stats = calculate_statistics(signals)
    return jsonify(stats)


@app.route('/api/signals')
def api_signals():
    """API: Список всех сигналов."""
    limit = request.args.get('limit', 50, type=int)
    signals = load_signals_history()
    # Сортируем по времени (новые первые)
    sorted_signals = sorted(signals, key=lambda x: x.get("time", ""), reverse=True)[:limit]
    return jsonify(sorted_signals)


@app.route('/api/signals/<signal_id>')
def api_signal_detail(signal_id: str):
    """API: Детали конкретного сигнала."""
    signals = load_signals_history()
    # Ищем по времени или индексу
    try:
        idx = int(signal_id)
        if 0 <= idx < len(signals):
            return jsonify(signals[idx])
    except:
        pass
    
    # Ищем по времени
    for signal in signals:
        if signal.get("time") == signal_id:
            return jsonify(signal)
    
    return jsonify({"error": "Signal not found"}), 404


@app.route('/api/bot/status')
def api_bot_status():
    """API: Статус бота."""
    status = get_bot_status()
    return jsonify(status)


@app.route('/api/config')
def api_config():
    """API: Текущая конфигурация (без секретов)."""
    safe_config = {
        "pair": getattr(config, "PAIR", "N/A"),
        "timeframe": getattr(config, "TIMEFRAME", "N/A"),
        "multi_tf": getattr(config, "ENABLE_MULTI_TF", False),
        "multi_timeframes": getattr(config, "MULTI_TIMEFRAMES", []),
        "quality_threshold": getattr(config, "QUALITY_THRESHOLD", 60),
        "min_send_quality": getattr(config, "MIN_SEND_QUALITY", 50),
        "use_atr_targets": getattr(config, "USE_ATR_TARGETS", True),
    }
    return jsonify(safe_config)


@app.route('/api/cache/stats')
def api_cache_stats():
    """API: Статистика кэша."""
    try:
        from utils_cache import get_cache
        cache = get_cache()
        return jsonify({
            "size": cache.size(),
            "max_size": cache.max_size,
            "ttl_seconds": cache.ttl_seconds
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Создаем папку для шаблонов если её нет
    templates_dir = BASE_DIR / 'templates'
    templates_dir.mkdir(exist_ok=True)
    
    port = int(os.getenv('DASHBOARD_PORT', 5000))
    host = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    
    # Проверка доступности порта
    import socket
    import time
    max_retries = 3
    retry_delay = 1
    for attempt in range(max_retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.close()
            break  # Порт свободен
        except OSError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Порт {port} занят (попытка {attempt + 1}/{max_retries}), жду {retry_delay} сек...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                # Порт занят, пробуем другой
                logger.warning(f"Порт {port} занят после {max_retries} попыток, пробую порт {port + 1}")
                port = port + 1
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((host, port))
                    sock.close()
                except OSError:
                    logger.error(f"Порты {port-1} и {port} заняты. Остановите другие процессы или укажите другой порт через DASHBOARD_PORT")
                    sys.exit(1)
    
    logger.info(f"Запуск дашборда на http://{host}:{port}")
    app.run(host=host, port=port, debug=False)

