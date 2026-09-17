# Entwicklungsleitfaden

Eine Anleitung zum eigenständigen Erweitern, Anpassen und Debuggen dieser Software.

---

## Grundkonzept

Diese Software wurde von einer Person geschrieben, die Anweisungen und Frustrationen an einen KI-Agenten ausspricht.
Jede Zeile Code wurde von der KI geschrieben.

Das bedeutet: **Sie können dasselbe tun.**

Sie müssen kein Programmierer sein. Sie müssen den Autor nicht bitten.
Alles, was Sie brauchen, ist klar zu denken, genau zu erklären und die Bereitschaft, es zu wiederholen.

Sie brauchen nicht diese schwarze Konsole mit weißem Text.
Werfen Sie zunächst diesen festgefahrenen Gedanken und diese Vorurteile weg.
Dies ist eine großartige Zeit, in der alles visuell gelöst werden kann.

---

## Bevor Sie beginnen

### Was Sie vorher lesen sollten

Wenn Sie beabsichtigen, APIs hinzuzufügen oder zu ändern, lesen Sie zunächst die [API-Sicherheitsrichtlinie](docs/ja/help/developer/api-security.md).

- Öffnen Sie nicht alles über `GET`
- Was sollte bei `read-only API key` erhalten bleiben
- Kriterien für localhost-Bestimmung, Geheimnisse, Konfigurations-API und Validierung

Wenn Sie diesen Leitfaden lesen, ohne neue Routes hinzuzufügen, wiederholen Sie denselben Fehler.

### Holen Sie sich yu_ai_manager

Führen Sie einfach das Installationsprogramm aus.
Folgen Sie dann den Anweisungen auf dem Bildschirm. Das ist alles.

Denken Sie an eine Sache.
Derzeit gibt es keine automatische Aktualisierung. Wenn eine neue Version veröffentlicht wird, führen Sie das Installationsprogramm auf die gleiche Weise aus und ersetzen Sie es.

### Verbinden Sie MCP

Öffnen Sie yu_ai_manager und gehen Sie zu **Settings → API Keys**.
Es gibt einen Bereich namens **MCP Connection Snippet**. Kopieren Sie das JSON mit einem Klick.

Öffnen Sie dann Claude Desktop und klicken Sie auf **Settings (Zahnrad) → Developer → Edit Config**.
Fügen Sie das kopierte JSON ein, speichern Sie es und starten Sie Claude Desktop neu.

Das ist alles. Das ist alles, was Sie brauchen, um eine Verbindung herzustellen.

**Über API-Schlüssel:** Wenn Sie den Snippet nicht verwenden und manuell konfigurieren möchten, erstellen Sie einen Schlüssel in **Settings → API Keys**. Ein Schlüssel, der mit `sk_...` beginnt, wird nach dem Erstellen nur einmal angezeigt. Kopieren Sie es sofort.

### Überprüfen Sie Ihre Umgebung

1. Läuft yu_ai_manager? — Starten Sie es und überprüfen Sie
2. Läuft der MCP-Server? — Überprüfen Sie in den Claude Desktop-Einstellungen
3. Können Sie einen KI-Agenten verwenden? — Claude Desktop oder ähnliches

Das ist alles. Fertig vorbereitet.

### Git-Hooks aktivieren (nur für Knoten, die mit Git entwickeln/pushen, einmal nach dem Klonen)

Wenn Sie dieses Repository mit Git bearbeiten (Commits oder Pushes durchführen), führen Sie dies nach dem Klonen einmal aus.

```bash
git config core.hooksPath .githooks
```

Dies aktiviert die Überprüfungen in `.githooks/` für Pre-Commit und Pre-Push (Lint, Typ, verschiedene Drift-Überprüfungen).
**Wenn Sie dies nicht festlegen, schlafen die Überprüfungen.** Selbst wenn die Logik korrekt ist, funktioniert sie nicht als Kontrollpunkt, sodass Drift einschleicht (dies ist tatsächlich der Grund, warum die Dokumentationsindizes durcheinander geraten sind).

Die Überprüfung ist einfach. Wenn `.githooks` zurückkommt, ist es alles.

```bash
git config --get core.hooksPath
```

Jeder Knoten benötigt dies einmal (diese Git-Einstellung ist eine lokale Einstellung pro Klon und wird nicht gemeinsam genutzt).

---

## Verwenden Sie MCP

Wenn der MCP-Server läuft, müssen Sie ihn verwenden.

yu_ai_manager hat Hilfe-Endpunkte für KI-Agenten. Über MCP können Sie direkt auf die Datenbank, Protokolle, Einstellungen und **sogar den Quellcode selbst** zugreifen.
Es ist schneller und genauer, es dem MCP direkt zu zeigen, als es durch die Browser-UI zu erklären.
Sagen Sie dem KI-Agenten einfach:

Stellen Sie eine Verbindung zum MCP-Server von yu_ai_manager her.

```
Überprüfen Sie die Hilfe-Endpunkte und sagen Sie mir, was Sie tun können.

```

### Quellcode mit MCP lesen lassen

yu_ai_manager verfügt über ein eingebautes Quellcode-Referenztool.

- **source_tree** — Dateisystem in Baumstruktur anzeigen
- **source_read** — Inhalt einer bestimmten Datei lesen
- **source_search** — Volltextsuche im gesamten Quellcode

KI-Agenten können diese verwenden, um Quellcode direkt im Chat zu lesen.
Sie müssen nicht einen Ordner in GitHub Desktop öffnen und es Claude Code übergeben.

Wenn Sie den Quellcode referenzieren möchten, können Sie folgendes sagen:

```
Überprüfen Sie die Dateisystem-Struktur mit source_tree,
und lesen Sie die relevanten Dateien mit source_read.
```

---

## Funktionen hinzufügen

Bitten Sie den Autor nicht, Funktionen zum Core hinzuzufügen. Die Antwort ist Nein.

Verwenden Sie das Erweiterungssystem.
**Alles kann in Claude Desktop Chat erledigt werden.** Sie müssen nicht Ihren Schreibtisch verlassen.

### Schritt 1: Entscheiden Sie im Chat, was Sie erstellen möchten

Sagen Sie nicht einfach "machen Sie".

Besprechen Sie zunächst im Claude Desktop-Chat, was Sie tun möchten. „Ich möchte diese Funktion" oder „Ich möchte diese Operation automatisieren" — sprechen Sie mit der KI darüber, während Sie dies artikulieren.
Sobald Sie klar haben, was Sie erstellen möchten, sagen Sie:

Die KI erstellt eine Spezifikation.

```

```



### Schritt 2: Lassen Sie es direkt implementieren

Sie müssen nicht ins Arbeitszimmer gehen. Fahren Sie im selben Chat fort:

```
Die Spezifikation ist bereit. Implementieren Sie sie bitte als Erweiterung.
Erstellen Sie ein Grundgerüst mit create_extension, schreiben Sie Code mit write_extension_file.
Überprüfen Sie mit validate_extension, ob es Probleme gibt.
```

Die KI erstellt und bearbeitet Erweiterungsdateien direkt über MCP.
Alles wird mit nur einem Chat auf Ihrem Schreibtisch erledigt.

**Aber ob Sie es so machen, entscheiden Sie selbst.**

Verwenden Sie die Vorschläge der KI als Referenz. Sie sind jedoch nicht verpflichtet, sie zu befolgen.
Der Zweck liegt bei Ihnen, nicht bei der KI.
Treffen Sie die Entscheidung.

Wenn Sie sich einigen können, lassen Sie es implementieren. Wenn etwas falsch ist, teilen Sie dies mit. Wiederholen Sie, bis es funktioniert.

Starten Sie yu_ai_manager neu, wenn die Erweiterung fertig ist.
Eine neue Erweiterung erscheint in Settings → Extensions. Überprüfen Sie die Berechtigungen und genehmigen Sie sie zum Ausführen.

### Schritt 3: Teilen Sie es (Optional)

Wenn Sie etwas Nützliches erstellen, können Sie es teilen.
Andere Menschen entscheiden, ob sie es verwenden. We made, you decide.

---

## Melden Sie einen Fehler

### Schritt 1: Protokolle abrufen

Öffnen Sie yu_ai_manager und gehen Sie zu **Settings → Logs**.
Kopieren Sie die Protokolle vor und nach dem Problem.

Wenn Sie die Protokolle nicht finden, beschreiben Sie bitte genau:
- Was du getan hast
- Was du erwartet hast, dass passiert
- Was tatsächlich passiert ist

"Etwas stimmt nicht" ist keine Beschreibung.

### Schritt 2: Machen Sie einen Screenshot oder Video

Wenn das Problem visuell ist und nicht mit Worten erklärt werden kann:

- **Screenshot**: `Windows + Shift + S`
- **Bildschirmaufzeichnung**: `Windows + Shift + R`

Auf dem Mac: Screenshot ist `Cmd + Shift + 4`, Aufzeichnung ist `Cmd + Shift + 5`

Sie können Bilder direkt in den Chat ziehen.
Ein Bild ist viel wertvoller als Tausende von verworrenen Erklärungen.

**Sie können auch sehen, was im Browser passiert.**

Drücken Sie `F12` im Browser. Ein Fenster öffnet sich an der Seite des Bildschirms.
Sie müssen noch nicht verstehen, was es bedeutet. Denken Sie einfach daran.

Wenn ein KI-Agent sagt: "Öffnen Sie F12 und überprüfen Sie Fehler", ist dies hier.
Wenn rote und gelbe Dinge auftauchen, wählen Sie alles aus, kopieren Sie es und geben Sie es dem Agenten.
Das ist alles, was Sie brauchen.

### Schritt 3: Auf GitHub posten

Posten Sie Protokolle und Screenshots auf einem GitHub-Issue.
Der Autor sieht es vielleicht. Irgendwann. Keine Garantie.

Wenn Sie es sofort beheben möchten, gehen Sie zum nächsten Abschnitt.

---

## Fehler selbst beheben (empfohlen)

Es ist schneller, als auf den Autor zu warten. Wirklich.

### Werkzeuge

**Claude Desktop Chat + MCP.** Das ist alles.

Denken, recherchieren, beheben — alles wird hier erledigt.
Mit MCP können Sie Erweiterungsdateien lesen und schreiben sowie Code-Scans ausführen.
Sie brauchen sonst nichts.

### Ablauf des Debuggens

Beschreiben Sie das Problem im Claude Desktop-Chat.
Protokolle, Screenshots, was Sie getan haben, was Sie erwartet haben — alles werfen.

Mit MCP kann die KI Quellcode direkt lesen und den Zustand des Systems überprüfen. Sagen Sie:

```
Wenn ich in yu_ai_manager [X] klicke, passiert [Y]. Es sollte eigentlich [Z] sein.
Überprüfen Sie die Backend-Protokolle und den Status mit MCP.
Lesen Sie auch die entsprechenden Quellen mit source_tree und source_read.
Identifizieren Sie die Ursache und beheben Sie sie.
```

Die KI identifiziert die Ursache und schlägt eine Lösung vor.
Wenden Sie die Lösung mit write_extension_file an und überprüfen Sie mit validate_extension.
Starten Sie yu_ai_manager neu und überprüfen Sie, ob es funktioniert.

### Was Sie dem KI-Agenten geben

1. **Fehlerprotokoll** — Roher Text, nicht paraphrasiert
2. **Screenshot oder Video** — Für visuelle Fehler
3. **Was Sie getan haben** — Die Operation, bei der das Problem auftrat
4. **Was Sie erwartet haben** — Wie es sein sollte
5. **Zweck** — Nicht nur die Symptome, sondern warum es notwendig ist

### Wenn die KI Sie nicht versteht

Die KI ist keine Person. Sie kann manchmal Teile, die Sie auslassen, nicht ergänzen.

- Sie kann dich fragen — antworte genau
- Es funktioniert möglicherweise nicht wie gewünscht — erkläre genau, was anders ist
- Wenn die Antworten immer daneben liegen, versuchen Sie eine andere Formulierung
- Wenn Sie feststellen, dass Informationen fehlen, fügen Sie sie hinzu
- Wenn Worte nicht funktionieren, geben Sie relevante Dateien

Dies ist iterative Arbeit. Es funktioniert. Machen Sie weiter.

Es ist wirklich dasselbe wie Anweisungen für einen Menschen. Aber da Gesichtswahrer, Laune und Emotionen nicht relevant sind, ist es viel einfacher.

---

## Räumen Sie zuerst die sichtbaren Dinge auf

Beseitigen Sie sichtbare Fehler, bevor Sie unsichtbare beseitigen.
Es hat keinen Sinn, Insektizide auf einem Spielfeld voller Unkraut zu verteilen. Zuerst müssen Sie den Boden vorbereiten.

Sie haben etwas implementiert. Es sieht aus, als würde es funktionieren. Aber ob die Außenseite wirklich richtig funktioniert, ist oft nicht sicher, wenn Sie mit der Maus herumklicken. Man übersieht Dinge. Mit Erfahrung bemerkt man es nicht mehr.

Verwenden Sie Playwright. Ein KI-Agent wird Ihren Browser tatsächlich bedienen und die UI überall überprüfen.

Sagen Sie dem KI-Agenten:

```
Bedienen Sie yu_ai_manager mit Playwright, um Bugs und UX-Bewertungen und Verbesserungsvorschläge zu machen.

```

Der Agent bedient den Browser, findet zerbrochene Layouts, nicht funktionierende Tasten, unnatürliche Operationsflüsse, verwirrende Navigation — und zeigt diese Probleme und Vorschläge. Nicht nur Fehlerbehebung, sondern auch Punkte wie "Das ist schwer zu bedienen".

Ob Sie akzeptieren, entscheiden Sie, aber hören Sie alles zuerst.

Danach können Sie zu den unsichtbaren Problemen übergehen.

---

## Beseitigen Sie alle unsichtbaren Fehler

Sichtbare Fehler können behoben werden. Das Problem ist unsichtbar.

Stellen Sie sich den Bereich unter dem Kühlschrank vor. Es gibt nur eine Schabe, die vorne zu sehen ist.
Aber wenn Sie den Kühlschrank bewegen, gibt es eine andere Welt darunter.
Software ist dasselbe. Fehler, die nicht im Protokoll auftauchen, Fehler, die nicht reproduziert werden, Fehler, die niemand gefunden hat — sie existieren wirklich.
Es ist praktisch unmöglich, dass Menschen sie alle finden.

MCP debug ist dieses Insektizid.

### Wie man es macht

Sagen Sie dem KI-Agenten:

```
Stellen Sie eine Verbindung zum yu_ai_manager MCP her und debuggen Sie den gesamten Quellcode.
Verwenden Sie source_tree, um die Dateisystem-Struktur zu verstehen, und lesen Sie sie mit source_read der Reihe nach.
Melden Sie alle möglichen Fehler, Konsistenzprobleme und fehlerleitenden Stellen.
```

Die KI liest Quellen, überprüft den tatsächlichen Zustand des Systems mit MCP und entdeckt versteckte Probleme.
Wenn ein Bericht ankommt, lassen Sie es beheben.

### Fragen Sie hartnäckig

Beenden Sie es nicht beim ersten Mal.

Wenn der Agent sagt "Das ist alles", antworte:

```
Gibt es noch etwas?
```

Wiederholen Sie dies. Der Agent gräbt jedes Mal ein wenig tiefer.
Wenn sie wirklich sagen, dass es nichts mehr gibt, ist es wahrscheinlich wirklich nicht vorhanden.

Hartnäckigkeit ist keine Tugend. Aber gegenüber Fehlern ist Hartnäckigkeit Gerechtigkeit.

---

## Führen Sie vor der Veröffentlichung eine Sicherheitsüberprüfung durch

Wenn Sie eine Erweiterung veröffentlichen möchten, lassen Sie sie vorher überprüfen.

Es ist nicht schwierig. Es geht schnell.

Sie müssen nur dem KI-Agenten sagen:

```
Führen Sie eine Sicherheitsüberprüfung für diese Erweiterung (oder diesen Code) durch.
Überprüfen Sie die Einstellungen und Sandbox-Informationen von yu_ai_manager auch mit MCP.
Lesen Sie die entsprechenden Dateien mit source_read, und melden Sie alle Probleme.
```

yu_ai_manager verfügt über eine eingebaute Code-Scan-Funktion für Erweiterungen.
Dies wird beim Laden einer Erweiterung automatisch ausgeführt. Starten Sie den Server neu und laden Sie die Erweiterung einmal.

Der Scan erkennt automatisch:
- Gefährliche Module (`subprocess`, `ctypes`, `importlib`)
- Direkter DB-Betrieb (`sqlite3` — SandboxedDB verwenden)
- Dynamische Code-Ausführung (`eval`, `exec`, `__import__`)
- Netzwerkzugriff (`requests`, `urllib` usw.)

Wenn es schwerwiegende Probleme gibt, wird das Laden der Erweiterung verweigert. Wenn es nur eine Warnung ist, wird es geladen, aber im Protokoll vermerkt.
Überprüfen Sie die Protokolle und beheben Sie alle Probleme.

Wenn Sie Code auf anderen Systemen ausführen, übernehmen Sie diese Verantwortung.

Für Details zum Sicherheitsmodell, lesen Sie „[Sicherheitsmodell der Erweiterung](docs/ja/help/developer/extension-security.md)".

---

## Berühren Sie nicht den Core

Mit einer Erweiterung haben Sie eine geschützte Welt.
Wenn Sie das schützende System selbst — core und eingebaute Erweiterung — ändern, vergessen Sie nicht, dass dies alles betreffen kann und **dass Sie selbst auch betroffen sein können**.

Wenn Sie die Tauri-Version verwenden oder nicht, Sie können den Core und eingebaute Erweiterungen von Claude Desktop aus nicht ändern.
Es ist nicht "sollte nicht", sondern **es ist technisch unmöglich**.
Der Pfad existiert in der API nicht. Sie können nicht berühren, was Sie nicht sehen.

Wenn Sie wirklich berühren müssen, verwenden Sie die Python-Version. Das ist alles.

---

## Über Geduld

KI-Agenten sind mächtig, aber keine Magie. Einige Probleme erfordern mehrere Versuche.

Wenn Sie ungeduldig werden:
- Treten Sie einen Schritt zurück
- Lesen Sie noch einmal, was Sie mitgeteilt haben
- Überlegen Sie, welche Informationen fehlen
- Versuchen Sie einen anderen Winkel

Das Problem wird gelöst. Was erforderlich ist, ist nicht Wut, sondern klares Denken.

---

## Zum Abschluss

KI ist ein intelligentes Baugerät.

Selbst mit schwerem Gerät kann man nicht bohren, wenn man es nicht fahren kann. Ein Mensch, der es fahren kann, leistet das Werk von Dutzenden. Aber was gegraben werden soll und wo gebaut werden soll, entscheidet immer noch der Mensch. Selbst wenn das Werkzeug klüger wird, hat immer noch der Mensch den Zweck.

Der Autor hat diese Software in 18 Tagen geschrieben, während er einem KI-Agent sagte, was zu tun ist.
Jede Funktion, jede Reparatur, jede Designentscheidung entstand aus Gesprächen.

Umgekehrt, die Grundlagen in diesem Dokument sind alles, was Sie brauchen, um etwas in diesem Ausmaß zu erstellen.

Die Grundlagen sind alltäglich langweilig.
Aber das ist der erste Schritt zum Stapeln von Dammsteinen.
Die Art, Steine zu stapeln, die Winkelkorrektionen — das lernt man mit der Zeit.
Sogar komplexe und schwierige Probleme können schließlich gelöst werden.

Aber wenn die Grundlagen vernachlässigt werden, bricht selbst eine kleine Sache zusammen.

Unterschätzen Sie nicht das Oben Geschriebene.
Um die Grundlagen zu festigen, ist es am wichtigsten, die Grundlagen der Ihr eigenen Techniken zu festigen.

Das Werkzeug ist hier. Die Dokumentation auch.

**Go for it.**
