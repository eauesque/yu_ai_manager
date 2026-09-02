# 5 minuti per iniziare YU AI Manager

## Cos'è YU AI Manager

YU AI Manager è un'applicazione WebUI che gestisce centralizzato i metadati delle immagini generate da IA (Stable Diffusion / NovelAI / ComfyUI ecc.). Estrae automaticamente prompt e informazioni modello embed nelle immagini, semplificando ricerca tag, visualizzazione e organizzazione.

---

## Ambiente di esecuzione

| Elemento | Requisito |
|------|------|
| Python | 3.11 o versioni superiori |
| Node.js | 18 o versioni superiori (per build frontend) |
| OS | Windows 10/11, macOS, Linux |
| Browser | Chrome / Firefox / Edge (versioni recenti consigliate) |

---

## Procedura installazione

### 1. Clona repository

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Crea virtual environment Python

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Installa dipendenze Python

```bash
uv pip install -r requirements.txt
```

> Se `uv` non è installato, prima esegui `pip install uv`.

### 4. Build frontend

```bash
pnpm install
pnpm run build
```

> Se `pnpm` non è installato, prima esegui `npm install -g pnpm`.

Installazione completata!

---

## Primo avvio

### 1. Avvia server

```bash
# Attiva venv se non già attivato
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. Accedi da browser

Dopo avvio, apri nel browser:

```
http://localhost:5000
```

---

## Prime cose da fare

### Step 1: Registra cartella immagini per scansione

Registra la cartella dove sono salvate le immagini IA per leggere i metadati.

1. Apri **Settings** dal menu hamburger in alto a destra
2. Seleziona tab **Scan**
3. Aggiungi il path della cartella target scansione
4. Dopo aggiunta cartella, scansione inizia automaticamente

La scansione mostra una barra di avanzamento in alto. Con molte immagini, può richiedere alcuni minuti, ma puoi comunque cercare e visualizzare durante la scansione.

### Step 2: Visualizza immagini in grid miniature

Dopo scansione completata, appaiono miniature in grid sulla pagina principale.

- **Scroll**: Virtual scrolling per migliaia di immagini
- **Sort**: Menu sort in alto per ordinare per data, valutazione, ecc.
- **Right-click**: Menu contestuale per aggiungere favoriti o collezioni

### Step 3: Filtra con ricerca tag

Digita tag separati da virgola nella barra ricerca per filtrare immagini.

```
1girl, blue_eyes, school_uniform
```

- **Autocompletion**: Suggerimenti tag durante digitazione
- **Filtri**: Filtra per intervallo date, formato file, valutazione stelle, ecc.
- **Ricerca nel prompt**: Ricerca full-text nel testo prompt

### Step 4: Visualizza info dettagliate in modal

Click su miniatura apre modal dettaglio.

- **Info tab**: Visualizza prompt, negative prompt, nome modello, parametri generazione
- **AI Analysis tab**: Risultati tagging automatico da WD-Tagger (se configurato)
- **Valutazione stelle**: Dai 1-5 stelle all'immagine
- **Favoriti**: Aggiungi a preferiti con icona cuore
- **Modifica tag**: Aggiungi/rimuovi tag utente
- **Navigazione tastiera**: Frecce sinistra/destra per muoversi tra immagini

---

## Operazioni comuni riepilogate

| Azione | Operazione |
|-------------|------|
| Trova immagine | Digita tag in barra ricerca |
| Visualizza dettagli immagine | Click su miniatura |
| Aggiungi a favoriti | Icona cuore in modal dettaglio, o menu right-click |
| Valuta con stelle | Icona stelle in modal dettaglio |
| Aggiungi immagine a collezione | Menu right-click > Add to collection |
