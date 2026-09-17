# Sicherheitsmodell für Extensions

Diese Software zeichnet sich dadurch aus, dass "jeder Extensions mit KI erstellen kann".
Gleichzeitig sind Schutzmechanismen eingebaut, die Ihr System vor bösartigen Extensions schützen.

Diese Seite erklärt, wie diese Mechanismen funktionieren.
Geschrieben so, dass auch Nicht-Techniker sie verstehen können.

---

## Grundlegendes Konzept

Extensions laufen in einer **geschützten Welt**.

Innerhalb dieser geschützten Welt können Extensions relativ frei agieren.
Seiten hinzufügen, Daten anzeigen, Bilder verarbeiten — das ist die Aufgabe von Extensions.

Allerdings ist außerhalb der geschützten Welt — der Systemkern (core), andere Extensions, alle Dateien Ihres PCs — physisch unerreichbar, nicht nur durch Regeln verboten.

---

## Berechtigungssystem

Extensions benötigen **Berechtigungen**, um etwas zu tun.

Berechtigungen sind wie Smartphone-App-Berechtigungen konzipiert.

- Eine Kamera-App benötigt Kamerazugriff — normal
- Eine Kamera-App, die Zugriff auf Kontakte anfordert — verdächtig

Extensions sind gleich. Wenn eine Extension zum Wasserzeichen-Einfügen Netzwerkzugriff anfordert, sollte man misstrauisch sein.

### Genehmigungsablauf

1. Extension installieren (oder von KI erstellen lassen)
2. YU AI Manager scannt automatisch den Code und prüft, was getan werden soll
3. Eine Liste der von der Extension angeforderten Berechtigungen wird angezeigt
4. **Bis Sie genehmigen, läuft die Extension nicht**

Lesen Sie die Informationen auf dem Genehmigungsbildschirm sorgfältig.
Besonders auf rot angezeigte Berechtigungen achten.

### Nach der Genehmigung

Die Extension arbeitet im Rahmen der genehmigten Berechtigungen.
Nicht genehmigte Berechtigungen sind unsichtbar — werden nicht verwendet, auch wenn die Extension es versucht.

---

## Drei unabhängige Überwachungen

Ihre Extension wird durch drei unabhängige Mechanismen überwacht.
Diese drei sind unabhängig — selbst wenn einer getäuscht wird, funktionieren die anderen zwei noch.

### 1. Code-Scan

Der Extension-Code wird automatisch analysiert und gefährliche Muster erkannt.
Externe Programmausführung, direkte Datenbankoperationen, dynamische Code-Ausführung — diese werden sofort erkannt.

### 2. Berechtigungskontrolle

Wenn eine Extension eine API aufruft, wird geprüft, ob ein gültiger "Berechtigungsnachweis" vorhanden ist.
Der Nachweis wird nur ausgestellt, wenn Sie die Berechtigung genehmigt haben.
Extensions können keine Nachweise fälschen.

### 3. Audit-Protokoll

Alle Operationen von Extensions werden aufgezeichnet.
Diese Aufzeichnungen werden an einem unabhängigen Ort gespeichert, den Extensions nicht selbst ändern können.

Bei Anomalieerkennung — z.B. wenn versucht wird, nicht deklariertes Verhalten auszuführen — wird eine automatische Benachrichtigung gesendet und bei Bedarf der Berechtigungsnachweis der Extension widerrufen.

---

## Extensions mit KI erstellen

Wenn Extensions aus Claude Desktop erstellt werden, werden sie automatisch auf der **restriktivsten Stufe** registriert.

Das ist wie ein neuer Mitarbeiter, dem nicht sofort der Safe-Schlüssel gegeben wird.
Zuerst mit eingeschränkten Berechtigungen betreiben und nach Problemlosigkeit bei Bedarf Berechtigungen hinzufügen.

### Was mit KI erstellte Extensions tun können

**Ohne Genehmigung:**
- Daten lesen und anzeigen
- Seiten zur UI hinzufügen
- Einstellungsbildschirme hinzufügen

**Mit Genehmigung:**
- Mit externen Diensten kommunizieren
- In Datenbank schreiben
- Dateien lesen

**Unabhängig von allem unmöglich:**
- Systemkern (core) lesen oder ändern
- Andere Extensions lesen oder ändern
- Externe Programme ausführen
- Berechtigungsnachweise fälschen

---

## Regelmäßige Prüfungen

Extensions müssen nach einmaliger Genehmigung nicht dauerhaft überwacht werden.

Wenn der Code geändert wird und die Änderungsmenge einen bestimmten Schwellenwert überschreitet, wird **erneute Genehmigung** angefordert.
Dies verhindert die Taktik, schrittweise Änderungen vorzunehmen bis etwas völlig anderes entsteht.

Außerdem wird der Code regelmäßig automatisch neu geprüft.
Auch wenn beim Genehmigungszeitpunkt keine Probleme vorlagen, können neue Prüfungsregeln Probleme finden.

---

## Was Sie tun sollten

1. **Den Genehmigungsbildschirm sorgfältig lesen** — Verstehen, was angefordert wird, bevor genehmigt wird
2. **Ungewöhnliche Berechtigungsanfragen ablehnen** — Netzwerk für Bildverarbeitung ist seltsam
3. **Benachrichtigungen nicht ignorieren** — Bei Anomalieerkennung überprüfen
4. **Keine Extensions aus unzuverlässigen Quellen installieren** — Selbstverständlich

Umgekehrt: Das Obige zu tun ist ausreichend für Sicherheit.
Den Rest erledigen die Mechanismen.
