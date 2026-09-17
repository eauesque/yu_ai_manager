# Suche

## Grundsuche

Tags durch Komma-Eingabe in der Suchleiste eingeben.

```
1girl, blue_eyes, school_uniform
```

## Suchfilter

| Filter | Beschreibung |
|---------|------|
| Datumsbereich | Eingrenzen von Start- bis Enddatum |
| Dateiformat | PNG / WebP / JPG / GIF |
| Bewertung | 1-5 Sterne |
| Favoriten | Nur Favoriten anzeigen |
| Sammlung | Nur in bestimmter Sammlung |

## Prompt-Suche

Mit dem `in_prompt`-Feld kann der Prompt-Text von Bildern volltextgesucht werden.
Bei aktivierter FTS (Volltextsuche) schnelle Suche möglich.

## Sortierreihenfolge

| Sortierung | Beschreibung |
|--------|------|
| date | Registrierungsdatum (neuste zuerst) |
| date_old | Registrierungsdatum (älteste zuerst) |
| folder | Ordner-Reihenfolge |
| path | Pfad-Reihenfolge |
| random | Zufällig |
| rating_desc | Bewertung (höchste zuerst) |
| rating_asc | Bewertung (niedrigste zuerst) |

## Semantische Suche

Bei konfiguriertem Hailo-10H oder ONNX CLIP-Modell kann natürlichsprachliche Bildsuche verwendet werden.
Semantische Such-Button rechts neben der Suchleiste verwenden.

### Beschleunigung mit FAISS (empfohlen)

Semantische Suche verwendet standardmäßig NumPy-Brute-Force-Suche, aber
**FAISS erheblich beschleunigt** bei Installation.

| Bibliotheksgröße | NumPy (Standard) | FAISS (empfohlen) |
|-------------|-------------------|-------------|
| Unter 10.000 | Dutzende ms | Wenige ms |
| 100.000 | 1-3 Sek. | Dutzende ms |
| 1 Million+ | Über 10 Sek. | Unter 100ms |

FAISS wählt je nach Skalierung automatisch den optimalen Index:
- **Unter 50.000**: IndexFlatIP (exakte Suche, schnell genug)
- **50.000+**: IndexIVFFlat (approximate nearest neighbor, schnell bei großer Skala)

#### Installationsanleitung

```bash
# venv aktivieren vor Installation
source venv/bin/activate

# x86_64 (Intel/AMD) — direkt via pip installierbar
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — falls pip nicht geht
# Methode 1: via conda
conda install -c conda-forge faiss-cpu

# Methode 2: aus Quellen bauen
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

Nach Installation einfach Server neu starten für automatische Erkennung.
Beim Start wird folgendes im Log angezeigt:

```
FAISS x.x.x detected — using accelerated vector search
```

Wenn FAISS nicht installiert, funktioniert weiterhin NumPy.
