# -*- coding: utf-8 -*-
import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

msg = "🔔 Тест UTF-8: всё ок"
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": msg,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
}
r = requests.post(url, json=payload, timeout=20)
print(r.text)



