# Guida di Configurazione dell'Inferenza Distribuita

> Versione target: v4.67.0 e successive

## Che cos'è l'Inferenza Distribuita?

Una funzionalità in cui più nodi yu_ai_manager collaborano per **parallelizzare e distribuire** l'elaborazione dell'inferenza come etichettatura, CLIP, YOLO e riconoscimento vocale. È possibile condividere scansioni di file di grandi dimensioni su più macchine o delegare l'etichettatura a un Pi5 con Hailo NPU.

```
┌──────────────┐   Lotto di Immagini ┌──────────────┐
│    Local     │ ──────────────────► │  Pi5 (Hailo) │  tagger × 200 immagini
│    (Scan)    │ ──────────────────► │ Macchina GPU │  tagger × 300 immagini
│              │ ──────────────────► │    Local     │  tagger × 100 immagini
└──────────────┘   Lavoro            └──────────────┘
                  Condiviso
```

---

## Prerequisiti

Le seguenti condizioni devono essere soddisfatte su ogni nodo:

1. yu_ai_manager è in esecuzione
2. **L'estensione LAN Cowork è abilitata** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. I nodi sono **accoppiati tra loro** ([Guida all'Autenticazione dei Peer](../lan-cowork/peer-auth.md))
4. I motori di inferenza da utilizzare sono configurati su ogni nodo (ONNX / Hailo / Whisper, ecc.)

---

## Passaggi di Configurazione

### Passaggio 1: Abilitare LAN Cowork su ogni Nodo

In `config.json` su tutti i nodi:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

Dopo il riavvio, i nodi si scopriranno automaticamente tramite mDNS.

### Passaggio 2: Completare l'Accoppiamento

Eseguire l'accoppiamento tra tutte le coppie di nodi (bidirezionale).
Dettagli: [Autenticazione PIN dei Peer e Accoppiamento dei Token](../lan-cowork/peer-auth.md)

### Passaggio 3: Verificare la Matrice di Inferenza Distribuita

Aprire `/mesh-inference` su qualsiasi nodo.

I nodi accoppiati appaiono come righe, i tipi di inferenza appaiono come colonne:

| Nodo | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| Local | ☑ Abilitato | ☑ Abilitato | ☑ Abilitato | ☑ Abilitato |
| pi5-hailo | ☑ Abilitato | ☑ Abilitato | — Non Disponibile | — Non Disponibile |
| gpu-win | ☑ Abilitato | ☑ Abilitato | ☑ Abilitato | ☑ Abilitato |

- **☑ Abilitato**: Usa questo nodo per l'inferenza
- **☐ Disabilitato**: Salta (può essere alternato manualmente)
- **—**: Questo nodo non ha il motore di inferenza target (non può essere utilizzato)

### Passaggio 4: Verificare il Funzionamento

Eseguire un batch di etichettatura e confermare nei log che vengono utilizzati più nodi:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Requisiti per Tipo di Inferenza

| Tipo | Motore Richiesto | Descrizione |
|---|---|---|
| `tagger` | ONNX (WD14, ecc.) o Hailo NPU | Etichettatura in stile Danbooru per immagini |
| `clip` | ONNX CLIP o Hailo | Vettori di embedding semantico per immagini (per ricerca semantica) |
| `yolo` | ONNX YOLO | Rilevamento di oggetti nelle immagini |
| `whisper` | faster-whisper o remoto | Trascrizione da voce a testo per audio/video |

I nodi senza un motore configurato mostreranno "—" per quel tipo e non verranno instradati per quel tipo.

---

## Esempi di Progettazione del Ruolo

### Esempio 1: Dedicare Pi5 + Hailo NPU per l'Etichettatura

Assegnare Pi5 esclusivamente per l'etichettatura per ridurre il carico su altri nodi.

Configurazione della matrice:
- Pi5: tagger ☑, altri ☐
- Local: clip ☑, yolo ☑, whisper ☑, tagger ☐ (delegare a Pi5)

### Esempio 2: Scansione in Massa Veloce

Abilitare tagger sia sulla macchina GPU che sulla macchina locale, condividendo automaticamente i file tramite il lavoro condiviso. Non è necessaria alcuna divisione manuale.

### Esempio 3: Modalità Solo Locale (Temporanea)

Fare clic sul pulsante "Modalità Solo Locale" in `/mesh-inference` per disabilitare tutti i peer remoti contemporaneamente. Utile in caso di disconnessione della rete.

---

## Risoluzione dei Problemi

### Il Peer Non Appare nella Matrice

1. Verificare che il peer sia riconosciuto con `/api/lan/peers`
2. Confermare che l'accoppiamento è completo ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Verificare che LAN Cowork sia abilitato sul nodo remoto

### L'Instradamento verso un Nodo Specifico Non Funziona

- Verificare che il tipo target per quel nodo mostri ☑ nella matrice
- Verificare che la risposta di `/api/lan/peers` mostri `status: "online"` per quel nodo
- Verificare che il battito del nodo remoto sia in arrivo (cercare `heartbeat` nei log)

### Tutto Viene Elaborato Localmente

Se tutti i peer remoti sono offline o disabilitati, si verifica un fallback locale automatico.
Questo è un funzionamento normale (non un errore).

### Errore `no_enabled_peers`

Quel tipo è disabilitato su tutti i nodi.
Abilitare almeno 1 nodo per quel tipo nella matrice.

---

## Documentazione Correlata

- [Architettura dell'Inferenza Distribuita](overview.md) — Progettazione interna del lavoro condiviso e DisableAwareStrategy
- [Matrice di Inferenza Distribuita](toggle.md) — Dettagli sull'operazione WebUI
- [Panoramica di LAN Cowork](../lan-cowork/README.md) — Configurazione complessiva di LAN Cowork
- [Autenticazione PIN dei Peer](../lan-cowork/peer-auth.md) — Procedura di accoppiamento
