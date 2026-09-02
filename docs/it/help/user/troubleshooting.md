# Risoluzione dei Problemi

## Problemi Comuni

### Il server non si avvia

- Verificare che l'ambiente virtuale Python sia attivato: `source venv/bin/activate`
- Verificare che i pacchetti dipendenti siano installati: `uv pip install -r requirements.txt`
- Verificare che la porta non sia in uso: `ss -tlnp | grep 5000`

### Le immagini non vengono visualizzate

- L'API thumbnail richiede il file immagine fisico
- Verificare che il percorso nella tabella `files` corrisponda al percorso effettivo del file
- Verificare che il percorso della radice di scansione sia corretto

### Impossibile accedere dalla LAN

- Verificare che "LAN Access" sia ON in Settings > Server
- Verificare che l'autenticazione PIN sia configurata (obbligatoria per pubblicazione LAN)
- Verificare che la porta sia aperta nel firewall
- Verificare che l'indirizzo IP del server sia corretto

### Errore connessione MCP

- Verificare che `YU_BASE_URL` sia corretto
- Verificare che il server sia avviato
- Verificare che la API key sia valida
- Per connessioni LAN, verificare la disponibilità dell'endpoint HTTP/SSE (`/mcp`)

### La scansione è lenta

- Disattivare `compute_hash` per accelerare
- Per percorsi remoti, regolare le impostazioni timeout del filesystem remoto
- Con grandi quantità di file, la scansione iniziale richiede tempo

### La generazione thumbnail è lenta

- Durante la scansione l'I/O disco è saturo, quindi la generazione thumbnail rallenta. Dopo il completamento della scansione il pre-warming viene eseguito automaticamente
- **pyvips (opzionale)**: Per grandi quantità di immagini JPEG grandi, lo shrink-on-load di libvips accelera il processo
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: scaricare la DLL dalla [pagina release di libvips](https://github.com/libvips/libvips/releases), aggiungerla al PATH e poi `uv pip install pyvips`
  - Se installato viene rilevato automaticamente. Funziona anche con Pillow se non installato
- **Pillow-SIMD (opzionale)**: Accelera il ridimensionamento immagini di 2-4x con ARM NEON / x86 AVX2
  - `uv pip install pillow-simd` (sostituto drop-in di Pillow)

## Debug

- Verificare i log del server dalla scheda Settings > Logs
- Modalità debug MCP: strumenti aggiuntivi disponibili con `YU_DEBUG_MODE=1`
- Controllo integrità DB: `python db_health.py`
