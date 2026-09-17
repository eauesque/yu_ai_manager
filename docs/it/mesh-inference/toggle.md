# Matrice di Inferenza Distribuita

**Versione**: v4.67.0 e successive

## Panoramica

Nella pagina `/mesh-inference` è possibile abilitare/disabilitare per unità di tipo di inferenza ogni peer che partecipa all'inferenza mesh. I target sono 4 tipi: tagger, clip, yolo, whisper.

Questo permette di assegnare ruoli come dedicare la Hailo NPU del Pi5 esclusivamente al tagger, o elaborare clip sull'host GPU, senza toccare la configurazione.

## Utilizzo

1. Cliccare su "Inferenza Distribuita" dalla barra di navigazione
2. Cliccare su ogni cella della matrice per abilitare/disabilitare
   - Spuntato = abilitato (usa quel peer per quel tipo di inferenza)
   - Non spuntato = disabilitato (salta quel peer)
   - — = quel peer non offre quel tipo (non operabile)
3. Il pulsante "Modalità solo locale" disabilita in blocco tutti i peer remoti
4. Lo stato viene persistito automaticamente in `data/mesh_inference_state.json`

## Comportamento

- Le impostazioni vengono mantenute anche per i peer offline (vengono applicate automaticamente alla riconnessione)
- Il pulsante "Modalità solo locale" è premibile solo quando c'è almeno un tipo abilitato localmente
- Se si avvia un batch tagger con tagger disabilitato per tutti i peer, fallisce immediatamente con errore `no_enabled_peers`
- Anche se un peer si disconnette/riconnette temporaneamente per rilevamento mDNS, lo stato di disabilitazione viene mantenuto

## Relazione con il Vecchio Checkbox di Inferenza Distribuita YOLO

Il checkbox "Inferenza Distribuita" nella pagina di rilevamento YOLO è mantenuto per retrocompatibilità e si combina come segue:

| yoloDistributed | Colonna yolo della matrice | Comportamento effettivo |
|---|---|---|
| ON | Tutti i peer abilitati | Distribuzione su tutti i peer come prima |
| ON | Alcuni disabilitati | Salta i peer disabilitati |
| OFF | Ignorato | Solo locale (bypass router) |

## Correlati

- Riferimento API: [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router (livello separato): [../llm-router/](../llm-router/)

## UI Settings

Settings > Mesh Inference tab per controlli toggle per:
- YOLO (object detection)
- CLIP (semantic search)
- LLM (text generation)

## Effetti

- **ON**: Usa remote se disponibile, fallback local
- **OFF**: Solo inferenza locale
- **Prefer local**: Prova local prima, poi remote

## Performance considerate

Toggle remote inference ha overhead network.
Valuta latenza rete vs speedup inference.
