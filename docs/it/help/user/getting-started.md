# Introduzione

YU AI Manager è un'applicazione WebUI per la gestione dei metadati delle immagini generate da IA.

## Installazione

### Requisiti di sistema

- Python 3.11 o versioni superiori
- Node.js 18 o versioni superiori (per build del frontend)

### Procedura setup

```bash
# Clona repository
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Installa uv (solo prima volta)
pip install uv

# Crea virtual environment Python e installa dipendenze
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Build frontend
pnpm install
pnpm run build

# Opzionale: velocizza ricerca semantica (per librerie grandi)
uv pip install faiss-cpu
```

## Come avviare

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Accedi a `http://localhost:5000` dal browser.

## Configurazione iniziale

1. **Registra cartelle di scansione**: Settings > Scan tab, aggiungi cartelle dove sono salvate le immagini IA
2. **Avvia scansione**: Dopo aggiunta cartella, scansione inizia automaticamente
3. **Visualizza immagini**: Pagina principale per cercare e visualizzare immagini

## Condivisione LAN

Per accesso da altri dispositivi:

1. Settings > tab **Server**, attiva "LAN Access"
2. Configura autenticazione PIN (obbligatoria per LAN pubblico)  
   **Settings > Server tab** — campo "PIN authentication code", inserisci cifre (4-8 digit)
3. Riavvia server

Accedi da altri device su LAN con `http://<server-IP>:5000`.
