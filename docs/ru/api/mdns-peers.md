# API: /api/mdns (Обнаружение пиров)

> Целевая версия: v4.64.0 и позже (Hailo расширения: v4.66.0 и позже)

API для узлов yu_ai_manager на LAN для обнаружения друг друга через mDNS (`_yu-ai._tcp.local.`). Есть две конечные точки.

---

## GET /api/mdns/identity

### Обзор

Конечная точка самопрезентации для узла. Другие узлы вызывают это во время проверки пира, чтобы подтвердить, что информация, объявленная через mDNS, принадлежит действительному экземпляру yu_ai_manager.

### Аутентификация

**Обход аутентификации (не требуется).** Аутентификация намеренно опущена, так как эта конечная точка используется для взаимной проверки пира. Ответ содержит только информацию, уже общедоступную через mDNS. Не включены секреты или конфиденциальная информация.

### Ответ

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `product` | string | Всегда `"yu_ai_manager"` |
| `node_id` | string | Уникальный UUID узла |
| `version` | string | Версия приложения (читается из файла VERSION) |
| `capabilities` | string[] | Список доступных возможностей. В настоящее время только `"hailo"` |
| `hailo_ollama_url` | string (необязательно) | URL доступа LAN для Hailo-Ollama. Не включено, если LAN IP не может быть определен |

**Условие для `capabilities` включать `"hailo"`:** Бэкенд `"hailo-local"` зарегистрирован в каталоге LLM Router.

**Условие для `hailo_ollama_url` быть включенным:** Бэкенд `"hailo-ollama-local"` зарегистрирован в каталоге и может быть определен LAN IP. Адреса loopback (`127.0.0.1` и т.д.) переписываются на LAN IP.

---

## GET /api/mdns/peers

### Обзор

Возвращает список пиров LAN, обнаруженных этим узлом. Предназначено для проверки статуса подсистемы mDNS и отладки.

### Аутентификация

**Обход аутентификации (не требуется).** Ответ содержит только информацию, уже транслируемую на LAN через mDNS.

### Ответ (обычный)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Поле | Тип | Описание |
|---|---|---|
| `running` | bool | Работает ли подсистема mDNS |
| `status` | string | Строка состояния подсистемы |
| `self_node_id` | string | node_id этого узла |
| `peers` | object[] | Список обнаруженных пиров (см. таблицу ниже) |

**Элементы peers:**

| Поле | Тип | Описание |
|---|---|---|
| `node_id` | string | Уникальный UUID пира |
| `hostname` | string | Имя хоста mDNS |
| `version` | string | Версия приложения пира |
| `llm_base_url` | string \| null | URL конечной точки LLM пира |
| `llm_provider` | string \| null | Имя провайдера LLM (например `"ollama"`) |
| `capabilities` | string[] | Список возможностей пира |
| `web_port` | int \| null | Порт WebUI пира |
| `addresses` | string[] | IP адреса LAN пира |
| `hailo_ollama_url` | string \| null | URL Hailo-Ollama пира |
| `first_seen` | float \| null | Время первого обнаружения (Unix timestamp) |
| `last_seen` | float \| null | Время последней проверки (Unix timestamp) |

### Ответ (mDNS не инициализирован)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Когда `running: false`, mDNS либо отключен, либо инициализация не удалась. Проверьте конфигурацию и журналы запуска.

---

## Режим отладки

Запустите yu с переменной среды `TAGDB_DEBUG_TRUSTED_PEERS=1`, чтобы включить дополнительные поля в ответе `/api/mdns/peers`.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Поле | Описание |
|---|---|
| `trusted_ips` | Список IP адресов, зарегистрированных в реестре доверенных IP |
| `bridge.managed_aliases` | Список псевдонимов, управляемых мостом mDNS |
| `bridge.config_aliases` | Список псевдонимов, статически определенных в конфигурации |
| `bridge.cooldown_seconds_remaining` | Оставшиеся секунды охлаждения, ключ по первым 8 символам node_id |

**Предупреждение:** `trusted_ips` может служить целью атаки, поэтому по умолчанию не открывается. Не устанавливайте `TAGDB_DEBUG_TRUSTED_PEERS=1` в производственных средах.

---

## Поток обнаружения mDNS

```
Другой узел запускается
    │
    ▼
Объявляет mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge получает on_peer_added()
    │
    ▼
HTTP проверка через GET /api/mdns/identity
    │
    ├─ Успех → Регистрация в PeerRegistry / BackendCatalog
    └─ Ошибка → Повтор после охлаждения
```

---

## Связанные файлы

- `routes/mdns_identity.py` -- Реализация конечной точки
- `core/mdns/` -- mDNS сервис / утилиты адреса
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Реестр доверенных IP
- `docs/en/mesh-inference/overview.md` -- Общая архитектура сетевого вывода
