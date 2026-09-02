# Guida allo sviluppo di Custom UI

Guida al sistema Custom UI che consente di sostituire completamente il frontend di YU AI Manager.

## Indice

- [Panoramica](#panoramica)
- [Architettura](#architettura)
- [Guida rapida](quickstart.md) — Procedura di creazione di un'UI minima
- [Guida alla progettazione](design-guide.md) — Progettazione CSS, tema, responsive, componenti
- [Guida ai template](templates.md) — Pattern Jinja2, i18n, struttura delle pagine
- [Funzionalità avanzate](advanced.md) — Aggiornamenti SSE in tempo reale, operazioni batch, sicurezza
- [Riferimento API](api-reference.md) — Raccolta di link a documentazione API completa

## Panoramica

YU AI Manager ha un'API backend completamente separata, quindi puoi sostituire liberamente il frontend.
Un'UI personalizzata viene abilitata semplicemente posizionandola nella directory `ui/<nome>/`.

### Cosa puoi fare con questo sistema

- **Sostituzione UI completa**: Sostituisci tutte le pagine come quella di ricerca, statistiche, impostazioni con il tuo design
- **Personalizzazione del tema**: Cambia lo schema colori sovrascrivendo solo le variabili CSS
- **Sostituzione parziale**: Personalizza solo le pagine che ti servono, usa l'UI di default per il resto
- **Generazione UI con IA**: Passa la documentazione API a Claude o ChatGPT per generare automaticamente un'UI

### Architettura

```
yu_ai_manager/
├── ui/
│   ├── default/              # UI di riferimento (built-in)
│   │   ├── manifest.json     # Metadati UI (obbligatorio)
│   │   ├── templates/        # Template HTML Jinja2
│   │   │   ├── index.html    # Pagina di ricerca principale
│   │   │   ├── stats.html    # Dashboard statistiche
│   │   │   ├── tools.html    # Pagina strumenti
│   │   │   ├── settings.html # Pagina impostazioni
│   │   │   ├── story.html    # Pagina Your Story
│   │   │   ├── inspect.html  # Ispezione metadati
│   │   │   └── _nav.html     # Barra di navigazione comune (include)
│   │   └── static/           # CSS, JS, immagini
│   │       ├── css/          # Fogli di stile
│   │       ├── dist/         # Output di compilazione TypeScript
│   │       └── favicon.svg   # Favicon
│   ├── custom/               # UI personalizzata (gitignored, rilevamento automatico)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # UI aggiuntiva (nome libero)
│       ├── manifest.json
│       └── ...
├── routes/                   # Route API lato server
│   ├── pages.py              # Definizione routing pagine
│   └── ...                   # Vari endpoint API
└── docs/api/                 # Documentazione API
```

### Ordine di risoluzione UI

Quando il server si avvia, determina quale UI usare in questo ordine di priorità:

| Priorità | Condizione | Comportamento |
|----------|-----------|---------------|
| 1 | `config.json` contiene `"ui": "my-theme"` | Usa `ui/my-theme/` specificato |
| 2 | `ui/custom/` contiene un `manifest.json` valido | Rileva e usa automaticamente `ui/custom/` |
| 3 | Nessuno dei precedenti | Usa `ui/default/` come fallback |

### manifest.json

Ogni UI personalizzata richiede un `manifest.json`:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Campo | Obbligatorio | Descrizione |
|-------|------|-----------|
| `name` | Sì | Nome identificativo dell'UI (consigliato: stesso del nome della directory) |
| `version` | Sì | Versione semantica |
| `description` | No | Descrizione dell'UI |
| `author` | No | Nome dell'autore |
| `api_version` | No | Versione API supportata (`"1"`) |
| `type` | No | `"full"` (predefinito) o `"theme"` |

### Distribuzione di file statici

La directory `static/` dell'UI personalizzata è mappata all'URL `/static/` di Flask:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

Riferimento dall'HTML:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### API di gestione UI

È possibile gestire l'UI dalla scheda "UI" della pagina Impostazioni o tramite API:

| Metodo | Percorso | Descrizione |
|--------|------|-----------|
| GET | `/api/ui/list` | Elenco delle UI installate |
| POST | `/api/ui/switch` | Cambia UI attiva (richiede riavvio) |
| POST | `/api/ui/install` | Installa UI da URL (solo localhost) |
| DELETE | `/api/ui/<name>/uninstall` | Disinstalla UI (solo localhost) |

### Strumenti MCP

Puoi gestire l'UI anche tramite MCP (Model Context Protocol):

- `list_uis()` — Elenco UI installate
- `switch_ui(name)` — Cambia UI attiva
- `install_ui(url)` — Installa UI da URL
- `uninstall_ui(name)` — Disinstalla UI
