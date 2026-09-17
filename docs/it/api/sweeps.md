# API Sweeps

Endpoint per la cronologia di esecuzione del sweep Bridge (assi dei parametri NAI / SD WebUI / ComfyUI).

Le informazioni di esecuzione sono state persistite nelle tabelle `sweeps` / `sweep_axes` (migrazione 68) da v4.183.0 in poi. L'elenco della cronologia della pagina `/sweep/<id>` viene renderizzato tramite questa API.

## GET /api/sweeps/history

Restituisce i sweep recenti. Utilizzato da `/sweep/<id>` per mostrare i filtri "stesse condizioni come lo sweep attuale".

### Parametri di query

| Parametro | Tipo | Predefinito | Descrizione |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Numero massimo di voci restituite |
| `ref` | string | — | ID sweep di riferimento; obbligatorio quando `match` è impostato |
| `match` | CSV | — | Elenco separato da virgole di campi da confrontare con il riferimento |
| `tol_steps` | string | `exact` | Tolleranza per i passaggi: `exact` / `5` / `10` / `20` (percentuale) |
| `tol_cfg` | string | `exact` | Tolleranza per CFG (stessi valori) |
| `completed_only` | `0`/`1` | `0` | `1` mantiene solo `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` mantiene solo le righe con `first_file_id` non nullo |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Chiavi `match` consentite

- `bridge` / `checkpoint` / `vae` / `sampler` — uguaglianza di stringa
- `positive` / `negative` — uguaglianza di `prompt_template` / `negative_template`
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` all'axis_index 0/1/2 deve corrispondere
- `resolution` — corrispondenza di `width` E `height`
- `steps` / `cfg` — corrispondenza numerica (`tol_*` controlla la tolleranza)
- `baseSeed` — corrispondenza di `base_seed`

Le chiavi per le quali lo sweep di riferimento non ha alcun valore vengono ignorate silenziosamente (nell'interfaccia utente la casella di controllo corrispondente è disabilitata).

### Risposta

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

`total` è il numero di righe non filtrate di `sweeps`, utilizzato per il badge "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Legge il pacchetto XMP di `file_id` e restituisce i metadati dello sweep strutturati. Vedere `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Scansiona la cartella padre dell'hint `file_id` e restituisce ogni file il cui XMP porta lo stesso ID sweep.

## Come vengono popolate le righe

- **Al momento del salvataggio**: `core/bridge_core/bridge_save_batch.py` chiama `upsert_sweep_from_meta()` dopo l'importazione automatica. L'intestazione di esecuzione e gli assi vengono scritti al primo sguardo; i batch successivi aggiornano solo `last_file_id` / `file_count` / `updated_at`.
- **Retroempitura per i file vecchi**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Esamina i file `has_sweep=1` e ricostruisce le righe dagli attributi XMP. Idempotente.

## Limitazioni note

- Il percorso di salvataggio asincrono (`return_file_ids=False`) può lasciare `first_file_id` NULL. L'interfaccia utente renderizza quindi la riga come elemento non cliccabile.
- `prompt_template` / `negative_template` vengono archiviati una volta per esecuzione. Le sostituzioni per asse di stile S/R non vengono ricostruite; i valori degli assi per immagine rimangono nel pacchetto XMP e vengono letti da `/api/sweep/info/<file_id>`.
