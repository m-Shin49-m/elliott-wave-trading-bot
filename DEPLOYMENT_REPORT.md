# Отчет о развертывании Elliott Wave Bot на Ubuntu

## Выполненные команды

### 1. Распаковка проекта
```bash
cd "/home/shin/Рабочий стол"
7z x elliott_wave_bot.7z -o. -y
```

### 2. Проверка структуры проекта
Все необходимые файлы на месте:
- ✅ bot.py
- ✅ config.py
- ✅ elliott_wave.py
- ✅ liquidity_zones.py
- ✅ news.py
- ✅ prob_model.py
- ✅ prob_model.json
- ✅ requirements.txt
- ✅ send_test.py

### 3. Проверка Python и системных зависимостей
```bash
python3 --version  # Python 3.12.3
# python3-venv и python3-pip уже установлены
```

### 4. Создание виртуального окружения
```bash
cd "/home/shin/Рабочий стол/elliott_wave_bot"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

**Установленные зависимости:**
- python-telegram-bot==13.15
- ccxt>=4.0.0
- requests==2.31.0
- и все транзитивные зависимости

### 5. Исправление кода для Linux
Исправлен импорт `msvcrt` (Windows-специфичный) на кроссплатформенный вариант с поддержкой `fcntl` для Linux.

**Изменения в bot.py:**
- Добавлена проверка платформы для файловой блокировки
- Использование `fcntl` на Linux вместо `msvcrt`

### 6. Проверка запуска бота
```bash
cd "/home/shin/Рабочий стол/elliott_wave_bot"
timeout 5 .venv/bin/python bot.py
```
✅ Бот успешно запускается без ошибок

### 7. Создание systemd service файла
Создан файл: `/home/shin/Рабочий стол/elliott_wave_bot/elliott-bot.service`

## Содержимое service файла

```ini
[Unit]
Description=Elliott Wave Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=shin
WorkingDirectory=/home/shin/Рабочий стол/elliott_wave_bot
ExecStart=/home/shin/Рабочий стол/elliott_wave_bot/.venv/bin/python /home/shin/Рабочий стол/elliott_wave_bot/bot.py
Environment="TELEGRAM_TOKEN=7527369349:AAHUsDd7y--kBUDhw4AIDqEFuSUa4NzBHLQ"
Environment="TELEGRAM_CHAT_ID=1170691157"
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Команды для завершения развертывания (требуют sudo)

Выполните следующие команды в терминале:

```bash
# 1. Скопировать service файл в systemd
sudo cp "/home/shin/Рабочий стол/elliott_wave_bot/elliott-bot.service" /etc/systemd/system/elliott-bot.service
sudo chmod 644 /etc/systemd/system/elliott-bot.service

# 2. Перезагрузить systemd daemon
sudo systemctl daemon-reload

# 3. Включить автозапуск и запустить сервис
sudo systemctl enable --now elliott-bot.service

# 4. Проверить статус
sudo systemctl status elliott-bot.service
```

## Управление сервисом

### Просмотр логов в реальном времени
```bash
journalctl -u elliott-bot.service -f
```

### Просмотр последних логов
```bash
journalctl -u elliott-bot.service -n 100
```

### Остановка сервиса
```bash
sudo systemctl stop elliott-bot.service
```

### Перезапуск сервиса
```bash
sudo systemctl restart elliott-bot.service
```

### Отключение автозапуска
```bash
sudo systemctl disable elliott-bot.service
```

### Проверка статуса
```bash
sudo systemctl status elliott-bot.service
```

## Проверка работы бота

После запуска сервиса проверьте:

1. **Статус сервиса:**
   ```bash
   sudo systemctl status elliott-bot.service
   ```
   Должен показывать `active (running)`

2. **Логи:**
   ```bash
   journalctl -u elliott-bot.service -f
   ```
   Должны быть сообщения о запуске бота и работе цикла

3. **Telegram:**
   Бот должен отправлять сообщения в указанный чат (если есть сигналы)

## Примечания

- **Путь к проекту:** `/home/shin/Рабочий стол/elliott_wave_bot`
- **Виртуальное окружение:** `.venv` в папке проекта
- **Логи бота:** `elliott_bot.log` в папке проекта
- **Логи systemd:** через `journalctl -u elliott-bot.service`
- **Автозапуск:** включен, бот запустится при загрузке системы
- **Автоперезапуск:** при падении бот перезапустится через 5 секунд

## Альтернативный способ: использование скрипта

Можно использовать готовый скрипт:
```bash
cd "/home/shin/Рабочий стол/elliott_wave_bot"
./deploy_commands.sh
```

**Внимание:** Перед запуском скрипта убедитесь, что в `elliott-bot.service` указаны правильные значения `TELEGRAM_TOKEN` и `TELEGRAM_CHAT_ID` (если они отличаются от значений в config.py).
















