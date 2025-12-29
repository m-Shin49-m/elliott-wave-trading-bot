# -*- coding: utf-8 -*-
"""Тест отправки сообщения в Telegram"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    import config
except ImportError:
    import elliott_wave_bot.config as config

try:
    from telegram import Bot
    from bot import send_telegram_message
    import logging
    
    logger = logging.getLogger('test')
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    
    print("=" * 50)
    print("ТЕСТ ОТПРАВКИ В TELEGRAM")
    print("=" * 50)
    print(f"Токен (первые 15 символов): {config.TELEGRAM_TOKEN[:15]}...")
    print(f"Chat ID: {config.TELEGRAM_CHAT_ID}")
    print()
    
    bot = Bot(token=config.TELEGRAM_TOKEN)
    
    # Тест 1: Простое сообщение
    print("Тест 1: Отправка простого сообщения...")
    try:
        result = bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text="🔔 Тест: бот работает!",
            parse_mode="HTML"
        )
        print("✅ Сообщение отправлено успешно!")
        print(f"   Message ID: {result.get('message_id', 'N/A')}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        if "404" in str(e) or "Not Found" in str(e):
            print()
            print("⚠️  Ошибка 404 означает:")
            print("   - Токен неверный, или")
            print("   - Chat ID неверный, или")
            print("   - Бот не добавлен в чат/канал")
            print()
            print("Проверьте:")
            print("   1. Токен получен у @BotFather")
            print("   2. Chat ID получен у @userinfobot")
            print("   3. Бот добавлен в чат/канал")
    
    print()
    print("=" * 50)
    
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что зависимости установлены: pip install python-telegram-bot")
















