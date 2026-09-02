# LAN MCP-Zugriff & Help-Endpunkt-Spezifikation

**Implementierungsversion**: 3.1.0
**Zugehörige Dokumentation**: `docs/de/features/mcp-integration-guide.md`
**Zugehörige Dateien**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Übersicht

1. **LAN MCP-Zugriff** — Ermöglichen Sie MCP-Clients im LAN, sich mit dem MCP-Endpunkt per IP-Adresse zu verbinden, wenn LAN-Freigabemodus aktiviert ist
2. **`/help` Endpunkt** — Bieten Sie ein integriertes Web-Handbuch für die Anwendung an (auch als MCP-Ressource veröffentlicht)

---

## 1. LAN MCP-Zugriff

### 1-1. Architektur

Über das LAN verbinden sich MCP-Clients direkt mit dem YU AI Manager `/mcp` Endpunkt unter Verwendung von HTTP/SSE-Transport.

### 1-2. MCP SSE-Endpunkt

| Element | Details |
|------|------|
| Endpunkt | `/mcp` (SSE + Nachrichtenposting) |
| Transport | HTTP + Server-Sent Events (SSE) |
| Authentifizierung | Nicht erforderlich von localhost. API-Schlüssel erforderlich von LAN-IPs |

### 1-3. API-Schlüssel-Authentifizierung

Der bestehende API-Schlüssel-Verwaltungs-Mechanismus (`/api/keys`) wird wiederverwendet.

### 1-4. Einstellungen-UI

Ein LAN MCP-Verbindungs-Konfigurationscode-Snippet (HTTP-Version) wird zur Einstellungen > API-Schlüssel Registerkarte hinzugefügt.

---

## 2. `/help` Endpunkt

### 2-1. Design-Prinzipien

- Vollständig offline
- Dual-Zweck als MCP-Ressource
- Keine Authentifizierung erforderlich

### 2-2. Endpunkte

| Endpunkt | Inhalt |
|----------------|------|
| `GET /help` | Handbuch Titelseite |
| `GET /help/<section>` | Bereichs-spezifische Seite |
| `GET /api/help/toc` | Inhaltsverzeichnis JSON |
| `GET /api/help/content/<section>` | Bereichs-Body JSON |

### 2-3. MCP-Tools

- `help_search`: Schlüsselwortsuche
- `help_get_section`: Bereichs-Abruf
