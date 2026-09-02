# Mesh-Inferenz-Matrix

**Version**: ab v4.67.0

## Übersicht

Auf der Seite `/mesh-inference` kann für jeden an der Mesh-Inferenz teilnehmenden Peer pro Inferenztyp aktiviert/deaktiviert werden. Zielgruppe sind die vier Typen tagger, clip, yolo und whisper.

Damit lassen sich Aufgaben verteilen -- z. B. Pi5 Hailo NPU auf Tagger konzentrieren oder CLIP auf einem GPU-Host ausführen -- ohne die Konfiguration zu bearbeiten.

## Nutzung

1. Über die Navigationsleiste auf „🕸️ Mesh-Inferenz" klicken
2. Durch Klicken einer Zelle in der Matrixtabelle aktivieren/deaktivieren
   - ☑ = aktiv (dieser Inferenztyp wird auf diesem Peer genutzt)
   - ☐ = inaktiv (dieser Peer wird übersprungen)
   - — = dieser Peer bietet den Typ nicht an (nicht bedienbar)
3. Über den Button „Nur-lokal-Modus" können alle Remote-Peers gleichzeitig deaktiviert werden
4. Der Zustand wird automatisch in `data/mesh_inference_state.json` persistiert

## Verhalten

- Einstellungen bleiben auch für Offline-Peers erhalten (werden bei Reconnect automatisch angewendet)
- „Nur-lokal-Modus" lässt sich nur auslösen, wenn lokal mindestens ein Typ aktiv ist
- Wird ein Tagger-Batch gestartet, während auf allen Peers der Tagger deaktiviert ist, schlägt er sofort mit dem Fehler `no_enabled_peers` fehl
- Beim vorübergehenden Ausscheiden und erneuten Beitritt eines Peers durch mDNS-Neuerkennung bleibt der Deaktivierungszustand erhalten

## Beziehung zur bestehenden YOLO-Distributed-Inferenz-Checkbox

Die „Distributed-Inferenz"-Checkbox auf der YOLO-Detection-Seite bleibt aus Kompatibilitätsgründen erhalten und verhält sich in Kombination wie folgt:

| yoloDistributed | Matrix yolo-Spalte | Tatsächliches Verhalten |
|---|---|---|
| ✅ ON | Alle Peers aktiv | Wie bisher auf alle Peers verteilt |
| ✅ ON | Teilweise inaktiv | Inaktive Peers überspringen |
| ❌ OFF | Wird ignoriert | Nur lokal (Router-Bypass) |

## Verwandt

- API-Referenz: [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router (andere Ebene): [../llm-router/](../llm-router/)
