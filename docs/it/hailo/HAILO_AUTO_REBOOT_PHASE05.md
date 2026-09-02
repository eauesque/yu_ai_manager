# Guida operativa Hailo Auto-Reboot Phase 0.5

**Creato**: 2026-05-17 (v4.215.0)
**Destinazione**: Operazioni di osservazione CMA leak su Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0
**Stato**: Fase di osservazione. Non viene eseguito alcun riavvio reale; vengono registrati solo gli eventi `would_fire`.

---

## 1. Scopo della Phase 0.5

La Phase 0.5 è la fase di osservazione del progetto di riavvio automatico contro i CMA leak in HailoRT 5.3.0 + `hailo1x_pci`.

In questa fase, la macchina a stati calcola i seguenti stati:

| Stato | Condizione |
|---|---|
| `idle` | Stato normale |
| `prewarn` | `CmaFree < 80 MB` persiste per 180 secondi |
| `draining` | `CmaFree < 30 MB` persiste per 60 secondi, oppure il pre-reject di `acquire_genai` si verifica 3 volte consecutive |
| `would_fire` | Trascorsi 120 secondi da `draining` |

Importante: Nella Phase 0.5, anche se viene raggiunto `would_fire`, il Pi NON viene riavviato. L'evento viene solo registrato in formato JSON Lines in `logs/hailo_auto_reboot.log`.

---

## 2. Perché il valore predefinito è `mode = "off"`

Il valore predefinito di `hailo.auto_reboot.mode` è `"off"`. Poiché il riavvio automatico può interrompere il lavoro dell'operatore, l'osservazione viene avviata solo negli ambienti in cui l'operatore ha esplicitamente scelto di partecipare (opt-in).

La configurazione consigliata per la Phase 0.5 è la seguente:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` è un prerequisito per la Phase 0.5. Il percorso di riavvio effettivo viene gestito dalla Phase 4 in poi.

### 2.1 Procedura di opt-in

La configurazione di avvio dà priorità al file specificato tramite `--config` o `TAGDB_CONFIG`. Se non specificato, legge `config.json` nella directory radice del repository, poi `tagdb_config.json`.

Esempio:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Aggiungere le seguenti impostazioni a `<repo>/config.json` o al file JSON specificato tramite `--config` / `TAGDB_CONFIG` durante l'operazione:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Riavviare il server per applicare la configurazione. Mantenere gli argomenti effettivamente utilizzati in base al proprio metodo di avvio.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

Se si opera con systemd, riavviare l'unità corrispondente:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Procedura di disattivazione

Impostare `hailo.auto_reboot.mode` su `"off"` nella stessa configurazione e riavviare il server.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

Con `mode = "off"`, gli eventi di osservazione JSON Lines vengono conservati, ma non viene generato alcun riepilogo WARN in `error.log`.

---

## 3. Come leggere i log

I log di osservazione vengono scritti nel seguente file:

```text
logs/hailo_auto_reboot.log
```

Il formato è JSON Lines. Gli eventi principali sono i seguenti:

| Evento | Significato |
|---|---|
| `boot_baseline` | Punto di inizio osservazione all'avvio |
| `prewarn_entered` | Condizione PREWARN soddisfatta |
| `drain_entered` | Condizione DRAIN soddisfatta |
| `would_fire` | Punto che diventerebbe un trigger di riavvio nella Phase 1+ |
| `drain_cleared` | CMA recuperato e DRAIN eliminato |

Esempio:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Esempi di comandi di verifica:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Se `would_fire` si verifica frequentemente, indica che con le soglie attuali è molto probabile che sia necessario un riavvio del Pi durante il funzionamento reale. Al contrario, se appare solo `prewarn_entered` senza progredire verso `drain_entered`, le soglie o i tempi di tolleranza possono essere riadattati prima della Phase 1.

---

## 4. Procedura di verifica API

Verificare `/api/system/cma` con la chiave API di amministrazione.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Esaminare `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` e `cma.auto_reboot.consecutive_rejects` nella risposta.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Periodo di osservazione

L'obiettivo è di 1–2 settimane. Assicurarsi che il periodo copra almeno i seguenti modelli:

- Utilizzo normale del chat LLM
- Utilizzo prolungato del chat
- Operazioni che causano errori di caricamento del modello Hailo GenAI o pre-reject
- Primo caricamento dopo il riavvio del Pi

L'osservazione si considera completa quando è possibile aggregare i dati di frequenza per `prewarn_entered` / `drain_entered` / `would_fire` nell'arco di 1–2 settimane. Dopo l'osservazione, esaminare il numero di occorrenze di `would_fire`, il motivo di `drain_entered` (`cma` / `rejects`) e il tasso di diminuzione di `CmaFree` per finalizzare le soglie prima di distribuire la Phase 1.

Esempio di aggregazione:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Documenti correlati

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
