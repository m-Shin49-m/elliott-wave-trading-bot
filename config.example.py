# -*- coding: utf-8 -*-
# ПРИМЕР КОНФИГУРАЦИИ
# Скопируйте этот файл в config.py и заполните своими данными

import os

# Telegram (используйте переменные окружения!)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# Trading pair and timeframe
PAIR = "AVAX/USDT"
TIMEFRAME = "1h"

# Multi-timeframe analysis
ENABLE_MULTI_TF = True
MULTI_TIMEFRAMES = ["15m", "1h"]

# ... остальные настройки из оригинального config.py ...

