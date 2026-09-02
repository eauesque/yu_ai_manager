# LAN Cowork Network Behavior (What Happens on Your LAN)

> Target: Rust standalone (`yu-server`) v4.538.0 and later. For Python backend hybrid deployments,
> see "Differences from Python Version" at the end of this page.

This page summarizes **"what your machine starts doing on the network when LAN Cowork is enabled."**
Read it before changing any settings.

---

## Key Points

- **By default, it does nothing.** Rust standalone does not listen on or announce itself on the LAN
  unless explicitly enabled via the settings described below.
- When enabled, **your node becomes discoverable by other nodes on the same LAN.** This is intended
  behavior by design.
- **PIN presence does not stop discovery announcements.** See "PIN Relationship (Commonly Misunderstood)"
  for details.

---

## What Starts When Enabled

| Operation | Description |
|---|---|
| **UDP listen** | Binds to `0.0.0.0:19850` (all interfaces) |
| **Periodic announcements** | Every 10 seconds, sends a signed HELLO broadcast to `255.255.255.255:19850`. The content includes your node ID, public key, API port, hostname, and other details |
| **Register other nodes** | Verifies the signature of received HELLOs and records the sender node in your peer list (TOFU) |
| **Accept inbound HTTP** | Peer-specific endpoints (listed in the table below) start responding |
| **Local delivery** | Accepted peer events are delivered to the SSE stream (`/api/events/stream`) that logged-in screens subscribe to |
| **Expiration cleanup** | Every 60 seconds, stale pairing requests and plaintext PINs are removed from memory |

### Inbound Endpoints

| Endpoint | Authentication |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **No session required** (peer list lookup) |
| `GET /ext/lan_cowork/api/peer/status` | **No session required** (your node descriptor) |
| `POST /ext/lan_cowork/api/peer/register` | **No session required** (peer self-registration; the server validates the sender) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **No session required** (pairing initiation; unpaired peers cannot hold sessions) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Signature + nonce (Bearer not required) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Signature + Bearer token |

"No session required" means **login session is not required**, not **no authentication**. Unpaired
peers cannot hold sessions, so only these 5 routes are exceptions. All other routes require login
as usual.

---

## How to Enable or Disable

Switch it in the **`extensions` section** of `config.json`.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **If the key is absent, it is disabled** (Rust standalone).
- Changes take effect after **restart**.
- To temporarily switch, you can also use a startup option. Priority order is
  **command line > `config.json` > environment variable > default**.

| Method | Enable | Disable |
|---|---|---|
| Command line | `--native-daemon` | `--no-native-daemon` |
| Environment variable | `YU_LAN_COWORK_NATIVE_DAEMON=1` | Same with `=0` |

> Environment variables interpret only `1`, `true`, and `yes` as "enabled." `on` and `Y` are
> **treated as disabled**.

### Check if Enabled

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Response | Meaning |
|---|---|
| `200` | Enabled. Peer features are operational |
| `405` | **Disabled** (feature is not compiled in) |
| `503` | Enabled but not ready (node keys not yet generated, or initialization failed) |

> **Do not rely on the extension list shown in the UI.** The UI may show LAN Cowork as "enabled"
> based on bundled metadata, but this is **independent of whether the daemon is actually running.**
> Check the endpoint response above or look for the `native_daemon=...` line in startup logs to
> determine actual status.

---

## PIN Relationship (Commonly Misunderstood)

**It is not accurate to assume that if you do not set a PIN, nothing can be touched from the LAN.**

- **Correct**: Using `--lan` (listen on all interfaces) requires a PIN; without it, startup aborts.
  The default listen address is `127.0.0.1`, so **HTTP is not reachable from the LAN in normal startup.**
- **Note 1**: If you specify a LAN IP directly in `--host`, this PIN requirement check is bypassed.
  Moreover, without a PIN, the login gate itself opens, so **avoid exposing to the LAN without a PIN.**
- **Note 2**: **UDP announcements are independent of whether a PIN is set.** Once enabled, even a
  PIN-less node broadcasts its existence every 10 seconds on the LAN. A PIN limits only HTTP exposure.

In short, **PIN reduces HTTP exposure but does not stop discovery announcements.**

### When Listening Only on Loopback (v4.539.0 and Later)

If the listen address is loopback only (the default `127.0.0.1`, which also applies to the desktop version),
**this node does not announce itself on the LAN**. Other nodes could not connect even if it announced itself.
The following warning is logged once after startup (it is WARN, not INFO, so it is visible by default).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

To use it on the LAN, bind a LAN address or use `--lan` (`--lan` requires a PIN).

> Before v4.539.0, a loopback-only listener announced a LAN IP. Peers could discover it but could not
> connect, which is why this behavior was changed.

---

## Things to Know Before Enabling

- **Disabling does not automatically erase peer records recorded while enabled.** Additionally,
  **on first startup after enabling**, old peer records are cleaned (records not reachable for more
  than 7 days, and unpaired records older than 1 hour are deleted).
  We recommend backing up `tags.db` before switching.
- Received peer events flow to the SSE stream subscribed by logged-in screens. **The content is
  input from the remote node** (the sender ID is replaced with a server-authenticated value on the
  server side).
- Only **count, type, and sender ID** are logged; event content is not recorded.
- To check operational status, enable INFO log level (e.g., `RUST_LOG=yu_server=info`). With default
  settings, peer event reception is not logged.

---

## Differences from Python Version

| | Python backend hybrid | Rust standalone |
|---|---|---|
| Default | **Enabled** (enabled if missing from `config.json`) | **Disabled** (explicit enablement required) |
| Implementation | Python extension | `yu-server` |

**Rust standalone deliberately defaults to "disabled."** This avoids changing network behavior on
upgrade. Hybrid behavior remains unchanged from before.

> Older documentation recommended configuration at `{"lan_cowork": {"enabled": true}}` (top level),
> but **this key location is not read by any implementation.** The `extensions` section above is the
> correct location.
