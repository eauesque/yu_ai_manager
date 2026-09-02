# Настройка с Podman

Контейнерная среда YU AI Manager поддерживает как Docker, так и Podman.
Управляющие скрипты (`scripts/yu-docker.sh`, `tools/docker-build.sh`) автоматически определяют установленную среду выполнения.

---

## Предварительные требования

- Podman 4.0 или выше
- Плагин `podman compose` (Podman 4.7+) или `podman-compose` (через pip)

### Установка Podman

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install podman

# Fedora
sudo dnf install podman

# macOS (Homebrew)
brew install podman
podman machine init
podman machine start
```

---

## Базовое использование

### Через управляющий скрипт (рекомендуется)

Скрипт автоматически определяет Docker / Podman — команды те же, что для Docker.

```bash
./scripts/yu-docker.sh init
./scripts/yu-docker.sh build
./scripts/yu-docker.sh up
./scripts/yu-docker.sh logs
./scripts/yu-docker.sh down
```

### Прямые команды

```bash
# Сборка
podman build -t yu-ai-manager .

# Запуск (compose)
podman compose up yu-ai-manager -d

# Запуск (одиночный)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager
```

---

## Отличия от Docker и особенности

### Rootless-режим

Podman по умолчанию работает в rootless (без прав root).

| Параметр | Влияние | Решение |
|----------|---------|---------|
| Порты < 1024 | Недоступны в rootless | Порт 5000 — без проблем |
| Проброс устройств | Нужны права для `/dev/hailort0` и т.д. | `podman run --device` + права группы или `sudo podman` |
| Маппинг UID | UID `appuser` в контейнере ≠ UID хоста | При проблемах с правами тома: `podman unshare chown` |

### Проброс устройства Hailo

```bash
# Метод 1: Добавить пользователя в группу hailort
sudo usermod -aG hailort $USER

# Метод 2: Запуск с правами root
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Интеграция с systemd (серверная эксплуатация Linux)

```bash
# Генерация systemd-юнита после запуска контейнера
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Включение
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Автозапуск при загрузке
loginctl enable-linger $USER
```

---

## Устранение неполадок

### `podman compose` не найден

```bash
# Для Podman до 4.7 плагин не входит в комплект
uv pip install podman-compose
```

### Нет доступа к localhost из контейнера

В rootless Podman используйте `host.containers.internal` (аналог `host.docker.internal` в Docker).

---

## Сводка совместимости

| Файл | Совместим с Podman | Примечания |
|------|--------------------|-----------|
| `Dockerfile` | OK | Стандарт OCI |
| `docker-compose.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Проброс устройств — осторожно с правами |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Автоопределение |
| `scripts/yu-docker.sh` | OK | Автоопределение |
