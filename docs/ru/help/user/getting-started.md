# Начало работы

YU AI Manager — это WebUI-приложение для управления метаданными AI-генерированных изображений.

## Установка

### Требования

- Python 3.11 или выше
- Node.js 18 или выше (для сборки фронтенда)

### Процедура настройки

```bash
# Клонировать репозиторий
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Установить uv (первый раз)
pip install uv

# Создать виртуальное окружение Python и установить зависимости
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Собрать фронтенд
pnpm install
pnpm run build

# Опционально: Ускорение семантического поиска (для больших библиотек)
uv pip install faiss-cpu
```

## Запуск

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Откройте `http://localhost:5000` в браузере.

## Первоначальная настройка

1. **Регистрация папки для сканирования**: Добавить папку с AI-изображениями на вкладке Settings > Scan
2. **Запуск сканирования**: После добавления папки сканирование запустится автоматически
3. **Просмотр изображений**: Поиск и просмотр изображений на главной странице

## Публикация в LAN

Для доступа с других устройств:

1. Включить «LAN Access» на вкладке Settings > **Server**
2. Настроить PIN-аутентификацию (обязательна при публикации в LAN)
   Ввести цифры (4–8 знаков) в поле «PIN-код» на **вкладке Settings > Server**
3. Перезапустить сервер

С других устройств в сети: `http://<IP сервера>:5000`
