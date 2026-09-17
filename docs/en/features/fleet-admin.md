# Fleet Admin

The Fleet Admin feature for LAN Cowork lets you manage multiple yu-ai-manager nodes from a central location.

## Overview

- **Machine info collection**: Aggregate CPU/RAM/GPU/disk/version/uptime from all nodes
- **Remote log viewing**: Live-stream logs from any peer via SSE from the central UI
- **Version update distribution**: Instruct peers to run `git pull --ff-only` + graceful restart

## Prerequisites

- LAN Cowork extension enabled (`extensions["builtin-lan-cowork"].enabled = true`)
- Peers paired with each other
- Cloned as a git repository (for update feature)
- `psutil>=5.9` installed in the Python virtual environment

## Setup

### Chief node configuration

Add to `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ],
        "allow_log_stream_from": [
          "<paired peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Regular node configuration

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<chief peer_id>"
        ],
        "allow_log_stream_from": [
          "<chief peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Accessing the Fleet UI

Navigate to `/ext/lan_cowork/fleet/ui` on the chief node's browser.

This URL returns 404 on regular nodes.

## Tab Features

### Overview Tab

- Node cards with CPU/RAM/GPU/Disk usage bars
- Online / Offline / Info Unavailable status display
- `[CHIEF]` badge on chief node
- Auto-refresh every 30 seconds + manual refresh button
- Warning banner when multiple chiefs are detected

### Logs Tab

- Live log streaming from any peer via SSE (tail -f style)
- Level filter (DEBUG / INFO / WARNING / ERROR)
- Search box (client-side filter)
- Auto-scroll ON/OFF
- Pause / Resume

### Update Tab

- Version / git commit / branch comparison table
- Per-node "Pull & Restart" button
- Batch update dispatch for multiple nodes
- Progress display (precheck → fetching → pulling → restarting → online)
- Chief node excluded from batch update (individual button only)

## Security

Authorization uses a two-layer model:

1. **Pairing (identity)**: Bearer token identifies who is calling
2. **Allowlist (permission)**: Each operation requires explicit peer_id authorization

Being paired does NOT grant all permissions.

### Allowlist configuration example

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- Both string and `{peer_id: ...}` formats are accepted
- Your own peer_id is automatically included (no configuration needed)

## Chief Auto-Demotion

If multiple `chief = true` nodes start on the same network, the later one automatically demotes itself (after `chief_observation_sec` seconds of observation).

Manual restart with updated config is required to restore chief status (no auto-promotion).

## git Update Constraints

- Uses `git pull --ff-only` only (no merge/rebase)
- Returns `failed` immediately if fast-forward is not possible (working tree is not modified)
- Rejects updates if the working tree is dirty

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/fleet/ui` returns 404 | `chief = true` not set | Check config.json and restart |
| `/fleet/info` returns 500 | psutil not installed | `uv pip install psutil>=5.9` |
| `git_not_available` error | git missing or wrong PATH | Verify git installation |
| `postcheck_online` timeout after update | Restart took more than 3 min | Increase `postcheck_timeout_sec` |
| Multi-chief warning banner persists | Old chief process still running | Restart the old chief |

## API Reference

### All nodes

| Endpoint | Description |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | Machine info (Bearer auth required) |
| `GET /ext/lan_cowork/fleet/logs/stream` | Self log SSE (allowlist required) |
| `POST /ext/lan_cowork/fleet/update` | git pull + restart (allowlist required) |
| `GET /ext/lan_cowork/fleet/update/status` | Update job status |

### Chief node only

| Endpoint | Description |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | Aggregated peer info |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Relay peer log SSE |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Batch update dispatch |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Dispatch progress |
| `GET /ext/lan_cowork/fleet/ui` | Fleet admin UI |
