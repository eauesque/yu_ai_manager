# Playbook di manutenzione dei test

Raccolta dei punti da controllare per primi quando pytest si blocca a causa di vecchie infrastrutture di test o dipendenze dall'ambiente.

## Obiettivo

- Distinguere `failed` da `skipped`
- Distinguere gli skip legittimi dovuti all'ambiente dai test stale da riparare
- Fissare il percorso più breve quando un broad run (`pytest tests -q --maxfail=1`) si blocca

## Comandi di base

Verifica generale standard:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

Verifica anche i motivi degli skip:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

Trattare lo shared test server in modo strict:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

Audit delle licenze:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## Come leggere gli skip attuali

Al 2026-04-21, nel broad run i principali motivi di skip si distribuiscono lungo queste 5 categorie.

### 1. Shared Test Server non avviato

È lo skip più frequente. Lo shared server in `tests/conftest.py` viene avviato best-effort: se non riesce ad avviarsi, i test che dipendono da browser/server vengono declassati a skip invece che a fail.

Motivi tipici:

- `Shared test server unavailable on port <PORT>`

Principali bersagli:

- `tests/api/`
- test browser UX review
- test LAN Cowork / Fleet dipendenti da browser/server
- live browser test che usano `TARGET_URL` / `BASE` / `TARGET`
- test di audit che usano fixture Playwright/WebKit proprie invece della fixture `page`

In un run normale è uno **skip legittimo**. Tuttavia, è da indagare se:

- anche gli unit test che non dipendono dallo shared server finiscono in skip per lo stesso motivo
- test shared server che prima passavano improvvisamente diventano massicciamente skip
- la causa non emerge nemmeno con `PYTEST_STRICT_AUTOSTART_SERVER=1`

### 2. Test specifici del sistema operativo

Test sandbox / AppArmor / process isolation specifici di Linux. Su Windows lo skip è corretto.

Esempi rappresentativi:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

Motivi tipici:

- `Linux only`
- `AppArmor è dedicato a Linux`

Questo è uno **skip legittimo**.

### 3. Dipendenze opzionali o componenti esterni mancanti

Test che non vengono eseguiti in ambienti privi di particolari pacchetti o nodi esterni.

Esempi rappresentativi:

- mDNS E2E su hardware reale: `optional zeroconf package is not installed`
- Avvio del browser: `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / nodi di inferenza esterni non collegati

Questo è uno **skip legittimo**. Non è un elemento da riparare: è solo l'ambiente prerequisito che non è pronto.

### 4. Dati di test insufficienti

Test browser che richiedono immagini, risultati di ricerca, log di conversazione o più record di dati, e che vengono skippati perché un DB leggero non li soddisfa.

Motivi tipici:

- `No search results available in database`
- `Skip poiché non ci sono immagini nel DB`
- `Richiesti almeno 2 file`
- `No prompts to test copy`

Questo è **generalmente uno skip legittimo**. Tuttavia, per i test in cui dovrebbe essere la fixture a preparare i dati necessari, si sospetti che siano diventati stale.

### 5. Rate limit / protezione delle API esterne

Parte dei test di integration rispetta servizi esterni o rate limit e viene skippata.

Esempi rappresentativi:

- `Skip per rate limit raggiunto`

Questo è uno **skip legittimo**.

### 6. Fuzz / burn-in di lunga durata

Il burn-in sotto `tests/fuzz/` non è per il normale controllo di regressione, ma per verifiche aggiuntive di durabilità e resistenza al crash.

Per impostazione predefinita viene escluso dalle espressioni di marker in `pytest.ini`.

Per eseguirlo:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

Se necessario:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

Questo **non va mescolato al broad run standard**.

## Pattern da trattare come anomalie

Non archiviare con "è solo uno skip, nessun problema" — considerare come oggetto di manutenzione i casi seguenti.

### A. Un test leggero che prima passava ora finisce in setup skip

Esempi:

- Uno smoke API che dovrebbe completarsi con le fixture app/client viene trascinato in una dipendenza dallo shared server
- Unit test su migrazione / schema / DB helper cadono perché presuppongono lo stato globale runtime inizializzato

In questi casi, sospettare una divergenza tra i presupposti del test harness e quelli dell'implementazione.

### B. Il broad run passa, ma l'esecuzione singola fallisce

Esempi tipici:

- Dipende da stato process-global
- Si basa su effetti collaterali che un test precedente ha inizializzato per caso durante il broad run

Anche l'esecuzione singola deve tornare a uno stato riproducibile.

### C. Motivo di skip vago

Esempi negativi:

- `failed`
- `not ready`
- `something wrong`

Lo skip reason dovrebbe indicare in una breve frase "cosa manca, quindi è stato saltato".

## Priorità di riparazione

1. Correggere gli hard failure che bloccano il broad run
2. Correggere i test stale che si rompono solo in esecuzione singola
3. Riportare gli skip shared server/browser a skip sicuri anziché fail
4. Mantenere come optional skip le dipendenze opzionali o quelle dall'hardware reale

## Cosa è stato fissato con questa manutenzione

- Le dipendenze da browser/server sono unificate: shared server non disponibile → skip, non fail
- Il license audit osserva solo le dipendenze dichiarate in `requirements*.txt`, non l'intero venv
- Il test DB soddisfa il prerequisito di path FTS dello schema di ricerca attuale
- Le migrazioni 54 / 55 sono state corrette in modo da non essere fragili rispetto all'evoluzione dello schema base o allo stato runtime non inizializzato

## Criterio di giudizio nei casi dubbi

- Se manca solo l'ambiente prerequisito, va bene come skip
- Se sono aspettative vecchie che non seguono l'implementazione attuale, correggere il test
- Se dipende da effetti collaterali del broad run, correggere implementazione o test
- Se un unit test richiede stato process-global, sospettare il design
