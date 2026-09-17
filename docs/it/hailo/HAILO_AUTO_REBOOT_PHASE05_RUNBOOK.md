# Hailo Auto-Reboot Phase 0.5 — Manuale operativo per questo ambiente

**Creato**: 2026-05-17 (v4.215.1)
**Ambiente di destinazione**: — Pi 5 che esegue questo repository
**Scopo**: Un manuale autonomo che consente di avviare, verificare e concludere l'osservazione della Fase 0.5 anche se la sessione di chat originale è andata persa.
**Specifica di progetto**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**Guida generale per gli operatori**: `docs/it/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (questo documento è la variante specifica per l'ambiente)

---

## 0. Prerequisiti e lavori già completati

- L'implementazione dell'osservazione della Fase 0.5 è stata integrata e inviata a main in v4.215.1 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (radice del repository) contiene già il blocco `hailo.auto_reboot`, **aggiunto il 2026-05-17**
  - Impostazioni consigliate: `mode = "lazy"` + `dry_run = true`
  - Backup: `config.json.bak.<timestamp>`
- **Non verrà avviato alcun riavvio reale** (`dry_run = true` + il design della Fase 0.5 registra solo gli eventi `would_fire`)

Verificare config.json:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → Deve apparire {"mode":"lazy","dry_run":true,...}
```

---

## 1. Procedura di primo avvio e attivazione

### 1.1 Riavvio del server

È necessario riavviare per applicare la modifica alla configurazione. **Riavviare utilizzando lo stesso metodo di avvio attualmente in uso.**

Comando di avvio tipico (da adattare all'ambiente reale):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

Se è in esecuzione come servizio systemd, riavviare l'unità corrispondente con `sudo systemctl restart <unit>`.

### 1.2 Verifica entro 30 secondi dall'avvio (3 punti)

#### A. L'evento `boot_baseline` è stato registrato?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Atteso: una riga contenente `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Risoluzione dei problemi se assente**:

- `logs/hailo_auto_reboot.log` non esiste → il ciclo judge non è in esecuzione (possibilmente non avviato in modalità `["full"]` o la variabile d'ambiente `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` è impostata)
- Il file esiste ma è vuoto → errore di risoluzione del percorso in `core/hailo_device_core/auto_reboot_logger.py`; verificare i permessi della directory `logs/`
- `cma_free_mb: null` → lettura di `/proc/meminfo` non riuscita (comportamento atteso su hardware non Pi, innocuo)

#### B. L'opt-in è attivo tramite la risposta `/api/system/cma`?

Se si è connessi tramite PIN nel browser, non è richiesta alcuna chiave API. Usare curl oppure eseguire nella console DevTools del browser (durante una sessione PIN attiva):

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Atteso:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

Se `enabled: false` o `mode: "off"` → verificare che `hailo.auto_reboot.mode` in config.json sia `"lazy"` e che il server abbia completato il riavvio.

#### C. Non ci sono errori di avvio in `error.log`?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

Nessun output significa OK. Se ci sono errori, fare riferimento a «8. Problemi noti» alla fine di questo documento.

---

## 2. Operazioni quotidiane durante il periodo di osservazione

### 2.1 Utilizzo normale

**Azione principale**:

- **Utilizzare la chat LLM come al solito** tramite `/ext/hailo-genai/chat` o `/tools` (es. Qwen3-1.7B)
- Usare VLM / S2T secondo le necessità
- Sessioni lunghe (30+ minuti continuativi) e cambi di modello multipli vale la pena provarli intenzionalmente per ampliare i dati di osservazione

Non sono richiesti test speciali. **Più si usa normalmente, più dati raccoglie la Fase 0.5** — questo è l'obiettivo del design.

### 2.2 Revisione settimanale (una volta a settimana, ~5 minuti)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Conteggio di ciascun tipo di evento
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Timestamp e CmaFree per gli eventi would_fire
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# Motivo di drain_entered (cma o rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Punti di controllo**:

- `would_fire` appare 1 o più volte → il deployment della Fase 1 ha valore (verificare se i timestamp registrati coincidono con i riavvii manuali effettuati)
- `prewarn_entered` si attiva frequentemente ma non progredisce a `drain_entered` → `prewarn_threshold_mb` (80 MB) potrebbe essere troppo basso; ricalibrare
- Il motivo di `drain_entered` è sempre `rejects` → il DRAIN è guidato dai rifiuti; sono necessarie misure diverse dalla regolazione delle soglie

---

## 3. Fine dell'osservazione e criteri di decisione per la Fase 1

### 3.1 Periodo di osservazione richiesto

**Minimo 7 giorni / Raccomandato 14 giorni**. Il periodo deve coprire almeno i seguenti schemi:

- Chat LLM normale
- Chat LLM lungo (30+ minuti in una singola sessione)
- Cambio di modelli VLM / S2T
- Almeno un rifiuto preliminare di `acquire_genai` (CmaFree insufficiente)
- Primo caricamento dopo un riavvio del Pi

### 3.2 Criteri numerici per il deployment della Fase 1

Aggregazione:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Tabella decisionale:

| Risultato dell'osservazione | Decisione Fase 1 |
|---|---|
| `would_fire` ≥ 1 | **GO** (l'automazione del riavvio ha valore) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Riaggiustare le soglie e considerare la Fase 1 (DRAIN viene raggiunto ma `would_fire` no — `fire_grace_seconds` potrebbe essere ridotto) |
| Solo `prewarn_entered`, `drain_entered` = 0 | La soglia attuale non raggiunge mai lo stato «critico» → la Fase 1 può non essere necessaria in base ai pattern di utilizzo |
| Tutti gli eventi a 0 (solo `boot_baseline`) | L'utilizzo non esaurisce la CMA → Fase 1 non necessaria |

### 3.3 Attività post-osservazione

1. Salvare i risultati aggregati in `docs/it/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (nuovo file)
2. In caso di deployment della Fase 1: procedere alla Fase 1 nella specifica rev3 §5.2 (banner DRAIN nell'interfaccia utente + i18n); riconfermare le soglie di §3.1 sulla base dei dati di osservazione
3. Se la Fase 1 non è necessaria: impostare `mode = "off"` in config.json e archiviare il registro delle osservazioni

---

## 4. Procedura di disattivazione (emergenza / interruzione dell'osservazione)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Riavviare il server
```

Anche con `mode = "off"`, gli eventi JSONL continuano a essere registrati (l'output WARN su `error.log` viene soppresso). Per disabilitare completamente, usare la variabile d'ambiente:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Riferimento ai file di log (file correlati)

| File | Scopo |
|---|---|
| `logs/hailo_auto_reboot.log` | **Log principale di questa funzionalità**. Formato JSONL; rotazione a 10 MB × 30 backup |
| `logs/hailo_cma.log` | Logger di eventi CMA esistente (dalla v4.214.10). Registra eventi di ciclo di vita VDevice/modello come `acquire_genai` |
| `logs/error.log` | Log degli errori globale dell'applicazione. Quando `mode != "off"`, genera anche riepiloghi WARN per `drain_entered` / `would_fire` |

---

## 6. Posizioni del codice correlato (per future indagini)

| Funzionalità | File |
|---|---|
| Macchina a stati + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Punto di ingresso del ciclo in background | `core/web/startup_background_hailo_judge.py` |
| Registrazione delle attività in background | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Valori predefiniti della configurazione | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| Hook acquire_genai | `core/hailo_device_core/device_manager_genai.py` |
| Estensione `/api/system/cma` | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Test unitari | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Cronologia della revisione (riferimento)

Questa implementazione ha superato il processo di revisione completo di AGENTS (vedere il messaggio del commit v4.215.1). I singoli file di report sono stati scritti in `.claude/agent-outputs/`, che è elencato in `.gitignore` e non è gestito da git. Possono essere rigenerati se necessario.

---

## 8. Problemi noti

| Sintomo | Causa e rimedio |
|---|---|
| Nulla appare in `logs/hailo_auto_reboot.log` | Server non riavviato / `mode = "off"` ancora impostato / non avviato in modalità `["full"]` / variabile d'ambiente `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` impostata |
| `cma_free_mb: null` persiste | In esecuzione su hardware non Pi (es. WSL2) o lettura di `/proc/meminfo` non riuscita; verificare sul vero hardware Pi |
| `hailo_runtime_version: null` | Il pacchetto `hailo_platform` non è installato in questo ambiente; su un vero Pi 5, il valore viene popolato se HailoRT 5.3.0 è installato |
| `would_fire` non appare mai | Il carico di utilizzo è troppo leggero o le soglie sono troppo permissive; provare chat lunghi continui / cambi di modello e riosservare |
| La modalità `eager` è configurata ma non funziona | Nella Fase 0.5, `eager` torna intenzionalmente a `off` (con un log di avviso); previsto per l'implementazione nella Fase 1+ |

---

## 9. Rollback di emergenza

Nel caso improbabile che l'implementazione della Fase 0.5 presenti un problema (bassa probabilità poiché non vengono attivati riavvii reali):

```bash
cd /home/pi/GitHub/yu_ai_manager
# Revertire da v4.215.1 a v4.214.13 (solo specifica, prima dell'implementazione)
git revert -m 1 69be148c6
git push
```

Oppure **disattivazione completa solo tramite configurazione** (consigliato):

```bash
# Aggiungere all'ambiente di avvio e riavviare il server
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Manutenzione di questo documento

- Al completamento dell'osservazione, **aggiungere il riepilogo di §3.3 alla fine di questo documento** (necessario per la decisione sulla Fase 1 nelle future sessioni di chat)
- Dopo il deployment della Fase 1, rinominare questo documento in `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` e creare un nuovo manuale per la Fase 1
- Questo documento si trova in `/home/pi/GitHub/yu_ai_manager/docs/it/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (gestito da git)
