# Einstellungen

## Server-Einstellungen

| Element | Beschreibung |
|---------|----------|
| Host | Bind-Adresse (wenn LAN aus, dann 127.0.0.1 fest) |
| Port | Web-Server-Portnummer |
| LAN Access | AN ermöglicht Zugriff von anderen LAN-Geräten |
| PIN Auth | Verlangt PIN-Eingabe beim Zugriff |
| Boss Mode | Zeigt Zeitungs-ähnlichen PIN-Login-Bildschirm |

## Scan-Einstellungen

Registrierte Ordner hinzufügen/entfernen/neu ordnen/aktivieren/deaktivieren.

## Parser-Einstellungen

| Element | Beschreibung |
|---------|----------|
| Extract A1111 | Stable Diffusion WebUI Format-Metadaten extrahieren |
| Extract ComfyUI | ComfyUI Workflow-Metadaten extrahieren |
| Normalize tags | Tags auf Kleinbuchstaben normalisieren |
| Compute hash | Datei-Hash für Duplikat-Erkennung berechnen |
| FTS | Volltextindex-Suche aktivieren |

## API-Schlüssel

Verwalten Sie API-Schlüssel für externe Tools (MCP-Server, Skripte, Agenten). Wird mit Bearer-Authentifizierung verwendet.

## Erscheinungsbild

Passen Sie Theme, Akzentfarbe, Hintergrundbild, Soundeffekte usw. an.

## Verschlüsselt geheime Datenspeicher

PIN, Bluesky-Passwort, Webhook-Geheimnisse usw. werden mit Fernet-Verschlüsselung aus `cryptography` geschützt.

- **Verschlüsselungsformat**: String mit `enc:` Präfix
- **Kompatibilität**: Bestehende unverschlüsselte Werte funktionieren (nur neue Speicherung ist verschlüsselt)
- **Installation**: `uv pip install cryptography` (deaktiviert, wenn nicht installiert)

### Schlüssel-Backend

Verschlüsselungsschlüssel werden in dieser Priorität abrufen:

1. **Passphrase** — Umgebungsvariable `YU_SECRET_PASSPHRASE` setzen für PBKDF2-HMAC-SHA256 (600,000 Iterationen). Salz wird in `data/secret.salt` gespeichert
2. **OS Keychain** — Wenn `keyring` installiert, wird Schlüssel in Windows Credential Manager / macOS Keychain / Linux Secret Service gespeichert
3. **Datei** — `data/secret.key` (älter kompatibel, auto-generiert beim ersten Mal)

```bash
# Passphrase-Beispiel
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Keychain verwenden
uv pip install keyring
```

### Schlüssel exportieren/importieren

Für Migration auf andere Maschine oder Backup können Sie verschlüsselte Schlüssel (passwortgeschützt, JSON-Format) exportieren/importieren.

- `POST /api/settings/secrets/export` — Mit Passwort (8+ Zeichen) exportieren
- `POST /api/settings/secrets/import` — Mit Exportdaten und Passwort wiederherstellen
- `POST /api/settings/secrets/migrate-keychain` — Von Datei zu Keychain migrieren
- `GET /api/settings/secrets/status` — Backend-Status prüfen

### Migration zu Keychain

Für Migration von dateispeicherten Schlüsseln zu Keychain, rufen Sie `/api/settings/secrets/migrate-keychain` auf. Nach Migration wird `data/secret.key` automatisch gelöscht.

## 1Password CLI Integration

Wenn `op` CLI installiert ist, können Sie Geheimnisse dynamisch aus 1Password Vault abrufen.

### Einrichtung

1. [1Password CLI](https://developer.1password.com/docs/cli/) installieren
2. Mit `op signin` anmelden
3. `config.json` um `op_secrets` Mapping erweitern:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Über Settings API oder MCP-Tool `op_uri` mit Einstellungen setzen:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### Betrieb

- Wenn Schlüssel in `op_secrets` registriert ist, wird `op read` verwendet

