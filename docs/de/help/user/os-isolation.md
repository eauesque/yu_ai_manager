# OS-Level-Isolation-Leitfaden

Funktion zur Einschränkung des Systemzugriffs von Extensions (Erweiterungen) durch OS-Sicherheitsmechanismen.

## 1. Was ist OS-Isolation?

Beim Installieren einer Smartphone-App erscheint "Diese App fordert Kamerazugriff an". OS-Isolation folgt demselben Konzept.

Basierend auf den von der Extension deklarierten Berechtigungen (Datei-Lesen/Schreiben, Netzwerkkommunikation, externe Befehlsausführung) **blockiert der OS-Kernel physisch nicht autorisierte Operationen**. Unabhängig davon, welche Techniken im Python-Code verwendet werden, können Kernel-Level-Einschränkungen nicht umgangen werden.

> **Hinweis**: Diese Funktion dient hauptsächlich zur sicheren Verwendung von Drittanbieter-Extensions. `builtin-*`-Extensions werden als vertrauenswürdig (L0) behandelt und ohne Einschränkungen betrieben.

---

## 2. Unterstützte Plattformen

| OS | Isolation-Methode | Reifegrad |
|----|---------|--------|
| **Linux** | AppArmor (Mandatory Access Control) | Empfohlen, produktionstauglich |
| **macOS** | sandbox-exec (Seatbelt) | Experimentell (von Apple nicht empfohlen) |
| **Windows** | Restricted Token + Job Object | Grundlegende Ressourceneinschränkung |

Linux AppArmor hat den höchsten Reifegrad und ist die empfohlene Umgebung.

---

## 3. Linux-Setup (AppArmor)

### 3.1 Was ist AppArmor?

AppArmor ist ein im Linux-Kernel integriertes Sicherheitsmodul. Mit Profilen pro Prozess definiert es, welche Dateien gelesen/geschrieben werden können und ob Netzwerkkommunikation erlaubt ist, und der Kernel erzwingt dies.

### 3.2 Automatisches Setup

Mit dem mitgelieferten Setup-Skript vollständig einrichten:

```bash
sudo bash scripts/setup-apparmor.sh
```

Dieses Skript macht folgendes:
1. **AppArmor-Pakete prüfen/installieren** — `apparmor`, `apparmor-utils` automatisch installieren
2. **Kernel-Parameter hinzufügen** — `lsm=apparmor` zu `/boot/firmware/cmdline.txt` (mit Backup)
3. **sudoers-Regel einrichten** — Nur `apparmor_parser`-Befehl ohne Passwort ausführbar
4. **AppArmor-Dienst aktivieren** — Autostart mit systemd

> **Für Nicht-Raspberry Pi OS**: In GRUB-Umgebungen manuell `lsm=apparmor` zu `GRUB_CMDLINE_LINUX` in `/etc/default/grub` hinzufügen und `sudo update-grub` ausführen.

### 3.3 Neustart

Bei hinzugefügten Kernel-Parametern Neustart erforderlich:

```bash
sudo reboot
```

### 3.4 Betriebsprüfung

```bash
# Kernel-Modul aktiviert prüfen
cat /sys/module/apparmor/parameters/enabled
# → "Y" = aktiviert

# Geladene Profile anzeigen
sudo aa-status
```

### 3.5 In config.json aktivieren

Nach Betriebsbestätigung folgendes zu `config.json` hinzufügen:

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

---

## 4. Konfigurations-Referenz

Gesteuert über `os_isolation`-Abschnitt in `config.json`:

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| Schlüssel | Typ | Standard | Beschreibung |
|------|------|-----------|------|
| `enabled` | bool | `false` | OS-Isolation-Funktion gesamt aktivieren/deaktivieren |
| `linux.apparmor` | bool | `true` | AppArmor-Profile verwenden |
| `macos.sandbox_exec` | bool | `false` | macOS sandbox-exec verwenden (experimentell) |
| `windows.restricted_token` | bool | `true` | Prozesse mit eingeschränktem Token starten |
| `windows.job_object` | bool | `true` | Ressourcenbegrenzung mit Job Object |
| `windows.job_limits.memory_mb` | int | `512` | Max. Speicher pro Extension (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | CPU-Auslastungsgrenze pro Extension (%) |
| `windows.job_limits.max_processes` | int | `10` | Max. Prozesse, die Extension erzeugen kann |

---

## 5. Zuordnung von Extension-Berechtigungen zu AppArmor-Regeln

Basierend auf in `extension.json` deklarierten Berechtigungen werden AppArmor-Profile automatisch generiert:

| Extension-Berechtigung | AppArmor-Kontrolle |
|---------------|-------------------|
| `db:read` | Nur Lesen von `data/`-Verzeichnis |
| `db:write` | Lesen/Schreiben von `data/`-Verzeichnis |
| `fs:read:scan_roots` | Lesen konfigurierter Scan-Roots |
| `fs:write:any` | Lesen/Schreiben aller Pfade |
| `network:local` | TCP/Unix-Socket (kein UDP) |
| `network:internet` | Alle TCP/UDP/Unix-Sockets |
| `subprocess` | Ausführung in `/usr/bin/`, `/bin/` usw. |
| Keine Netzwerkberechtigung | TCP/UDP explizit verweigert, nur IPC-Unix-Sockets |
| Keine subprocess-Berechtigung | Ausführung in `/usr/bin/`, `/bin/` usw. explizit verweigert |

Das eigene Verzeichnis der Extension (`extensions/<name>/`) ist immer lesen/schreibbar.

---

## 6. Statusprüfung per API

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Beispielantwort (Linux / AppArmor aktiviert):

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

Bei `available: false` enthält das `setup`-Feld Setup-Anweisungen.

---

## 7. Fehlerbehebung

### AppArmor wird nicht aktiviert

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" oder Datei existiert nicht
```

**Lösung**:
- Raspberry Pi OS: Prüfen ob `lsm=apparmor` in `/boot/firmware/cmdline.txt` vorhanden, Neustart
- GRUB: `GRUB_CMDLINE_LINUX="... lsm=apparmor"` prüfen, `sudo update-grub && sudo reboot`

### "sudoers not configured" bei Extension-Start

```bash
sudo bash scripts/setup-apparmor.sh
```

Skript richtet `/etc/sudoers.d/yu-ai-apparmor` ein.

### Extension funktioniert nicht wegen fehlender Berechtigungen

Erforderliche Berechtigungen in `permissions.required` der `extension.json` hinzufügen oder Berechtigungen manuell über Settings > Extensions zuweisen.

### Manuelles AppArmor-Profil prüfen

Generierte Profile werden in `/tmp/yu_ai_apparmor/` gespeichert:

```bash
# Profil-Inhalt prüfen
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# Aktuell geladene YU AI Manager-Profile
sudo aa-status | grep yu_ai_ext
```

---

## 8. Sicherheitshinweise

OS-Isolation ist Teil einer mehrschichtigen Verteidigung. YU AI Manager sichert durch folgende Schichten:

1. **Statische Analyse** (Phase 1) — Extension-Code bei Installation mit AST analysieren
2. **Berechtigungs-Gatekeeper** (Phase 2-3) — Proxy-gesteuerte Berechtigungsprüfung via ServiceRegistry
3. **OS-Isolation** (Phase 4) — Kernel-Level-Erzwingung für Dateien, Netzwerk, Prozesse

OS-Isolation allein beseitigt nicht alle Risiken, aber in Kombination mit anderen Verteidigungsschichten bietet es eine sichere Umgebung für Drittanbieter-Extensions.

Für Linux-Umgebung mit aktivierter OS-Isolation empfohlen, wenn nicht vertrauenswürdige Extensions installiert werden.
