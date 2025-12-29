# 🌊 Веб-дашборд Elliott Wave Bot

Веб-интерфейс для мониторинга и анализа работы торгового бота.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
cd "/home/shin/Рабочий стол/elliott_wave_bot"
source .venv/bin/activate
pip install flask flask-cors
```

Или обновите requirements.txt:
```bash
pip install -r requirements.txt
```

### 2. Запуск дашборда

```bash
./start_dashboard.sh
```

Или напрямую:
```bash
python3 dashboard.py
```

### 3. Открыть в браузере

Откройте: http://localhost:5000

## 📊 Возможности

### Статистика
- Общее количество сигналов
- Разделение по направлениям (BUY/SELL)
- Среднее качество сигналов
- Распределение по категориям (A/B/C)
- Статистика по таймфреймам

### Мониторинг
- Статус бота (работает/остановлен)
- Последние сигналы в реальном времени
- Текущая конфигурация
- Статистика кэша

### API Endpoints

- `GET /api/statistics` - Общая статистика
- `GET /api/signals?limit=50` - Список сигналов
- `GET /api/signals/<id>` - Детали сигнала
- `GET /api/bot/status` - Статус бота
- `GET /api/config` - Конфигурация
- `GET /api/cache/stats` - Статистика кэша

## ⚙️ Настройка

### Порт и хост

Измените через переменные окружения:

```bash
export DASHBOARD_PORT=8080
export DASHBOARD_HOST=0.0.0.0
python3 dashboard.py
```

Или в коде `dashboard.py`:
```python
port = int(os.getenv('DASHBOARD_PORT', 5000))
host = os.getenv('DASHBOARD_HOST', '127.0.0.1')
```

## 🔧 Запуск как systemd сервис

1. Скопируйте service файл:
```bash
sudo cp dashboard.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/dashboard.service
```

2. Создайте симлинк (если еще не создан):
```bash
sudo ln -sf '/home/shin/Рабочий стол/elliott_wave_bot' /opt/elliott_wave_bot
```

3. Запустите:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dashboard.service
sudo systemctl start dashboard.service
```

4. Проверка:
```bash
sudo systemctl status dashboard.service
```

## 📱 Доступ из сети

По умолчанию дашборд доступен только локально (`127.0.0.1`).

Для доступа из сети измените `DASHBOARD_HOST=0.0.0.0` в service файле или переменных окружения.

**⚠️ Внимание**: Убедитесь, что настроен firewall, если открываете доступ из сети!

## 🐛 Решение проблем

### Порт занят
```bash
# Проверьте, что использует порт
sudo lsof -i :5000

# Или измените порт через переменную окружения
export DASHBOARD_PORT=8080
```

### Ошибки импорта
```bash
# Убедитесь, что зависимости установлены
pip install flask flask-cors
```

### Нет данных
- Проверьте, что бот работает и создает `signals_history.csv`
- Убедитесь, что файл существует и доступен для чтения

## 📈 Автообновление

Дашборд автоматически обновляет данные каждые 30 секунд.

Для ручного обновления нажмите кнопку "🔄 Обновить".

---

**Готово!** Теперь у вас есть веб-интерфейс для мониторинга бота! 🎉
















