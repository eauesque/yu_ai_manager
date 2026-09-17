# Руководство по эксплуатации Hailo Auto-Reboot Phase 0.5

**Создано**: 2026-05-17 (v4.215.0)
**Цель**: Эксплуатация наблюдения за утечкой CMA на Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0
**Статус**: Фаза наблюдения. Фактическая перезагрузка не выполняется; записываются только события `would_fire`.

---

## 1. Цель Phase 0.5

Phase 0.5 — это фаза наблюдения за дизайном автоматической перезагрузки против утечек CMA в HailoRT 5.3.0 + `hailo1x_pci`.

В этой фазе конечный автомат вычисляет следующие состояния:

| Состояние | Условие |
|---|---|
| `idle` | Нормальное состояние |
| `prewarn` | `CmaFree < 80 МБ` сохраняется в течение 180 секунд |
| `draining` | `CmaFree < 30 МБ` сохраняется в течение 60 секунд, или предварительный отказ `acquire_genai` происходит 3 раза подряд |
| `would_fire` | Прошло 120 секунд с момента `draining` |

Важно: В Phase 0.5 даже при достижении `would_fire` Pi НЕ перезагружается. Событие только записывается в формате JSON Lines в `logs/hailo_auto_reboot.log`.

---

## 2. Почему значение по умолчанию — `mode = "off"`

Значение по умолчанию `hailo.auto_reboot.mode` равно `"off"`. Поскольку автоматическая перезагрузка может прервать работу оператора, наблюдение запускается только в средах, где оператор явно дал согласие (opt-in).

Рекомендуемая конфигурация для Phase 0.5:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` является обязательным условием Phase 0.5. Фактический путь перезагрузки обрабатывается в Phase 4 и далее.

### 2.1 Процедура opt-in

Конфигурация запуска отдаёт приоритет файлу, указанному через `--config` или `TAGDB_CONFIG`. Если не указано, читается `config.json` в корневом каталоге репозитория, затем `tagdb_config.json`.

Пример:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Добавьте следующие настройки в `<repo>/config.json` или в JSON-файл, указанный через `--config` / `TAGDB_CONFIG` во время эксплуатации:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Перезапустите сервер для применения конфигурации. Сохраните аргументы, которые вы фактически используете, в соответствии с вашим методом запуска.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

При эксплуатации с systemd перезапустите соответствующий юнит:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Процедура отключения

Верните `hailo.auto_reboot.mode` в значение `"off"` в той же конфигурации и перезапустите сервер.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

При `mode = "off"` события наблюдения в формате JSON Lines сохраняются, но сводка WARN не выводится в `error.log`.

---

## 3. Как читать журналы

Журналы наблюдения записываются в следующий файл:

```text
logs/hailo_auto_reboot.log
```

Формат — JSON Lines. Основные события:

| Событие | Значение |
|---|---|
| `boot_baseline` | Начальная точка наблюдения при запуске |
| `prewarn_entered` | Условие PREWARN выполнено |
| `drain_entered` | Условие DRAIN выполнено |
| `would_fire` | Точка, которая стала бы триггером перезагрузки в Phase 1+ |
| `drain_cleared` | CMA восстановлена, DRAIN снят |

Пример:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Примеры команд проверки:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Если `would_fire` происходит часто, это указывает на высокую вероятность того, что при текущих пороговых значениях потребуется перезагрузка Pi во время реальной эксплуатации. Напротив, если появляется только `prewarn_entered` без перехода к `drain_entered`, пороговые значения или время допуска можно перенастроить до Phase 1.

---

## 4. Процедура проверки API

Проверьте `/api/system/cma` с ключом API администратора.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Изучите `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` и `cma.auto_reboot.consecutive_rejects` в ответе.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Период наблюдения

Ориентировочный срок — 1–2 недели. Убедитесь, что период охватывает как минимум следующие сценарии:

- Обычное использование чата с LLM
- Длительное использование чата
- Операции, вызывающие сбои загрузки модели Hailo GenAI или предварительные отказы
- Первая загрузка после перезагрузки Pi

Наблюдение считается завершённым, когда можно агрегировать данные о частоте `prewarn_entered` / `drain_entered` / `would_fire` за 1–2 недели. После наблюдения изучите количество вхождений `would_fire`, причину `drain_entered` (`cma` / `rejects`) и скорость снижения `CmaFree`, чтобы окончательно определить пороговые значения перед развёртыванием Phase 1.

Пример агрегации:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Связанные документы

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
