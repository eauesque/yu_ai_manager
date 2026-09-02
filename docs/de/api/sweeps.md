# Sweeps API

Endpunkte für Bridge Sweep (NAI / SD WebUI / ComfyUI Parameterachsen) Ausführungsverlauf.

Die Ausführungsinformationen werden seit v4.183.0 in den Tabellen `sweeps` / `sweep_axes` gespeichert (Migration 68). Die Historienliste der Seite `/sweep/<id>` wird über diese API dargestellt.

## GET /api/sweeps/history

Gibt aktuelle Sweeps zurück. Wird von `/sweep/<id>` verwendet, um Filter für "gleiche Bedingungen wie der aktuelle Sweep" anzuzeigen.

### Abfrageparameter

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Maximale Anzahl zurückgegebener Einträge |
| `ref` | string | — | Referenz-Sweep-ID; erforderlich wenn `match` gesetzt ist |
| `match` | CSV | — | Kommagetrennte Liste von Feldern zum Abgleich mit der Referenz |
| `tol_steps` | string | `exact` | Toleranz für Schritte: `exact` / `5` / `10` / `20` (Prozent) |
| `tol_cfg` | string | `exact` | Toleranz für CFG (gleiche Werte) |
| `completed_only` | `0`/`1` | `0` | `1` behält nur `status='completed'` bei |
| `saved_only` | `0`/`1` | `0` | `1` behält nur Zeilen mit nicht-null `first_file_id` bei |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Zulässige `match` Schlüssel

- `bridge` / `checkpoint` / `vae` / `sampler` — Stringgleichheit
- `positive` / `negative` — `prompt_template` / `negative_template` Gleichheit
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` bei axis_index 0/1/2 muss übereinstimmen
- `resolution` — `width` UND `height` stimmen überein
- `steps` / `cfg` — numerischer Abgleich (`tol_*` steuert Toleranz)
- `baseSeed` — `base_seed` Abgleich

Schlüssel, für die der Referenz-Sweep keinen Wert hat, werden stillschweigend ignoriert (in der Benutzeroberfläche ist das entsprechende Kontrollkästchen deaktiviert).

### Antwort

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "base_seed": 1234567,
        "created_at": 1714992000,
        "prompt_template": "best quality, ...",
        "negative_template": "worst quality, ...",
        "checkpoint": "nai-anime-v3",
        "vae": null,
        "sampler": "k_euler",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "last_file_id": 12399,
        "file_count": 6,
        "status": "completed",
        "updated_at": 1714992100,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

`total` ist die ungefilterte Zeilenanzahl von `sweeps`, verwendet für das Badge "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Liest das XMP-Paket von `file_id` und gibt die strukturierten Sweep-Metadaten zurück. Siehe `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Scannt den übergeordneten Ordner des Hinweis-`file_id` und gibt alle Dateien zurück, deren XMP die gleiche Sweep-ID trägt.

## Wie Zeilen gefüllt werden

- **Bei Speicherzeit**: `core/bridge_core/bridge_save_batch.py` ruft `upsert_sweep_from_meta()` nach dem automatischen Importieren auf. Der Ausführungs-Header und die Achsen werden beim ersten Anblick geschrieben; nachfolgende Batches aktualisieren nur `last_file_id` / `file_count` / `updated_at`.
- **Nachträgliches Füllen für alte Dateien**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Durchläuft `has_sweep=1` Dateien und rekonstruiert Zeilen aus XMP-Attributen. Idempotent.

## Bekannte Einschränkungen

- Der asynchrone Speicherpfad (`return_file_ids=False`) kann `first_file_id` NULL hinterlassen. Die Benutzeroberfläche rendert die Zeile dann als nicht anklickbares Element.
- `prompt_template` / `negative_template` werden einmal pro Lauf gespeichert. S/R-ähnliche pro-Achsen-Substitutionen werden nicht rekonstruiert; pro-Bild-Achsenwerte bleiben im XMP-Paket und werden von `/api/sweep/info/<file_id>` gelesen.
