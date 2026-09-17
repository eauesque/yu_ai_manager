# Autodiagnosi e rapporto quando hai problemi

Quando YU AI Manager non funziona o si comporta in modo strano, ecco i passaggi per raccogliere indizi sulla causa e segnalarli agli sviluppatori. Non è necessaria alcuna conoscenza di comandi o Git.

## 1. Prima, premi "Segnala un problema"

1. Apri l'app nel browser e seleziona **Diagnostics** dal menu in alto a destra dello schermo.
2. Premi il pulsante **"Segnala un problema"**.
3. Dopo un momento, verrà creata una cartella `repair/2026XXXX-HHMMSS/`. Il suo contenuto è il seguente set di rapporti automatici:
   - Informazioni sull'ambiente, log recenti, impostazioni (informazioni personali e token sono già mascherati)
   - Modelli di prompt per la riparazione assistita da AI

Premi **"Apri cartella"** per aprirla in Esplora file. Con **"Converti in ZIP"** puoi raggrupparli in un singolo file zip.

> Informazioni sulla mascheratura: nomi utente, e-mail, stringhe che assomigliano a chiavi API e indirizzi IP vengono automaticamente sostituiti con `<REDACTED>`. Poiché non è perfetto, esamina il contenuto una volta prima di condividerlo.

## 2. Condividi

Allega il file ZIP a uno sviluppatore, a una finestra di supporto o a Discord. Il pulsante **"Copia il messaggio per Discord"** prepara anche un breve testo pronto per essere incollato.

## 3. Soluzioni provvisorie che puoi provare

### 3-A. Controllo dell'ambiente (doctor)

Premi il pulsante **"Diagnosi ambientale"** sulla schermata di diagnostica per visualizzare lo stato di Python, GPU, DB e altro in markdown. Prova in ordine gli `fix_hint` (suggerimenti per la correzione) elencati negli elementi in rosso (ERROR) o giallo (WARN).

### 3-B. Riavvia in Safe Mode

Quando l'avvio normale non funziona, l'app si arresta in modo anomalo o la lettura si interrompe indefinitamente, puoi avviare in **Safe Mode**.

- Windows: Doppio clic su `start.bat --safe-mode` (oppure aggiungi ` --safe-mode` alla fine del collegamento)
- macOS / Linux: Dalla riga di comando, esegui `./start.sh --safe-mode`

In Safe Mode puoi fare quanto segue:

- Verificare le impostazioni
- "Segnala un problema" e "Diagnosi ambientale"
- Applicare il **pacchetto di aggiornamento sicuro (update.zip)** fornito dagli sviluppatori (solo sostituzione di file, gli script di riparazione automatica sono disabilitati)

Safe Mode rimane attivo fino al successivo avvio normale. Una semplice riavvio ti riporterà alla modalità normale.

### 3-C. Applica il pacchetto di aggiornamento (update.zip)

Se ricevi `update.zip` da uno sviluppatore:

1. Schermata Diagnostics → sezione **"Applica aggiornamento"**
2. Seleziona il file e verifica che la **Verifica (Verify)** diventi verde
3. Premi **Applica** nella finestra di dialogo di conferma
4. Riavvia seguendo le istruzioni visualizzate

> Non applicare mai uno zip la cui verifica diventa rossa. Potrebbe essere stato alterato o potrebbe essere un pacchetto destinato a un'altra app.

Se accade qualcosa, puoi tornare allo stato precedente con **"Annulla aggiornamento precedente (Rollback)"**.

## 4. Cose da non fare

- Non incollare log non mascherati su social media o forum pubblici
- Non applicare `update.zip` da fonti sconosciute
- Non modificare manualmente la cartella `data/` o `tags.db`

## Se hai ancora bisogno di aiuto

Se il problema persiste, allega il file ZIP insieme a una descrizione di "quale operazione hai eseguito e cosa è accaduto". Il lato AI leggerà `prompt_for_codex.md` / `prompt_for_claude.md` e proporrà una patch di correzione.
