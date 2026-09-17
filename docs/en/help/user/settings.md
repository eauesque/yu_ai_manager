# Settings

## Server Settings

| Option | Description |
|--------|-------------|
| Host | Bind address (locked to 127.0.0.1 when LAN Access is OFF) |
| Port | Web server port number |
| LAN Access | Enable access from other devices on the LAN |
| PIN Auth | Require PIN entry on access |
| Boss Mode | Newspaper-style PIN login screen |

## Scan Settings

Add, remove, reorder, and enable/disable registered scan folders.

## Parser Settings

| Option | Description |
|--------|-------------|
| Extract A1111 | Extract Stable Diffusion WebUI format metadata |
| Extract ComfyUI | Extract ComfyUI workflow metadata |
| Normalize tags | Normalize tags to lowercase |
| Compute hash | Compute file hashes (for duplicate detection) |
| FTS | Enable full-text search index |

## API Keys

Manage API keys for external tools (MCP server, scripts, agents).
Used with Bearer authentication.

## Appearance

Customize theme, accent color, background image, sound effects, and more.

## Encrypted Secret Store

Sensitive values such as PIN, Bluesky password, and webhook secrets are protected with Fernet encryption from the `cryptography` package.

- **Encryption format**: Strings prefixed with `enc:`
- **Compatibility**: Existing plaintext values continue to work (only new saves are encrypted)
- **Installation**: `uv pip install cryptography` (encryption is disabled if not installed)

### Key Backends

The encryption key is obtained in the following priority order:

1. **Passphrase** — Set the `YU_SECRET_PASSPHRASE` environment variable to derive a key via PBKDF2-HMAC-SHA256 (600,000 iterations). The salt is automatically saved to `data/secret.salt`
2. **OS Keychain** — If the `keyring` package is installed, the key is stored in Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **File** — `data/secret.key` (legacy compatible, auto-generated on first use)

```bash
# Example: setting a passphrase
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Using the keychain
uv pip install keyring
```

### Key Export/Import

For migration to another machine or backup, you can export/import the encryption key in a password-protected JSON format.

- `POST /api/settings/secrets/export` — Export protected with a password (8+ characters)
- `POST /api/settings/secrets/import` — Restore key from exported data and password
- `POST /api/settings/secrets/migrate-keychain` — Migrate from file to keychain
- `GET /api/settings/secrets/status` — Check backend status

### Migrating to Keychain

To migrate a file-stored key to the keychain, call `/api/settings/secrets/migrate-keychain`. After migration, `data/secret.key` is automatically deleted.

## 1Password CLI Integration

On systems with the `op` CLI installed, secrets can be dynamically retrieved from a 1Password Vault.

### Setup

1. Install the [1Password CLI](https://developer.1password.com/docs/cli/)
2. Sign in with `op signin`
3. Add an `op_secrets` mapping to `config.json`:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Configure via the Settings API or MCP tools using `op_uri`:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### Behavior

- When a key is registered in `op_secrets`, the secret is fetched via `op read`
- Retrieved values are cached in memory for 5 minutes
- Falls back to the local encrypted store if the `op` CLI is not available
- Check 1Password authentication status via `GET /api/settings/op-status`

## Settings MCP Tools

Settings can be managed from MCP clients (e.g., Claude Desktop).

| Tool | Description |
|------|-------------|
| `settings_get_schema` | Get schema for all settings (types, descriptions, categories) |
| `settings_get_all` | Get all setting values (secrets are masked) |
| `settings_get` | Get a single setting value |
| `settings_set` | Update a setting value (secrets are auto-encrypted) |
| `secrets_status` | Get encryption key backend status |
| `secrets_export` | Export key as password-protected JSON |
| `secrets_import` | Import key from exported data |
