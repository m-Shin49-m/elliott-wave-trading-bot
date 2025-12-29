# ✅ Бот запущен и работает!

## Текущий статус

**Бот работает в фоне:**
- PID процесса: проверьте командой `ps aux | grep bot.py`
- Логи: `tail -f bot_output.log` или `tail -f elliott_bot.log`
- Остановка: `pkill -f "bot.py"`

## Для запуска через systemd (автозапуск при перезагрузке)

Выполните **одну команду** в терминале:

```bash
sudo bash "/home/shin/Рабочий стол/elliott_wave_bot/final_deploy.sh"
```

Эта команда:
1. Скопирует service файл в systemd
2. Включит автозапуск
3. Запустит сервис
4. Покажет статус

## После запуска через systemd

### Просмотр логов
```bash
journalctl -u elliott-bot.service -f
```

### Управление
```bash
sudo systemctl status elliott-bot.service    # статус
sudo systemctl restart elliott-bot.service   # перезапуск
sudo systemctl stop elliott-bot.service      # остановка
```

## Альтернатива: запуск без systemd

Если не хотите использовать systemd, можно запускать бот скриптом:

```bash
cd "/home/shin/Рабочий стол/elliott_wave_bot"
./start_bot.sh
```

**Недостаток:** не будет автозапуска при перезагрузке системы.
















