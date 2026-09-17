# Ricerca

## Ricerca di base

Digita tag nella barra ricerca separati da virgola.

```
1girl, blue_eyes, school_uniform
```

## Filtri ricerca

| Filtro | Descrizione |
|---------|------|
| Intervallo date | Filtra da data inizio a data fine |
| Formato file | PNG / WebP / JPG / GIF |
| Valutazione | Filtra per stelle 1-5 |
| Favoriti | Mostra solo elementi aggiunti a favoriti |
| Collezione | Mostra solo dentro collezione specifica |

## Ricerca in prompt

Il campo "in_prompt" consente full-text search nel testo prompt dell'immagine.
Se FTS (Full-Text Search) è abilitato, la ricerca è molto veloce.

## Ordinamento

| Ordinamento | Descrizione |
|--------|------|
| date | Data registrazione (più recenti) |
| date_old | Data registrazione (più antichi) |
| folder | Per folder |
| path | Per path |
| random | Casuale |
| rating_desc | Valutazione (più alta) |
| rating_asc | Valutazione (più bassa) |

## Ricerca semantica

Se Hailo-10H o modello CLIP ONNX è configurato, puoi cercare immagini con linguaggio naturale.
Usa il bottone ricerca semantica a destra della barra ricerca.

### Velocizzazione con FAISS (consigliato)

Per impostazione predefinita ricerca semantica usa NumPy brute-force, ma
**installare FAISS accelera significativamente**.

| Numero librerie | NumPy (default) | FAISS (consigliato) |
|-------------|-------------------|-------------|
| Fino a 10k | Decine ms | Pochi ms |
| 100k | 1-3 secondi | Decine ms |
| 1M+ | 10+ secondi | Meno di 100ms |

FAISS automaticamente sceglie indice ottimale per scala:
- **Meno di 50k**: IndexFlatIP (ricerca completa accurata, abbastanza veloce)
- **50k+**: IndexIVFFlat (approximate nearest neighbor, veloce anche grande scala)

#### Come installare

```bash
# Attiva venv prima di installare
source venv/bin/activate

# x86_64 (Intel/AMD) — installabile direttamente con pip
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — se pip non funziona
# Metodo 1: via conda
conda install -c conda-forge faiss-cpu

# Metodo 2: compila da sorgenti
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

Dopo installazione basta riavviare server e è auto-rilevato.
Se il log mostra:

```
FAISS x.x.x detected — using accelerated vector search
```

FAISS è abilitato.

Se FAISS non è installato, continua a funzionare con NumPy come prima.
