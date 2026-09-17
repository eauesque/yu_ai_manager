# Setup LLM Router

## Добавление в config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Интеграция с Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

При выполнении запросов укажите alias или физическое имя в поле `model`:
- `local-fast` (alias)
- `ollama-local/qwen2.5:7b` (физическое имя)

## Интеграция с Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Автоматическое обнаружение узлов -- Поддержка имен хостов `.local` (Home LAN)

При запуске нескольких машин в домашней локальной сети (например, Mac mini + Pi5 + GPU машина Windows), вы можете использовать имена хостов `.local` вместо IP-адресов в `base_url`. Таким образом, **конфигурация продолжит работать, даже если DHCP переназначит IP-адреса**. На стороне yu_ai_manager не требуется никаких дополнительных реализаций -- `httpx` автоматически разрешает имена через resolver операционной системы (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Пример: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Требования

| ОС | Требуется |
|---|---|
| macOS | Bonjour (встроен, дополнительная установка не требуется) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 и выше может разрешать `.local` нативно. Если не работает, установите Bonjour Print Services) |

### Проверка

```bash
# Тест работы разрешения имен
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → Если вернет 192.168.x.x, то работает
```

### Cross-subnet / Corporate LAN / VPN

mDNS работает через L2 multicast, поэтому **не может достичь через маршрутизаторы, VPN или изолированные VLAN в корпоративных сетях**. В таких окружениях укажите IP-адреса напрямую как раньше:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Если вам нужен reflector mDNS в окружении с сегментированной VLAN, проконсультируйтесь с администратором LAN. yu_ai_manager не предоставляет reflector или proxy mDNS.

### Известные ограничения

- **Разрешение mDNS на Windows может быть медленным** (~1 секунда): Рекомендуется устанавливать backend `timeout` на 3 секунды или больше
- **Суффикс `.local` требуется**: Использование только `mac-mini` вернется к NetBIOS / DNS, поэтому всегда пишите `mac-mini.local`
- **Ollama не объявляет через mDNS**: Используется только разрешение имени хоста; порт (11434) должен быть указан вручную. Для Ollama расположенного с yu, v4.71.0 добавляет advertiser `_ollama._tcp.local.` на стороне yu. Для чистых Ollama узлов (без yu) смотрите "Обработка чистых Ollama узлов (без yu)" ниже для политики

## Переменные окружения

| Переменная | Поведение |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Установите на `1` для отключения всего Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Установите на `1` для отключения цикла обновления каждые 5 минут |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Переопределить на `none`/`loopback`/`api_key` |

## Многоязычная документация

Следуя `docs/ reading rules` в CLAUDE.md, версии `en/zh-tw/zh-cn/ko` синхронизируются на основе источника `ja/` (как отдельная задача после реализации; смотрите TODO.md).

## Автоматическое обнаружение узлов (Phase B -- v4.64.0 и выше)

Узлы yu_ai_manager на одной LAN автоматически обнаруживают друг друга через mDNS (`_yu-ai._tcp.local.`). Даже без ручного написания backends в `config.json`, обнаруженные узлы автоматически регистрируются в `BackendCatalog` с aliases `mdns-<prefix>`.

### Как это работает

1. При запуске `core/mdns/` объявляет `_yu-ai._tcp.local.`
2. Он подписывается на TXT записи других узлов и проверяет наличие необходимых ключей (version/node_id/llm_base_url)
3. Для узлов с совпадающей основной версией отправляет HTTP GET на `http://<addr>:<web_port>/api/mdns/identity` для подтверждения совпадения product/node_id/version
4. Проверенные узлы регистрируются в LLM Router как `BackendInfo(alias="mdns-<node_id[:8]>")`
5. Далее существующий цикл зондирования обрабатывает периодические обновления

### Предварительные условия

- Responder mDNS ОС должен быть запущен (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Узлы должны быть на одной L2 подсети (для cross-router / VPN сценариев используйте ручную конфигурацию из Phase A)
- UDP 5353 должен быть разрешен через локальный firewall
- **Ollama должен быть открыт для LAN** -- Ollama привязывается к `127.0.0.1:11434` по умолчанию, поэтому недоступен с других узлов LAN. Установите переменную окружения `OLLAMA_HOST=0.0.0.0:11434` перед запуском Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: systemd unit / `.bashrc`, Windows: системные переменные окружения). Если не установлено, yu_ai_manager определит, что это только localhost и не будет объявлять `llm_base_url` (в логе стартапа появится предупреждение)

### Автоматическое обнаружение Ollama

Если нет localhost entry в `llm_router.backends` в `config.json`, yu_ai_manager ищет Ollama при запуске в следующем порядке:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama доступный из LAN
2. `http://localhost:11434/api/tags` -- Даже если обнаружен, объявление LAN не выполняется (показывается предыдущее предупреждение)

Если возвращен ответ 200 из LAN IP, он автоматически включается как `llm_base_url` в TXT запись. Это предназначено для zero-configuration участия узлов с co-hosted Ollama через mDNS. Нестандартные порты (11435, и т.д.) или lmstudio / llamacpp по-прежнему требуют явных entries в `config.json`.

### Обработка чистых Ollama узлов (без yu) (политика)

Чистые Ollama узлы, где `yu_ai_manager` **не** запущен (например, Mac члена семьи, имеющий только Ollama, или контейнер Ollama на NAS) **не охватываются автоматическим обнаружением**. Сам Ollama не имеет функции, объявляющей `_ollama._tcp.local.` официально, поэтому структурно нет способа их обнаружить.

Для использования таких узлов из LLM Router, сконфигурируйте их **вручную** одним из:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Если ваше окружение поддерживает имена хостов `.local` (смотрите "Автоматическое обнаружение узлов -- Поддержка имен хостов `.local`" выше), предпочитайте это
- В противном случае hard-code фиксированный IP

#### Почему автоматическое обнаружение не пытается

При проектировании этого (2026-04-11) были сравнены следующие три варианта, и вариант (c) руководство по ручной конфигурации был выбран:

| Вариант | Описание | Решение |
|---|---|---|
| (a) Сканирование всей LAN `:11434` при запуске | Brute-force зондирование всех хостов в подсети | **Отклонен** -- тяжелая сетевая нагрузка, деструктивен на корпоративных / больших LAN, может быть ошибочно принят за port scanning, противоречит edge-first философии |
| (b) Внешний Ollama advertiser daemon | Отправьте lightweight yu-provided advertiser, работающий рядом с каждым Ollama хостом | **Отклонен** -- требует дополнительный resident процесс, что эквивалентно установке `yu_ai_manager` самого. Аннулирует смысл "чистого" |
| (c) Ручная конфигурация backend через фиксированный IP / `.local` | Записи вручную в `config.json` | **Выбран** -- нулевая дополнительная реализация, явное поведение, избегает втягивания пользователей в незаинтересованные сканирования |

Если Ollama upstream позже официально объявит `_ollama._tcp.local.` или добавит официальный механизм service discovery, мы пересмотрим это как Phase D в то время.

### Отключение

Вы можете отключить автоматическое обнаружение в окружениях, где это не требуется (Docker изоляция, корпоративная LAN, CI, и т.д.):

- Добавьте `"mdns": {"enabled": false}` в `config.json`
- Или установите переменную окружения `YU_AI_MDNS_DISABLED=1`

### Известные поведения

- **Multi-homed окружения (Wi-Fi + Ethernet)**: С стандартной конфигурацией (`bind_address: null`), объявление происходит на обоих интерфейсах и `PeerInfo.addresses` будет содержать несколько IP. Для ограничения одним интерфейсом, укажите `"bind_address": "192.168.x.y"`.
- **Collision alias**: Если backend в `config.json` использует alias в формате `mdns-xxxxxxxx`, ручная конфигурация имеет приоритет и обнаруженная через mDNS запись пропускается.
- **Cross-subnet**: mDNS работает только в L2 broadcast domain по умолчанию. Для cross-subnet операции, используйте approach с именем хоста `.local` из Phase A.
- **Безопасность**: mDNS сам не имеет аутентификации. Он разработан для доверенных окружений, таких как home LANs. Отключение рекомендуется на открытом Wi-Fi или больших shared networks. Проверка `/api/mdns/identity` предотвращает случайное неправильное определение узлов или смешивание несовместимых старых версий.
