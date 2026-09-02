# Peer PIN Authentication & Token Pairing

**Implementation Version**: 4.92.0
**Related Files**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Overview

Before v4.92, peers on the LAN were identified solely by the `X-Peer-Id` header.
Since this header can be forged by anyone on the same network, security was insufficient.

Starting with v4.92, the system has migrated to **PIN approval-based token pairing**.

- On first connection, a "pairing request" is sent to the remote peer
- The remote administrator approves the request in the admin UI, generating a 6-digit PIN
- Entering the PIN issues a Bearer token (valid for 30 days)
- Subsequent communications are authenticated with `Authorization: Bearer <token>`

The legacy `X-Peer-Id` header method can be retained for compatibility via settings, but DELETE operations always require the new authentication.

---

## Pairing Flow

```
[Peer A (initiator)]                  [Peer B (target)]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                           Admin reviews in /lan-cowork/peers and approves
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (6-digit PIN, valid for 5 min)     |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer token, valid for 30 days)  |
       |                                      |
       |--- Subsequent: Authorization: Bearer <token>
```

### Step Details

| Step | Endpoint | Description |
|------|----------|-------------|
| 1. Send request | `POST /api/lan/pair/request` | Send peer ID, display name, and public key |
| 2. Await approval | — | Admin reviews the request in `/lan-cowork/peers` |
| 3. PIN issued | — | Admin clicks Approve to generate a 6-digit PIN (valid 5 min) |
| 4. PIN verification | `POST /api/lan/pair/verify` | Submit PIN and receive Bearer token |
| 5. Authenticated comms | — | Attach `Authorization: Bearer <token>` header |

---

## Admin UI (`/lan-cowork/peers`)

### Pending Requests

When a new peer sends a pairing request, it appears in the "Pending" tab of the admin UI.

- **Approve**: Generates a PIN and notifies the requesting peer via SSE
- **Reject**: Deletes the request. The requesting peer receives 403

### Connected Peers List

Displays all paired peers and the expiration date of each token.

| Column | Content |
|--------|---------|
| Display Name | Peer name |
| IP Address | Last observed source IP |
| Expires | Bearer token expiration (30 days) |
| Last Seen | Timestamp of last heartbeat |
| Actions | Revoke token button |

### Token Revocation

Clicking "Revoke" immediately invalidates the target peer's Bearer token.
On the next communication attempt, the peer receives 401 and automatically initiates re-pairing.

---

## Configuration

Settings are in the `lan_cowork` section of `config.json`, or via the "LAN Cowork" tab in the settings UI.

### `ip_check_mode`

Specifies how the source IP address is validated.

| Value | Behavior |
|-------|----------|
| `strict` | Only allow exact IP match from token issuance time (default) |
| `cidr` | Allow IPs within the CIDR range specified by `allowed_cidr` |
| `rfc1918` | Allow all private IP addresses (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Whether to retain compatibility with the legacy `X-Peer-Id` header authentication.

- `true`: Allow some operations with `X-Peer-Id` header only (default: `true`)
- `false`: Reject all connections without a Bearer token

> **Note**: Operations using the `DELETE` method (stop scan, force delete, etc.) always require a Bearer token, regardless of `allow_legacy_auth`.

### `protect_heartbeat`

Whether to require authentication for the heartbeat endpoint (`/api/lan/heartbeat`).

- `true`: Bearer token required for heartbeats too
- `false`: Heartbeats pass through without authentication (default: `false`)

Since heartbeats are sent frequently, `false` prevents delays in detecting token expiration.

### `protect_events`

Whether to require authentication for the SSE event stream (`/api/events/`).

- `true`: Bearer token required for SSE connections too
- `false`: SSE passes through without authentication (default: `false`)

---

## Security Notes

### Token Hashing

Issued Bearer tokens are **not stored in plain text** in the database.
They are stored after being hashed with scrypt (N=16384, r=8, p=1).
Even if the database is leaked, the original tokens cannot be recovered.

### Log Masking

- `Authorization: Bearer <token>` headers are automatically replaced with `Bearer [REDACTED]` in logs
- PIN codes are also never logged

### Rate Limiting

The following rate limits apply to prevent DoS attacks and brute-force attempts:

| Endpoint | Limit |
|----------|-------|
| `POST /api/lan/pair/request` | 10 requests/min/IP |
| `POST /api/lan/pair/verify` | 30 requests/min/IP |

PINs expire automatically after 5 minutes and can only be verified once per request.

---

## Troubleshooting

### Pairing Request Not Received

- Verify the remote peer's URL is configured correctly
- Check that the port is not blocked by a firewall
- Check the remote peer's logs for `pair/request` receipt status

### PIN Expired

PINs are valid for 5 minutes. If expired, click the "Approve" button again in the admin UI to generate a new PIN.

### Token Suddenly Stopped Working

Possible causes:

1. An administrator revoked the token in the admin UI
2. The 30-day validity period expired
3. With `ip_check_mode: strict`, the IP address changed

Perform re-pairing to resolve.

### After Setting `allow_legacy_auth` to `false`, Can No Longer Connect

If existing peers are still using the legacy authentication method, all of them will receive 401.
Complete re-pairing on each peer before setting `allow_legacy_auth: false`.
