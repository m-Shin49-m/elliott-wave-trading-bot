# Инструкция по настройке автозапуска

## 🚀 Быстрая настройка

Выполните **одну команду** в терминале:

```bash
sudo bash "/home/shin/Рабочий стол/elliott_wave_bot/setup_autostart.sh"
```

Эта команда:
1. ✅ Скопирует service файл в systemd
2. ✅ Включит автозапуск при загрузке системы
3. ✅ Запустит бота сейчас
4. ✅ Настроит автоперезапуск при падении

## 📋 Что будет настроено

- **Автозапуск при загрузке**: Бот запустится автоматически при перезагрузке системы
- **Автоперезапуск при падении**: Если бот упадет, он перезапустится через 5 секунд
- **Логи в systemd**: Все логи доступны через `journalctl`

## 🔍 Проверка работы

После выполнения скрипта проверьте:

```bash
# Статус сервиса (должен быть active)
sudo systemctl status elliott-bot.service

# Логи в реальном времени
journalctl -u elliott-bot.service -f

# Последние 50 строк логов
journalctl -u elliott-bot.service -n 50
```

## 🛠️ Управление сервисом

### Перезапуск
```bash
sudo systemctl restart elliott-bot.service
```

### Остановка
```bash
sudo systemctl stop elliott-bot.service
```

### Запуск
```bash
sudo systemctl start elliott-bot.service
```

### Отключить автозапуск
```bash
sudo systemctl disable elliott-bot.service
```

### Включить автозапуск обратно
```bash
sudo systemctl enable elliott-bot.service
```

## ⚠️ Важно

1. **Остановите старый процесс** (если запущен вручную):
   ```bash
   pkill -f "bot.py"
   ```

2. **Проверьте переменные окружения** в service файле:
   - `/etc/systemd/system/elliott-bot.service`
   - Убедитесь, что `TELEGRAM_TOKEN` и `TELEGRAM_CHAT_ID` указаны правильно

3. **После изменения config.py** перезапустите сервис:
   ```bash
   sudo systemctl restart elliott-bot.service
   ```

## 🐛 Решение проблем

### Сервис не запускается
```bash
# Проверьте логи
journalctl -u elliott-bot.service -n 100

# Проверьте путь к Python
ls -la "/home/shin/Рабочий стол/elliott_wave_bot/.venv/bin/python"

# Проверьте права на файлы
ls -la "/home/shin/Рабочий стол/elliott_wave_bot/bot.py"
```

### Сервис падает сразу после запуска
```bash
# Смотрите логи
journalctl -u elliott-bot.service -f

# Проверьте, что виртуальное окружение создано
test -d "/home/shin/Рабочий стол/elliott_wave_bot/.venv" && echo "OK" || echo "Создайте venv!"
```

### Автозапуск не работает
```bash
# Проверьте, что сервис включен
systemctl is-enabled elliott-bot.service

# Должно вывести: enabled
```

## 📝 Альтернатива: ручная настройка

Если скрипт не работает, выполните команды вручную:

```bash
# 1. Копировать service файл
sudo cp "/home/shin/Рабочий стол/elliott_wave_bot/elliott-bot.service" /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/elliott-bot.service

# 2. Перезагрузить daemon
sudo systemctl daemon-reload

# 3. Включить автозапуск
sudo systemctl enable elliott-bot.service

# 4. Запустить сервис
sudo systemctl start elliott-bot.service

# 5. Проверить статус
sudo systemctl status elliott-bot.service
```

---

**Готово!** После настройки бот будет работать 24/7 с автозапуском при перезагрузке.
















