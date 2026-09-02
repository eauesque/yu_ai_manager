# Einstellungen API

APIs zum Verwalten von Anwendungseinstellungen, geheimer Verschlüsselung und Integration mit externem Password Manager (1Password / Bitwarden).

Geheimwerte werden in GET-Antworten immer maskiert (`****`). Das Feld `source` zeigt an, von welchem Backend der Wert aufgelöst wurde.

## Authentifizierung

Alle Endpunkte erfordern PIN-Authentifizierung oder API-Schlüssel-Authentifizierung.

---

## GET /api/settings/schema

Abrufen der vollständigen Einstellungs-Schema-Definition. Gibt Schlüsselnamen, Typen, Standards, Kategorien und andere Metadaten für alle Einstellungen zurück.

### Parameter

Keine

### Antwort

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `key` | string | Einstellungs-Schlüssel (Punkt-separiert, z.B. `github.token`) |
| `type` | string | Wertyp (`str`, `int`, `float`, `bool`) |
| `default` | any | Standardwert |
| `category` | string | Kategoriename |
| `secret` | bool | Ob dies ein Geheimwert ist |
| `label` | string | Anzeige-Etikett |

---

## GET /api/settings/all

Alle Einstellungswerte abrufen. Geheimwerte werden in maskierter Form zurückgegeben.

### Parameter

Keine

### Antwort

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `key` | string | Einstellungs-Schlüssel |
| `value` | any | Aktueller Wert (maskiert wenn Geheimnis) |
| `source` | string | Werquelle: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Ob dies ein Geheimwert ist |
| `category` | string | Kategoriename |

---

## GET /api/settings/\<key\>

Einen einzelnen Einstellungswert abrufen. Der Schlüssel verwendet Punkt-separiertes Pfadformat (z.B. `github.token`).

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key` | string | Einstellungs-Schlüssel (Pfad-Parameter) |

### Antwort

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 404 | `not_found` | Unbekannter Einstellungs-Schlüssel |

---

## PUT /api/settings/\<key\>

Aktualisieren Sie einen Einstellungswert. Geheimwerte werden automatisch verschlüsselt. Geben Sie optional einen 1Password URI an, um das Geheimnis extern zu verwalten.

### Ratenumgrenzung

DESTRUCTIVE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key` | string | Einstellungs-Schlüssel (Pfad-Parameter) |

### Anfrage

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `value` | any | Ja | Der einzustellende Wert. Wird automatisch in den vom Schema definierten Typ konvertiert |
| `op_uri` | string | Nein | 1Password URI. Wenn angegeben, speichert eine `op_secrets`-Zuordnung statt des Wertes |

### Antwort

```json
{
  "key": "github.token",
  "updated": true
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `bad_request` | Anfragekörper fehlt `value` |
| 404 | `not_found` | Unbekannter Einstellungs-Schlüssel |

---

## GET /api/settings/secrets/status

Rufen Sie den Verschlüsselungs-Schlüssel-Backend-Status ab. Zeigt, welche Schlüsselverwaltungsmethode derzeit verwendet wird.

### Parameter

Keine

### Antwort

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `backend` | string | Aktueller Schlüssel-Backend (`keychain` / `passphrase` / `file`) |
| `available` | bool | Ob Verschlüsselung verfügbar ist |
| `keychain_supported` | bool | Ob OS Keychain unterstützt wird |

---

## POST /api/settings/secrets/export

Exportieren Sie den Verschlüsselungs-Schlüssel als passwortgeschütztes JSON. Wird für Sicherung oder Migration in eine andere Umgebung verwendet.

### Ratenumgrenzung

DESTRUCTIVE

### Anfrage

```json
{
  "password": "my-export-password"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `password` | string | Ja | Passwort zum Schutz der exportierten Daten |

### Antwort

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `bad_request` | Anfragekörper fehlt `password` |
| 400 | `export_failed` | Export-Operation fehlgeschlagen |

---

## POST /api/settings/secrets/import

Importieren Sie einen Verschlüsselungs-Schlüssel aus zuvor exportierten Daten.

### Ratenumgrenzung

DESTRUCTIVE

### Anfrage

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `export_data` | string | Ja | Die Daten, die während des Exports erhalten wurden |
| `password` | string | Ja | Das Passwort, das während des Exports festgelegt wurde |

### Antwort

```json
{
  "success": true,
  "message": "Schlüssel erfolgreich importiert"
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `bad_request` | `export_data` oder `password` fehlt |
| 400 | `import_failed` | Falsches Passwort oder beschädigte Daten |

---

## POST /api/settings/secrets/migrate-keychain

Migrieren Sie den Verschlüsselungs-Schlüssel vom Datei-Backend zum OS Keychain. Unterstützt macOS Keychain, Windows Credential Manager und Linux Secret Service.

### Ratenumgrenzung

DESTRUCTIVE

### Anfrage

Keine (kein Körper erforderlich)

### Antwort

```json
{
  "success": true,
  "message": "Schlüssel zu OS Keychain migriert"
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `migration_failed` | Keychain nicht verfügbar oder Migration fehlgeschlagen |

---

## GET /api/settings/op-status

Abrufen des 1Password CLI (`op`) Verbindungsstatus.

### Parameter

Keine

### Antwort

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `available` | bool | Ob `op` Befehl auf PATH vorhanden ist |
| `signed_in` | bool | Ob bei 1Password angemeldet |
| `version` | string | `op` CLI-Version |

---

## GET /api/settings/secrets/op-vaults

Liste verfügbarer 1Password Tresore.

### Parameter

Keine

### Antwort

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI nicht verfügbar |

---

## POST /api/settings/secrets/push-to-op

Batch-Schreiben Sie alle Geheim-Einstellungen zu 1Password und speichern Sie `op_secrets`-Zuordnungen in config.json.

### Ratenumgrenzung

DESTRUCTIVE

### Anfrage

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `vault` | string | Ja | Ziel-1Password-Tresor-Name |
| `item_title` | string | Nein | 1Password Element-Titel. Standard: `YU AI Manager` |
| `remove_local` | bool | Nein | Wenn `true`, entfernt lokal verschlüsselte Werte aus config.json nach dem Push. Standard: `false` |

### Antwort

```json
{
  "message": "2 Geheimnisse zu 1Password gepusht",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `bad_request` | `vault` fehlt |
| 400 | `no_secrets` | Keine Geheimnisse zum Pushen |
| 500 | `op_push_failed` | Schreiben zu 1Password fehlgeschlagen |
| 503 | `op_unavailable` | 1Password CLI nicht verfügbar |

---

## DELETE /api/settings/op-mapping/\<key\>

Entfernen Sie eine 1Password URI-Zuordnung und kehren Sie zur lokalen Verschlüsselung zurück.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key` | string | Einstellungs-Schlüssel (Pfad-Parameter) |

### Antwort

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 404 | `not_found` | Schlüssel nicht in `op_secrets`-Zuordnung gefunden |

---

## GET /api/settings/bw-status

Abrufen des Bitwarden CLI (`bw`) Verbindungsstatus.

### Parameter

Keine

### Antwort

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `available` | bool | Ob `bw` Befehl auf PATH vorhanden ist |
| `status` | string | Bitwarden Sitzungsstatus |

---

## GET /api/settings/secrets/bw-folders

Liste verfügbarer Bitwarden Ordner.

### Parameter

Keine

### Antwort

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI nicht verfügbar |

---

## POST /api/settings/secrets/push-to-bw

Batch-Schreiben Sie alle Geheim-Einstellungen zu Bitwarden und speichern Sie `bw_secrets`-Zuordnungen in config.json.

### Ratenumgrenzung

WRITE

### Anfrage

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `folder_id` | string/null | Nein | Ziel-Bitwarden-Ordner-ID. Weglassen für keinen Ordner |
| `item_name` | string | Nein | Bitwarden Element-Name. Standard: `YU AI Manager` |

### Antwort

```json
{
  "message": "2 Geheimnisse zu Bitwarden gepusht",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 400 | `no_secrets` | Keine Geheimnisse zum Pushen |
| 500 | `bw_push_failed` | Schreiben zu Bitwarden fehlgeschlagen |
| 503 | `bw_unavailable` | Bitwarden CLI nicht verfügbar |

---

## DELETE /api/settings/bw-mapping/\<key\>

Entfernen Sie eine Bitwarden-Zuordnung und kehren Sie zur lokalen Verschlüsselung zurück.

### Ratenumgrenzung

WRITE

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key` | string | Einstellungs-Schlüssel (Pfad-Parameter) |

### Antwort

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Fehler

| Status | Code | Beschreibung |
|--------|------|-------------|
| 404 | `not_found` | Schlüssel nicht in `bw_secrets`-Zuordnung gefunden |
