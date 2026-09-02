# Registrazione File Trascinamento e Rilascio

Trascina e rilascia i file immagine/video sulla pagina della libreria principale (`/`) per salvarli
in una directory **Drop Inbox** configurata e registrarli automaticamente nella libreria. Il percorso di scansione normale (`scan_one`) viene utilizzato, quindi l'estrazione dei metadati, la generazione delle miniature e l'etichettatura si eseguono come per una scansione normale.

## Comportamento

1. Con la pagina principale aperta, trascina i file dal file explorer o da un'altra finestra del browser
2. Sullo schermo appare un overlay che mostra il percorso di destinazione (Drop Inbox)
3. Al rilascio, ogni file viene copiato nella Drop Inbox e registrato
4. Un avviso mostra il numero di successi e fallimenti

## Risoluzione Drop Inbox

La Drop Inbox viene risolta in questo ordine di priorità:

1. `drop_inbox_dir` da `config.json` (impostazione esplicita)
2. Se non impostato: viene utilizzato il primo scan root abilitato così come è

**Vincolo**: `drop_inbox_dir` **deve** trovarsi all'interno di una delle voci `scan_roots`.
Qualsiasi percorso al di fuori dei scan root viene rifiutato con HTTP 400. Questo preserva
l'invariante che i scan root sono l'unica fonte di verità per i file della libreria.

## Esempio di Configurazione

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

La `drop_inbox_dir` viene creata se non esiste (il suo padre deve comunque trovarsi
all'interno di `scan_roots`).

## Gestione della Collisione di Nomi

Se un file con lo stesso nome esiste già nella inbox, i suffissi `_1`, `_2`, ...
vengono automaticamente aggiunti. I file esistenti non vengono mai sovrascritti.

## Estensioni Consentite

| Categoria | Estensioni |
|---|---|
| Immagini | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Video | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Gli archivi (`.zip` / `.7z` / `.rar`) **non sono supportati** tramite trascinamento. Posiziona
i file di archivio direttamente in uno scan root ed esegui una scansione regolare.

## Limitazioni

- La dimensione totale della richiesta è limitata a `MAX_CONTENT_LENGTH` (predefinito **100 MB**)
- I nomi file contenenti traversal di percorso (`..`) vengono rifiutati
- Il trascinamento di un'intera directory non è attualmente supportato (solo file singoli)

## API HTTP

### `POST /api/dnd-upload`

Accetta upload di file multipart, li salva nella Drop Inbox e li registra nella libreria.

Risposta:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Restituisce la Drop Inbox attualmente risolta affinché l'overlay dell'interfaccia utente la visualizzi.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Registra un file già presente sul disco per percorso (nessun upload). Il percorso deve trovarsi all'interno
di `scan_roots`. Utilizzato dallo strumento MCP `register_file`.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## Strumenti MCP

| Strumento | Descrizione |
|---|---|
| `register_file(path)` | Registra un file in un percorso assoluto nella libreria |
| `drop_inbox_info()` | Restituisce la directory Drop Inbox attualmente risolta |
