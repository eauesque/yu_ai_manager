# API Sweeps

Points de terminaison pour l'historique d'exécution des sweeps Bridge (axes de paramètres NAI / SD WebUI / ComfyUI).

Les informations d'exécution sont persistées dans les tables `sweeps` / `sweep_axes` (migration 68) depuis v4.183.0. La liste d'historique de la page `/sweep/<id>` est rendue via cette API.

## GET /api/sweeps/history

Retourne les sweeps récents. Utilisé par `/sweep/<id>` pour afficher les filtres "mêmes conditions que le sweep actuel".

### Paramètres de requête

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Nombre maximal d'entrées retournées |
| `ref` | string | — | ID de sweep de référence; requis lorsque `match` est défini |
| `match` | CSV | — | Liste séparée par des virgules de champs à comparer avec la référence |
| `tol_steps` | string | `exact` | Tolérance pour les étapes: `exact` / `5` / `10` / `20` (pourcentage) |
| `tol_cfg` | string | `exact` | Tolérance pour CFG (mêmes valeurs) |
| `completed_only` | `0`/`1` | `0` | `1` conserve uniquement `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` conserve uniquement les lignes avec `first_file_id` non null |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Clés `match` autorisées

- `bridge` / `checkpoint` / `vae` / `sampler` — égalité de chaîne
- `positive` / `negative` — égalité de `prompt_template` / `negative_template`
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` à axis_index 0/1/2 doit correspondre
- `resolution` — correspondance de `width` ET `height`
- `steps` / `cfg` — correspondance numérique (`tol_*` contrôle la tolérance)
- `baseSeed` — correspondance de `base_seed`

Les clés pour lesquelles le sweep de référence n'a pas de valeur sont silencieusement ignorées (dans l'interface utilisateur, la case à cocher correspondante est désactivée).

### Réponse

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

`total` est le nombre de lignes non filtrées de `sweeps`, utilisé pour le badge "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Lit le paquet XMP de `file_id` et retourne les métadonnées de sweep structurées. Voir `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Analyse le dossier parent de `file_id` et retourne tous les fichiers dont XMP porte le même ID de sweep.

## Comment les lignes sont remplies

- **À l'heure de l'enregistrement**: `core/bridge_core/bridge_save_batch.py` appelle `upsert_sweep_from_meta()` après l'importation automatique. L'en-tête d'exécution et les axes sont écrits au premier coup d'oeil; les lots suivants ne mettent à jour que `last_file_id` / `file_count` / `updated_at`.
- **Remplissage rétroactif pour les anciens fichiers**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Parcourt les fichiers `has_sweep=1` et reconstruit les lignes à partir des attributs XMP. Idempotent.

## Limitations connues

- Le chemin d'enregistrement asynchrone (`return_file_ids=False`) peut laisser `first_file_id` NULL. L'interface utilisateur rend ensuite la ligne comme un élément non cliquable.
- `prompt_template` / `negative_template` sont stockés une fois par exécution. Les substitutions par axe de style S/R ne sont pas reconstruites; les valeurs d'axe par image restent dans le paquet XMP et sont lues par `/api/sweep/info/<file_id>`.
