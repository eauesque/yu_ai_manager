# LAN Cowork

> Versione target: v4.55.0 e successive (autenticazione PIN disponibile da v4.92.0)

## Cos'è LAN Cowork?

LAN Cowork è una funzionalità di estensione che consente il coordinamento tra più nodi yu_ai_manager su una rete.  
Ogni macchina funziona in modo indipendente, consentendo la distribuzione di processi pesanti o la gestione collettiva come Fleet.

```
┌──────────────┐    Scoperta mDNS     ┌──────────────┐
│  Windows PC  │◄───────────────────────►│   Mac Mini   │
│ (GPU attivo) │   Associazione PIN    │ (Controllo)  │
│              │◄───────────────────────►│              │
│  Inferenza   │                       │  Gestione    │
│  distribuita │                       │   Fleet      │
│(etichetta)   │                       │              │
└──────────────┘                       └──────────────┘
        ▲                                      ▲
        └──────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Panoramica delle funzionalità

| Funzionalità | Descrizione |
|---|---|
| **Scoperta automatica mDNS** | Scopri automaticamente i nodi sulla stessa LAN senza configurazione |
| **Associazione PIN** | Autenticazione PIN approvata dall'amministratore per l'emissione di token inter-peer |
| **Inferenza distribuita** | Elaborazione parallela di tagger, CLIP, YOLO e Whisper su più nodi |
| **Distribuzione della generazione** | Delegare i lavori SD WebUI / ComfyUI ai nodi LAN |
| **Gestione Fleet** | Gestione centralizzata dei log e degli aggiornamenti delle versioni su tutti i nodi |
| **Inoltro eventi peer** | Trasmetti gli eventi da altri nodi al tuo SSE |
| **Routing LLM** | Registra automaticamente i peer scoperti in LLM Router |

---

## Passaggi di configurazione

### 1. Abilitazione

Aggiungi a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Nota**: Questa pagina indicava in precedenza la chiave di attivazione al livello superiore come `{"lan_cowork": {...}}`, ma nessuna implementazione legge una chiave in quella posizione. La sezione `extensions` sopra indicata è la posizione corretta.

> **Il valore predefinito dipende dal backend:** il backend Python (ibrido) considera una chiave mancante come **abilitata**, mentre il server Rust standalone è **disabilitato** salvo abilitazione esplicita. Per sapere cosa accade effettivamente in rete una volta abilitato, vedere [Comportamento di rete](network-behavior.md).

Dopo il riavvio:
- Ascolta gli altri nodi su UDP 19850
- Inizia ad annunciare _yu-ai._tcp.local. tramite mDNS

### 2. Associare i nodi

Per connettersi dal Nodo A al Nodo B:

1. **Interfaccia Web Nodo A** → `Impostazioni` → `LAN Cowork` → Aggiungi URL Nodo B
2. Il Nodo A invia `POST /api/lan/pair/request`
3. **Interfaccia Web Nodo B** → `/lan-cowork/peers` → Approva nella scheda "Approvazione in sospeso"
4. PIN a 6 cifre viene inviato al Nodo A (tramite SSE)
5. Il Nodo A inserisce il PIN → Ottieni token Bearer (valido 30 giorni)

> **Nota**: L'associazione è unidirezionale. Eseguire sia A→B che B→A.

Vedi [Autenticazione PIN tra peer e Associazione token](peer-auth.md) per i dettagli.

### 3. Verificare il funzionamento

```bash
# Elenco dei peer scoperti (dal Nodo A)
curl http://localhost:5000/api/mdns/peers

# Peer riconosciuti da LAN Cowork
curl http://localhost:5000/api/lan/peers
```

---

## Configurazione specifica della funzionalità

### Inferenza distribuita

L'inferenza distribuita diventa disponibile automaticamente dopo il completamento dell'associazione.

- `Impostazioni` → `LAN Cowork` → Abilita tipi di inferenza (tagger/CLIP/YOLO/Whisper) per ogni nodo
- O configura singolarmente tramite la matrice nella pagina `/mesh-inference`

Dettagli: [Configurazione dell'inferenza distribuita](../mesh-inference/setup.md)

### Gestione Fleet

Configurare un nodo "chief" per gestire gli altri nodi:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Dettagli: [Gestione Fleet](../features/fleet-admin.md)

### Distribuzione della generazione (Delega lavori SD / ComfyUI)

Distribuisci automaticamente i lavori di generazione ai nodi equipaggiati con GPU. Disponibile tramite registrazione backend del file di configurazione o scoperta automatica mDNS.  
Se il Nodo B esegue SD WebUI / ComfyUI, diventa disponibile immediatamente dopo la configurazione.

---

## Requisiti di rete

| Porta / Protocollo | Scopo | Richiesto |
|---|---|---|
| UDP 5353 | mDNS (scoperta nodi) | Solo stessa LAN L2 |
| UDP 19850 | Scoperta LAN Cowork | Solo stessa LAN L2 |
| TCP 5000 (predefinito) | API, associazione, inferenza | Tra peer |

- mDNS non funziona attraverso router o VPN (usa IP fissa o nome host `.local`)
- Assicurati che UDP 5353 e TCP 5000 siano aperti sulla LAN nel tuo firewall

---

## Indice della documentazione

| Documento | Contenuto |
|---|---|
| [Autenticazione PIN tra peer](peer-auth.md) | Flusso di associazione, gestione token, configurazione di sicurezza |
| [Configurazione dell'inferenza distribuita](../mesh-inference/setup.md) | Passaggi per parallelizzare l'inferenza su più nodi |
| [Matrice d'inferenza distribuita](../mesh-inference/toggle.md) | Abilita/disabilita per peer e per tipo tramite WebUI |
| [Architettura dell'inferenza distribuita](../mesh-inference/overview.md) | Design interno, work stealing, persistenza |
| [Gestione Fleet](../features/fleet-admin.md) | Gestione centralizzata dei log remoti e degli aggiornamenti delle versioni |
| [API Peer mDNS](../api/mdns-peers.md) | Dettagli degli endpoint `/api/mdns/*` |

---

## Sicurezza

- mDNS non ha autenticazione. **Usa solo su LAN domestiche o reti affidabili**
- Su Wi-Fi pubblico o LAN condivise, disabilita con `"mdns": {"enabled": false}`
- La comunicazione tra peer è protetta da token Bearer dall'associazione PIN (archiviati come hash scrypt)
- `ip_check_mode: strict` consente solo l'IP da cui è stato emesso il token (predefinito)
