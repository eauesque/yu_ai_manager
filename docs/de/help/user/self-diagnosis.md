# Selbstdiagnose bei Problemen und Fehlerbericht

Wenn YU AI Manager nicht funktioniert oder sich unerwartet verhält, können Sie hier Hinweise auf die Ursache sammeln und diese an den Entwickler melden. Sie benötigen keine Kenntnisse in Befehlen oder Git.

## 1. Zunächst auf „Problem melden" klicken

1. Öffnen Sie das Anwendungsfenster im Browser und wählen Sie aus dem Menü oben rechts **Diagnostics** aus.
2. Klicken Sie auf die Schaltfläche **„Problem melden"** (Report Issue).
3. Nach kurzer Zeit wird ein Ordner namens `repair/2026XXXX-HHMMSS/` erstellt. Der Inhalt ist ein automatischer Meldesatz mit:
   - Umgebungsinformationen, aktuelle Protokolle und Einstellungen (persönliche Daten und Tokens sind maskiert)
   - Prompt-Vorlagen für die KI-gestützte Reparatur

Wenn Sie auf **„Ordner öffnen"** klicken, wird der Ordner im Explorer geöffnet. Mit **„In ZIP packen"** können Sie alles in einer Datei zusammenfassen.

> Zum Maskieren: Benutzernamen, E-Mail-Adressen, API-Schlüssel, IP-Adressen und ähnliche Strings werden automatisch durch `<REDACTED>` ersetzt. Dies ist nicht vollständig, daher überprüfen Sie den Inhalt vor dem Freigeben.

## 2. Datei freigeben

Fügen Sie die ZIP-Datei an einen Entwickler, Support-Kontakt oder Discord an. Mit der Schaltfläche **„Nachricht für Discord kopieren"** erhalten Sie auch einen kurzen vorgefertigten Text zum Einfügen.

## 3. Selbst durchführbare Übergangslösungen

### 3-A. Umgebungsprüfung (doctor)

Klicken Sie auf der Diagnoseseite auf die Schaltfläche **„Umgebungsdiagnose"** (Environment Diagnostic). Hier werden der Status von Python, GPU, Datenbank usw. als Markdown angezeigt. Probieren Sie die `fix_hint` (Reparaturhinweise) der Elemente mit roter (ERROR) oder gelber (WARN) Kennzeichnung der Reihe nach aus.

### 3-B. Im Safe Mode neu starten

Wenn der normale Start nicht möglich ist, die Anwendung abstürzt oder sich ständig laden lässt, können Sie im **Safe Mode** starten.

- Windows: Doppelklicken Sie auf `start.bat --safe-mode` (oder fügen Sie ` --safe-mode` am Ende der Verknüpfung hinzu)
- macOS / Linux: Geben Sie in einem Terminal `./start.sh --safe-mode` ein

Im Safe Mode können Sie folgende Aktionen durchführen:

- Einstellungen überprüfen
- „Problem melden" und „Umgebungsdiagnose"
- Ein **sicheres Update-Paket (update.zip)** anwenden, das Sie vom Entwickler erhalten (nur Dateiverschleppung, automatisierte Reparaturskripte sind deaktiviert)

Der Safe Mode wird bis zum nächsten normalen Start beibehalten. Nach einem normalen Neustart kehren Sie zum normalen Modus zurück.

### 3-C. Update-Paket (update.zip) anwenden

Wenn Sie ein `update.zip` vom Entwickler erhalten:

1. Gehen Sie zu Diagnostics → Sektion **„Update anwenden"** (Apply Update)
2. Wählen Sie die Datei aus und überprüfen Sie, ob die **Verifikation** (Verify) grün wird
3. Klicken Sie im Bestätigungsdialog auf **Anwenden** (Apply)
4. Folgen Sie den angezeigten Anweisungen zum Neustart

> Wenn die Verifikation rot ist, wenden Sie die ZIP-Datei auf keinen Fall an. Es könnte sein, dass sie manipuliert wurde oder für eine andere Anwendung vorgesehen ist.

Wenn etwas schiefgeht, können Sie mit **„Letztes Update rückgängig machen" (Rollback)** zum vorherigen Status zurückkehren.

## 4. Das sollten Sie nicht tun

- Rohe Protokolle (vor der Maskierung) in sozialen Medien oder öffentlichen Foren veröffentlichen
- `update.zip`-Dateien aus unbekannter Quelle anwenden
- Manuell `data/`-Ordner oder `tags.db` bearbeiten

## Wenn Sie weiterhin Hilfe benötigen

Falls das Problem nicht gelöst ist, melden Sie das ZIP mit einer Beschreibung der durchgeführten Schritte und was passiert ist. Die KI-Seite liest `prompt_for_codex.md` / `prompt_for_claude.md` und erstellt einen Patch-Vorschlag.
