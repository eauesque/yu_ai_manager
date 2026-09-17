# Protocollo QR di YU v1 — Specifica Payload Unificata

**Versione:** 1.0
**Data:** 2026-02-23
**Applicazione target:** YU AI Manager (TagDB)

---

## Panoramica

YU AI Manager supporta la condivisione di prompt e la diagnostica degli errori tramite codici QR.
Questo documento fornisce una specifica unificata per il formato del payload QR.

### Librerie Utilizzate

| Scopo | Libreria | Versione |
|------|-----------|-----------|
| Generazione QR | QRCode.js | 1.0.0 |
| Lettura QR | jsQR | 1.4.0 |

### Limiti di Capacità QR

- Massimo caratteri: **2,953** (livello correzione errori M)
- Sopra 2,500 caratteri: il JSON meta viene minimizzato e ritentato
- Sopra 2,953 caratteri: errore (`qr.info.too_long`)

---

## Tipo Payload 1 — Condivisione Prompt

### Origine

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### Schema JSON

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Definizioni Campi

| Chiave | Tipo | Richiesto | Descrizione | Limite |
|------|-----|------|------|------|
| `v` | string | ✅ | Versione del protocollo. Attualmente `"1.0"` | — |
| `t` | string | ✅ | Tipo payload. Attualmente sempre `"prompt"` | — |
| `p` | string | ✅ | Prompt positivo | 2,000 caratteri |
| `n` | string | ✅ | Prompt negativo | 1,000 caratteri |
| `src` | string | ✅ | Identificatore emittente. Attualmente sempre `"TagDB"` | — |
| `m` | string | — | Nome modello | — |
| `s` | string | — | Valore seed | — |
| `st` | string | — | Conteggio step | — |
| `cfg` | string | — | Scala CFG | — |
| `sa` | string | — | Nome sampler | — |
| `sz` | string | — | Dimensione immagine in formato `"WxH"` | — |

---

## Modalità QR — 4 Tipi

### Modalità `positive`

```
qrText = shareData.p
```

- Contenuto: Solo testo prompt positivo
- Caso d'uso: Condivisione diretta di prompt

### Modalità `negative`

```
qrText = shareData.n
```

- Contenuto: Solo testo prompt negativo

### Modalità `meta`

```
qrText = JSON.stringify(shareData, null, 0)
```

- Contenuto: L'intero payload JSON Condivisione Prompt, compatto
- Ricade a `JSON.stringify` formattato quando il risultato supera 2,500 caratteri

### Modalità `url`

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Contenuto: Un URL alla pagina di condivisione di YU AI Manager
- Disabilitato su localhost (`localhost` / `127.0.0.1`)

---

## Tipo Payload 2 — Diagnostica Errore

### Origine

- Generato su errori HTTP -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### Schema JSON

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Definizioni Campi

| Chiave | Tipo | Descrizione | Limite |
|------|-----|------|------|
| `s` | string | Codice di stato HTTP (`"404"`, `"500"`, ecc.) | — |
| `p` | string | Percorso della richiesta | 80 caratteri |
| `v` | string | Versione applicazione (dal file `APP_VERSION`) | — |

---

## Procedura di Decodifica Condivisione URL

Decodifica sulla pagina di condivisione (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## Parametri Generazione QR

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 sulle pagine di errore
  height:       200,   // 180 sulle pagine di errore
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // Correzione errori 15%
});
```

---

## Estensioni Future (v1.x)

| Funzionalità | Status | Note |
|------|------|------|
| Esportazione QR collezione (più immagini) | Non implementato | Pianificato come tipo payload 3 |
| `t: "collection"` tipo | Non definito | Lista ID file + nome collezione |
| Compressione (gzip + Base64) | Non implementato | Alternativa per prompt che superano 2,953 caratteri |

---

## File di Implementazione

| File | Ruolo |
|----------|------|
| `routes/share.py` | Blueprint API di Condivisione |
| `routes/share_ops/payload_build.py` | Generazione payload |
| `routes/share_ops/prompt_extract.py` | Estrazione dati prompt |
| `core/web/app_factory_handlers.py` | Generazione dati QR errore |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | Costruzione e rendering QR |
| `static/js/runtime/tools/runtime-tools-qr.js` | Handler UI QR |
| `static/js/share/share-qr.js` | Decodifica immagine QR |
| `static/js/share/share-page.js` | Visualizzazione pagina di condivisione |
| `static/vendor/qrcode.min.js` | Libreria QRCode.js |
| `static/vendor/jsQR.min.js` | Libreria jsQR |
