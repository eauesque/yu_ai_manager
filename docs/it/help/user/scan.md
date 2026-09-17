# Scansione

## Registrazione cartelle scansione

Settings > tab Scan per aggiungere cartelle target scansione.

- Drag&drop per riordinare
- Checkbox per abilitare/disabilitare
- Puoi registrare più cartelle

## Esecuzione scansione

- Auto-avvio dopo aggiunta cartella
- Scansione manuale da pagina Tools o MCP con `trigger_scan`
- Progresso scansione notificato real-time via SSE

## Scansione automatica (Watcher)

Abilita extension Auto Scan Watcher per auto-rilevare modifiche file in cartelle registrate e scansionare automaticamente.

## File system remoto

Se scansioni path WSL / NAS / SMB, in Settings > tab Remote FS regola timeout.

## Scansione librerie grandi

Se scansioni decine di migliaia fino a 1 milione+ file:

- **Ricerca durante scansione**: API ricerca usa connessione DB sola lettura, non influenzata da write-lock durante scansione
- **Gestione WAL auto**: Durante scansione, checkpoint WAL automatico ogni 2000 file, previene dilatazione WAL
- **Evento scan.db_busy**: SSE invia evento inizio/fine scansione, frontend può mostrare stato busy

## Worker process scansione

Dalla v3.27.0, scansione esegue in processo separato da web_ui.py.
Questo significa **riavvio web_ui non interrompe scansione**.

### Come funziona

- Inizio scansione da WebUI avvia worker process in background
- Worker scrive file progresso (JSON) e PID file in `/tmp/yu-scan/`
- WebUI esegue polling file progresso e inoltra via SSE a frontend
- Riavvio WebUI auto-rileva worker in esecuzione e riconnette visualizzazione progresso

### Operi da CLI

Puoi operare worker da CLI direttamente. Funziona anche con WebUI arresto.

```bash
# Visualizza status
python -m core.scan.scan_worker status

# Ferma scansione in esecuzione (graceful shutdown — salva posizione interruzione in DB)
python -m core.scan.scan_worker stop

# Avvia scansione direttamente da CLI
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Opzioni
#   --recursive / --no-recursive  Include subdirectory (default: recursive)
#   --scan-zips                   Scansione immagini dentro ZIP/7z
#   --force                       Ri-scansione file esistenti
#   --resume                      Riprendi scansione interrotta
#   --config config.json          Specifica file config
```

### Meccanismi sicurezza

- **Monitoraggio parent process**: Worker avviato da WebUI monitora esistenza processo WebUI ogni 60 secondi. Se WebUI termina anomalmente, worker auto-salva interruzione e si ferma
- **Supporto SIGTERM**: `stop` o `kill` con SIGTERM completa operazione corrente, commit DB, salva posizione interruzione, esci
- **Prevenzione duplicati**: Non avvio simultaneo di più worker

### Troubleshooting

Se worker non risponde:

```bash
# Visualizza PID
cat /tmp/yu-scan/worker.pid

# Forza terminazione processo
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Pulizia file residui
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Errori scansione

Se errori durante scansione, visualizza con MCP `get_scan_errors`.
