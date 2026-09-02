# Руководство по развёртыванию и эксплуатации

Инструкции по эксплуатации YU AI Manager в производственной среде.

## 1. Обзор

Основные варианты развёртывания:

| Вариант | Применение | Конфигурация |
|---------|-----------|-------------|
| Прямой запуск | Личное использование / разработка | Python + venv |
| Docker | Серверная эксплуатация | docker-compose с Quart + Nginx |
| Обратный прокси | Публикация во внешнюю сеть | За существующим веб-сервером |

Данные хранятся в `data/tags.db` (SQLite). Внешний сервер БД не нужен.

---

## 2. Прямой запуск (разработка / личное использование)

### Настройка

```bash
# Получить репозиторий
git clone <repository-url> && cd yu_ai_manager

# Создать виртуальное окружение Python
python -m venv venv

# Активировать
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Установить зависимости
uv pip install -r requirements.txt

# Собрать фронтенд
pnpm install && pnpm run build

# Запустить
python web_ui.py --db data/tags.db
```

Открыть браузер по адресу `http://localhost:5000`.

### systemd-сервис (Linux)

```ini
# /etc/systemd/system/yu-ai-manager.service
[Unit]
Description=YU AI Manager
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/yu_ai_manager
ExecStart=/opt/yu_ai_manager/venv/bin/python web_ui.py --db data/tags.db --lan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yu-ai-manager
```

---

## 3. Развёртывание через Docker

### Быстрый старт

```bash
cp config.json.example config.json
mkdir -p data
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Доступ через `http://localhost` (через Nginx).

### Монтирование томов

| Хост | Контейнер | Назначение |
|------|-----------|-----------|
| `data/` | `/app/data/` | Хранение файла DB |
| `config.json` | `/app/config.json` | Конфигурация (только чтение) |

Добавьте папки с изображениями через `docker-compose.prod.yml`:

```yaml
volumes:
  - /path/to/images:/images:ro
```

---

## 4. Конфигурация обратного прокси

### Ключевые моменты Nginx

- **Статика**: Прямая отдача `/static/` через Nginx (минуя Quart)
- **SSE**: Для `/api/events/` отключить буферизацию `proxy_buffering off`
- **Лимит загрузки**: `client_max_body_size 100m`
- **Gzip**: Сжатие JSON, CSS, JS

### SSL/TLS

**Вариант 1: Проксирование через Cloudflare / Caddy / Traefik (рекомендуется)**

```
Клиент --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

### Настройка Trusted Proxy

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

---

## 5. Настройка аутентификации

### PIN-аутентификация

```json
{ "pin": "your-secret-pin" }
```

При публикации в LAN (`--lan` или байндинг `0.0.0.0`) PIN обязателен.

### API-ключ

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

---

## 6. Резервное копирование и восстановление

| Файл | Содержание |
|------|-----------|
| `data/tags.db` | SQLite DB со всеми метаданными, тегами и настройками |
| `config.json` | Настройки приложения |
| `data/secret.key`, `data/secret.salt` | Ключи шифрования |

```bash
# Копирование DB (безопасно при работающем сервере)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"
```

---

## 7. Процедура обновления

```bash
# 1. Остановить сервер
# 2. Обновить код
git pull

# 3. Обновить зависимости
uv pip install -r requirements.txt

# 4. Пересобрать фронтенд
pnpm install && pnpm run build

# 5. Запустить сервер
python web_ui.py --db data/tags.db
```

Миграция схемы DB выполняется автоматически при запуске.

---

## 8. Мониторинг и логи

### Стриминг логов

Вкладка Settings > Logs для просмотра логов в реальном времени.

### Проверка работоспособности

```bash
curl http://localhost:5000/api/server-info
```

Возвращает версию, версию схемы DB и другую информацию. Используйте для health check систем мониторинга.
