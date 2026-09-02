# LAN Cowork

> Zielversion: v4.55.0 und später (PIN-Authentifizierung ab v4.92.0)

## Was ist LAN Cowork

LAN Cowork ist eine Erweiterungsfunktion, die die Koordination mehrerer yu_ai_manager-Knoten in einem Netzwerk ermöglicht.  
Jede Maschine läuft unabhängig, während schwere Verarbeitungsaufgaben verteilt oder als Fleet zentral verwaltet werden können.

```
┌──────────────┐     mDNS-Erkennung    ┌──────────────┐
│  Windows PC  │◄──────────────────────►│   Mac Mini   │
│ (GPU aktiv)  │   PIN-Kopplung        │  (Kontrolle) │
│              │◄──────────────────────►│              │
│  Verteilte   │                       │    Fleet-    │
│  Inferenz    │                       │  Verwaltung  │
│ (Tagger etc) │                       │              │
└──────────────┘                       └──────────────┘
        ▲                                      ▲
        └──────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Funktionsübersicht

| Funktion | Beschreibung |
|---|---|
| **mDNS-Autoerkennung** | Automatische Erkennung von Knoten im gleichen LAN ohne Konfiguration |
| **PIN-Kopplung** | Admin-genehmigter PIN-Auth für Ausstellung von Peer-Token |
| **Verteilte Inferenz** | Parallele Verarbeitung von Tagger, CLIP, YOLO und Whisper auf mehreren Knoten |
| **Generierungsverteilung** | SD WebUI / ComfyUI-Jobs an LAN-Knoten delegieren |
| **Fleet-Verwaltung** | Zentrale Verwaltung von Protokollen und Versionsupdates über alle Knoten |
| **Peer-Event-Relay** | Ereignisse anderer Knoten in Ihre eigene SSE einbinden |
| **LLM-Routing** | Automatische Registrierung entdeckter Peers im LLM Router |

---

## Einrichtungsschritte

### 1. Aktivierung

Hinzufügen zu `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Hinweis**: Diese Seite empfahl zuvor den Aktivierungsschlüssel auf oberster Ebene als `{"lan_cowork": {...}}`, aber keine Implementierung liest einen Schlüssel an dieser Stelle. Der obige Abschnitt `extensions` ist der richtige Ort.

> **Der Standardwert hängt vom Backend ab:** Das Python-Backend (hybrid) behandelt einen fehlenden Schlüssel als **aktiviert**, während der eigenständige Rust-Server ohne explizite Aktivierung **deaktiviert** ist. Was nach der Aktivierung tatsächlich im Netzwerk geschieht, beschreibt [Netzwerkverhalten](network-behavior.md).

Nach Neustart:
- Lauschen auf anderen Knoten auf UDP 19850
- Ankündigung von _yu-ai._tcp.local. über mDNS starten

### 2. Knoten verbinden

Um von Knoten A zu Knoten B zu verbinden:

1. **Knoten A WebUI** → `Einstellungen` → `LAN Cowork` → Knoten-B-URL hinzufügen
2. Knoten A sendet `POST /api/lan/pair/request`
3. **Knoten B WebUI** → `/lan-cowork/peers` → In Registerkarte "Genehmigung ausstehend" genehmigen
4. 6-stelliger PIN wird an Knoten A gesendet (via SSE)
5. Knoten A gibt PIN ein → Bearer-Token (30 Tage gültig) erhalten

> **Hinweis**: Kopplung ist unidirektional. Führen Sie sowohl A→B als auch B→A durch.

Weitere Informationen finden Sie unter [Peer-PIN-Authentifizierung und Token-Kopplung](peer-auth.md).

### 3. Betrieb überprüfen

```bash
# Liste der erkannten Peers (von Knoten A)
curl http://localhost:5000/api/mdns/peers

# Von LAN Cowork erkannte Peers
curl http://localhost:5000/api/lan/peers
```

---

## Funktionsspezifische Einrichtung

### Verteilte Inferenz

Verteilte Inferenz wird nach erfolgreichem Pairing automatisch verfügbar.

- `Einstellungen` → `LAN Cowork` → Inferenztypen (Tagger/CLIP/YOLO/Whisper) für jeden Knoten aktivieren
- Oder einzeln über die Matrix auf der Seite `/mesh-inference` konfigurieren

Details: [Setup für verteilte Inferenz](../mesh-inference/setup.md)

### Fleet-Verwaltung

Konfigurieren Sie einen "Chef"-Knoten zur Verwaltung anderer Knoten:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Details: [Fleet-Verwaltung](../features/fleet-admin.md)

### Generierungsverteilung (SD / ComfyUI Job-Delegierung)

Verteilen Sie Generierungsjobs automatisch an GPU-ausgestattete Knoten. Verfügbar über Konfigurationsdatei-Backend-Registrierung oder mDNS-Autoerkennung.  
Wenn Knoten B mit SD WebUI / ComfyUI läuft, ist es sofort nach der Konfiguration verfügbar.

---

## Netzwerkanforderungen

| Port / Protokoll | Zweck | Erforderlich |
|---|---|---|
| UDP 5353 | mDNS (Knotenerkennung) | Nur gleiches L2-LAN |
| UDP 19850 | LAN Cowork-Erkennung | Nur gleiches L2-LAN |
| TCP 5000 (Standard) | API, Kopplung, Inferenz | Zwischen Peers |

- mDNS funktioniert nicht über Router oder VPNs hinweg (verwenden Sie feste IP oder `.local`-Hostname)
- Stellen Sie sicher, dass UDP 5353 und TCP 5000 in Ihrer Firewall für das LAN geöffnet sind

---

## Dokumentationsindex

| Dokument | Inhalt |
|---|---|
| [Peer-PIN-Authentifizierung](peer-auth.md) | Kopplungsablauf, Token-Verwaltung, Sicherheitskonfiguration |
| [Setup für verteilte Inferenz](../mesh-inference/setup.md) | Schritte zum Parallelisieren der Inferenz auf mehreren Knoten |
| [Verteilte Inferenz-Matrix](../mesh-inference/toggle.md) | Aktivieren/Deaktivieren pro Peer und pro Typ über WebUI |
| [Architektur verteilter Inferenz](../mesh-inference/overview.md) | Internes Design, Work Stealing, Persistierung |
| [Fleet-Verwaltung](../features/fleet-admin.md) | Zentrale Verwaltung von Remote-Protokollen und Versionsupdates |
| [mDNS Peer-API](../api/mdns-peers.md) | Details der `/api/mdns/*`-Endpunkte |

---

## Sicherheit

- mDNS hat keine Authentifizierung. **Nur in Heim-LANs oder vertrauenswürdigen Netzwerken verwenden**
- In öffentlichen WLANs oder gemeinsamen LANs mit `"mdns": {"enabled": false}` deaktivieren
- Peer-Kommunikation wird durch Bearer-Token aus PIN-Kopplung geschützt (als Scrypt-Hash gespeichert)
- `ip_check_mode: strict` erlaubt nur die IP, von der der Token ausgestellt wurde (Standard)
