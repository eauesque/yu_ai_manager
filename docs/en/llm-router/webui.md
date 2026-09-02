# LLM Router WebUI

An admin dashboard accessible at `/llm-router`. It allows you to check the status of registered backends and enable/disable them.

---

## Page Layout

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Summary cards
├─────────┴─────────┴────────┴─────────┤
│  Backends table                      │
├───────────────────────────────────────┤
│  Routing Aliases table               │
└───────────────────────────────────────┘
```

### Summary Cards (4)

| Card | Content |
|---|---|
| **Backends** | Total number of backends registered in the catalog |
| **Enabled** | Number of backends that are not disabled |
| **Models** | Total number of models exposed by all backends |
| **Routing aliases** | Number of aliases defined in the configuration file |

Card values are automatically rendered by fetching `/api/llm_router/status` on page load.

---

## Backends Table

Each row corresponds to a single physical backend (e.g. an Ollama instance).

### Column Descriptions

| Column | Description |
|---|---|
| **Alias** | A unique short name identifying the backend (e.g. `ollama-mac`, `mdns-pi5-hailo`). Used as the key for routing configuration and alias resolution |
| **Base URL** | The base URL of the backend's OpenAI-compatible endpoint (e.g. `http://192.168.1.10:11434`) |
| **Status** | Connectivity status of the backend. See details below |
| **SLO** | Resource load status of the backend (`vision_idle` / `vision_active` / `unknown`). Used for Hailo Vision backends |
| **Models** | Number of models retrieved in the last probe. May be expandable to show a detailed list depending on implementation |
| **Last Seen** | Date and time of the last successful response (ISO 8601). `null` if no successful response has ever been received |
| **Actions** | Per-backend action buttons (see below) |

### Status Values

| Value | Meaning |
|---|---|
| `ready` | The last probe succeeded and the model list has been retrieved |
| `unreachable` | A connection timeout or error occurred |
| `unknown` | No probe has been executed yet (e.g. right after startup) |
| `probing` | A probe is currently in progress (may appear briefly in the UI during a Refresh) |

> **Hint**: `unreachable` backends are excluded from routing but remain in the catalog. After network recovery, run Refresh All or an individual Refresh to restore them to `ready`.

### SLO Values

| Value | Meaning |
|---|---|
| `vision_idle` | Vision task is idle. LLM load is low |
| `vision_active` | A Vision task is running. The LLM router may prioritize other backends |
| `unknown` | SLO information is unavailable (non-Hailo backend, or retrieval failed) |

---

## Refresh All Button

Click **Refresh All** in the upper right to force a probe on all backends, updating their model lists and statuses.

- The button is disabled during execution and the page re-renders on completion
- Internal behavior: Calls `POST /api/llm_router/refresh` (no body) to execute `discover_all` for all backends
- Individual backend refreshes may be available via a Refresh button in the Actions column (implementation-dependent)

---

## Disabling / Enabling Individual Backends

### Steps

1. Look at the **Actions** column in the backends table
2. Click the **Disable** button on the row of the backend you want to disable
3. The button changes to **Enable** and the row is grayed out
4. To re-enable, click **Enable**

### Behavior and Persistence

- Changes are immediately reflected in the in-memory catalog
- Simultaneously, an atomic write is made to `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- The disabled state is preserved across application restarts
- If an mDNS-discovered backend was disabled before startup, the disabled state is automatically applied after discovery (`_pending_disabled` mechanism)
- If the write fails, the in-memory state is rolled back to avoid inconsistency with disk

### Behavior of Disabled Backends

- Excluded from routing in OpenAI-compatible endpoints such as `/v1/chat/completions`
- Direct routing to a disabled backend returns `503 Service Unavailable`
- Disabled backends still appear in the WebUI table (for status visibility and re-enabling)

---

## Routing Aliases Table

Displays the mapping between logical model names and physical model IDs as defined in the configuration file.

| Column | Description |
|---|---|
| **Alias** | The logical name clients specify in the `model` parameter (e.g. `default-llm`, `fast-chat`) |
| **Physical Model** | The physical model ID that actually processes the request (format: `backend-alias/model-name`, e.g. `ollama-mac/qwen2.5:7b`) |

### Role of Aliases

Aliases allow you to switch backends or models without changing client code.

- Clients send requests using a logical name like `"model": "default-llm"`
- The LLM Router resolves `default-llm → ollama-mac/qwen2.5:7b` and proxies the request
- When migrating a backend to another machine, just change the alias target

Aliases are statically defined in the configuration file, and the WebUI displays them in read-only mode. Changes require editing the configuration file and restarting the application.

---

## Common Operations

### When a Backend is Unreachable

1. Verify that the backend service (Ollama, etc.) is running
2. Run **Refresh All** or an individual Refresh
3. If the issue persists, check the error details in the `last_error` column (or API response)

### Permanently Disabling an mDNS-discovered Backend

1. Click **Disable** in the Actions column of the target backend
2. The alias is saved in `data/llm_router_state.json`, so it remains disabled even after re-discovery

### Temporarily Stopping Load on a Specific Backend

Use **Disable** to immediately exclude it from routing, then **Enable** to restore it when done. No restart is needed.
