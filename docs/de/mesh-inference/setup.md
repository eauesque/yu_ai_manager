# Verteilte Inferenz-Einrichtungsanleitung

> Zielversion: v4.67.0 und später

## Was ist verteilte Inferenz?

Eine Funktion, bei der mehrere yu_ai_manager-Knoten zusammenarbeiten, um Inferenzverarbeitung wie Tagging, CLIP, YOLO und Spracherkennung **parallel und verteilt** auszuführen. Sie können große Datei-Scans auf mehreren Maschinen verteilen oder das Tagging an einen Pi5 mit Hailo NPU delegieren.

```
┌──────────────┐   Bild-Batch    ┌──────────────┐
│   Lokal      │ ──────────────► │  Pi5 (Hailo) │  Tagger × 200 Bilder
│   (Scan)     │ ──────────────► │  GPU-Maschine│  Tagger × 300 Bilder
│              │ ──────────────► │    Lokal     │  Tagger × 100 Bilder
└──────────────┘   Arbeit        └──────────────┘
                  Stealing
```

---

## Voraussetzungen

Folgende Bedingungen müssen auf jedem Knoten erfüllt sein:

1. yu_ai_manager läuft
2. **LAN Cowork-Erweiterung ist aktiviert** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. Knoten sind **miteinander gekoppelt** ([Peer-Authentifizierungsanleitung](../lan-cowork/peer-auth.md))
4. Inferenz-Engines, die verwendet werden sollen, sind auf jedem Knoten eingerichtet (ONNX / Hailo / Whisper usw.)

---

## Einrichtungsschritte

### Schritt 1: LAN Cowork auf jedem Knoten aktivieren

In `config.json` auf allen Knoten:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

Nach einem Neustart werden sich die Knoten über mDNS gegenseitig erkennen.

### Schritt 2: Kopplung abschließen

Führen Sie die Kopplung zwischen allen Knotenpaaren durch (bidirektional).
Details: [Peer-PIN-Authentifizierung und Token-Kopplung](../lan-cowork/peer-auth.md)

### Schritt 3: Verteilte Inferenz-Matrix überprüfen

Öffnen Sie `/mesh-inference` auf einem beliebigen Knoten.

Gekoppelte Knoten werden als Zeilen angezeigt, Inferenztypen als Spalten:

| Knoten | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| Lokal | ☑ Aktiviert | ☑ Aktiviert | ☑ Aktiviert | ☑ Aktiviert |
| pi5-hailo | ☑ Aktiviert | ☑ Aktiviert | — Nicht verfügbar | — Nicht verfügbar |
| gpu-win | ☑ Aktiviert | ☑ Aktiviert | ☑ Aktiviert | ☑ Aktiviert |

- **☑ Aktiviert**: Diesen Knoten für Inferenz verwenden
- **☐ Deaktiviert**: Überspringen (kann manuell umgeschaltet werden)
- **—**: Dieser Knoten hat die Ziel-Inferenz-Engine nicht (kann nicht bedient werden)

### Schritt 4: Betrieb überprüfen

Führen Sie einen Tagging-Batch aus und bestätigen Sie in den Logs, dass mehrere Knoten verwendet werden:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Anforderungen nach Inferenztyp

| Typ | Erforderliche Engine | Beschreibung |
|---|---|---|
| `tagger` | ONNX (WD14 usw.) oder Hailo NPU | Danbooru-Style-Tagging für Bilder |
| `clip` | ONNX CLIP oder Hailo | Semantische Einbettungsvektoren für Bilder (für semantische Suche) |
| `yolo` | ONNX YOLO | Objekterkennung in Bildern |
| `whisper` | faster-whisper oder Remote | Sprache-zu-Text-Transkription für Audio/Video |

Knoten ohne konfigurierte Engine zeigen für diesen Typ „—" an und werden nicht für diesen Typ geroutet.

---

## Beispiele für Rollendesign

### Beispiel 1: Pi5 + Hailo NPU ausschließlich für Tagging

Reservieren Sie Pi5 ausschließlich für Tagging, um die Last auf anderen Knoten zu reduzieren.

Matrix-Konfiguration:
- Pi5: Tagger ☑, andere ☐
- Lokal: clip ☑, yolo ☑, whisper ☑, tagger ☐ (an Pi5 delegieren)

### Beispiel 2: Schnelles Massen-Scan

Aktivieren Sie den Tagger sowohl auf der GPU-Maschine als auch auf der lokalen Maschine, um Dateien automatisch über Work Stealing zu teilen. Keine manuelle Aufteilung erforderlich.

### Beispiel 3: Reiner lokaler Modus (temporär)

Klicken Sie in `/mesh-inference` auf die Schaltfläche „Nur lokal", um alle Remote-Peers auf einmal zu deaktivieren. Nützlich bei Netzwerkunterbrechung.

---

## Fehlerbehebung

### Peer wird in der Matrix nicht angezeigt

1. Überprüfen Sie mit `/api/lan/peers`, ob der Peer erkannt wird
2. Bestätigen Sie, dass die Kopplung abgeschlossen ist ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Überprüfen Sie, ob LAN Cowork auf dem Remote-Knoten aktiviert ist

### Routing zu einem bestimmten Knoten funktioniert nicht

- Überprüfen Sie, ob der Zieltyp für diesen Knoten in der Matrix ☑ anzeigt
- Überprüfen Sie, dass die Antwort von `/api/lan/peers` für diesen Knoten `status: "online"` anzeigt
- Überprüfen Sie, dass der Heartbeat des Remote-Knotens empfangen wird (suchen Sie in Logs nach `heartbeat`)

### Alles wird lokal verarbeitet

Wenn alle Remote-Peers offline oder deaktiviert sind, erfolgt ein automatisches lokales Fallback.
Dies ist normales Verhalten (kein Fehler).

### `no_enabled_peers`-Fehler

Dieser Typ ist auf allen Knoten deaktiviert.
Aktivieren Sie mindestens 1 Knoten für diesen Typ in der Matrix.

---

## Verwandte Dokumentation

- [Verteilte Inferenz-Architektur](overview.md) — Work Stealing und DisableAwareStrategy interner Entwurf
- [Verteilte Inferenz-Matrix](toggle.md) — Details zur WebUI-Bedienung
- [LAN Cowork-Übersicht](../lan-cowork/README.md) — LAN Cowork Gesamtkonfiguration
- [Peer-PIN-Authentifizierung](../lan-cowork/peer-auth.md) — Kopplungsverfahren
