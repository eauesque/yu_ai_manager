# Guida all'Isolamento a Livello OS

Funzionalità per limitare l'impatto delle Extension (estensioni) sul sistema tramite i meccanismi di sicurezza del sistema operativo.

## 1. Cos'è l'Isolamento OS

Quando si installa un'app sullo smartphone, appare un messaggio "Questa app richiede l'accesso alla fotocamera". L'isolamento OS si basa sullo stesso concetto.

In base ai permessi dichiarati dall'Extension (lettura/scrittura file, comunicazione di rete, esecuzione comandi esterni ecc.), **il kernel OS blocca fisicamente le operazioni non autorizzate**. Qualsiasi tecnica venga usata nel codice Python, i limiti a livello kernel non possono essere aggirati.

> **Nota**: Questa funzionalità serve principalmente per utilizzare in modo sicuro le Extension di terze parti. Le Extension `builtin-*` sono trattate come trusted (L0) e funzionano senza restrizioni.

---

## 2. Piattaforme Supportate

| OS | Metodo di Isolamento | Maturità |
|----|---------------------|---------|
| **Linux** | AppArmor (Mandatory Access Control) | Consigliato, pronto per produzione |
| **macOS** | sandbox-exec (Seatbelt) | Sperimentale (deprecato da Apple) |
| **Windows** | Restricted Token + Job Object | Limitazione risorse base |

AppArmor su Linux ha il più alto livello di completezza ed è l'ambiente consigliato.

---

## 3. Setup Linux (AppArmor)

### 3.1 Cos'è AppArmor

AppArmor è un modulo di sicurezza integrato nel kernel Linux. Definisce in un profilo "quali file può leggere/scrivere" e "se consentire la comunicazione di rete" per ogni processo, e il kernel lo fa rispettare.

Su Ubuntu/Debian è spesso abilitato di default, ma su alcune distribuzioni come Raspberry Pi OS è necessaria l'abilitazione manuale.

### 3.2 Setup Automatico

È possibile configurare tutto in una volta con lo script di setup allegato.

```bash
sudo bash scripts/setup-apparmor.sh
```

Questo script esegue le seguenti operazioni:

1. **Verifica/installazione pacchetti AppArmor** — Installazione automatica di `apparmor`, `apparmor-utils` se assenti
2. **Aggiunta parametri kernel** — Aggiunta di `lsm=apparmor` a `/boot/firmware/cmdline.txt` (con backup)
3. **Installazione regole sudoers** — Configurazione per eseguire solo il comando `apparmor_parser` senza password (minimo privilegio)
4. **Abilitazione servizio AppArmor** — Configurazione avvio automatico con systemd

### 3.3 Riavvio

Se sono stati aggiunti parametri kernel, è necessario un riavvio.

```bash
sudo reboot
```

### 3.4 Verifica Funzionamento

Dopo il riavvio, verificare che AppArmor sia attivo.

```bash
# Verifica attivazione modulo kernel
cat /sys/module/apparmor/parameters/enabled
# → "Y" se attivo

# Lista profili caricati
sudo aa-status
```

### 3.5 Abilitazione in config.json

Dopo aver confermato che AppArmor funziona, aggiungere quanto segue a `config.json`.

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

Con questo, al momento del lancio delle Extension di terze parti il profilo AppArmor viene generato e caricato automaticamente.

---

## 4. Riferimento Impostazioni

Controllato dalla sezione `os_isolation` di `config.json`.

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

| Chiave | Tipo | Default | Descrizione |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Abilitazione/disabilitazione funzionalità isolamento OS |
| `linux.apparmor` | bool | `true` | Usa profilo AppArmor |
| `macos.sandbox_exec` | bool | `false` | Usa macOS sandbox-exec (sperimentale) |
| `windows.restricted_token` | bool | `true` | Avvia processo con token limitato |
| `windows.job_object` | bool | `true` | Limitazione risorse con Job Object |
| `windows.job_limits.memory_mb` | int | `512` | Memoria massima per Extension (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Limite utilizzo CPU per Extension (%) |
| `windows.job_limits.max_processes` | int | `10` | Numero massimo processi generabili dall'Extension |

---

## 5. Corrispondenza tra Permessi Extension e Regole AppArmor

Le regole AppArmor vengono generate automaticamente in base ai permessi dichiarati nell'Extension in `extension.json`.

| Permesso Extension | Controllo AppArmor |
|-------------------|-------------------|
| `db:read` | Solo lettura della directory `data/` |
| `db:write` | Lettura/scrittura della directory `data/` |
| `fs:read:scan_roots` | Lettura delle radici di scansione configurate |
| `fs:write:any` | Lettura/scrittura di tutti i percorsi |
| `network:local` | TCP/Unix socket permessi (UDP negato) |
| `network:internet` | TCP/UDP/Unix socket tutti permessi |
| `subprocess` | Esecuzione di `/usr/bin/`, `/bin/` ecc. |
| Nessun permesso rete | TCP/UDP esplicitamente negati, solo Unix socket per IPC |
| Nessun permesso subprocess | Esecuzione di `/usr/bin/`, `/bin/` ecc. esplicitamente negata |

La directory dell'Extension stessa (`extensions/<name>/`) è sempre leggibile e scrivibile.

---

## 6. Verifica tramite API

Lo stato dell'isolamento OS è verificabile tramite API.

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Esempio risposta (Linux / AppArmor abilitato):

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

Se `available` è `false`, il campo `setup` contiene le istruzioni di setup.

---

## 7. Risoluzione dei Problemi

### AppArmor Non Si Attiva

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" o file non esistente
```

**Causa**: Il parametro kernel non è stato applicato.

**Soluzione**:
- Raspberry Pi OS: Verificare presenza di `lsm=apparmor` in `/boot/firmware/cmdline.txt` e riavviare
- Ambiente GRUB: Verificare `GRUB_CMDLINE_LINUX="... lsm=apparmor"` in `/etc/default/grub` e eseguire `sudo update-grub && sudo reboot`

### "sudoers not configured" all'Avvio Extension

**Causa**: La regola sudoers NOPASSWD per `apparmor_parser` non è configurata.

**Soluzione**:
```bash
sudo bash scripts/setup-apparmor.sh
```

Lo script installa la regola necessaria in `/etc/sudoers.d/yu-ai-apparmor`.

### Extension Non Funziona per Permessi Insufficienti

**Causa**: Il permesso necessario non è dichiarato nell'`extension.json` dell'Extension.

**Soluzione**: Aggiungere il permesso necessario a `permissions.required` nell'`extension.json` dell'Extension, o assegnare manualmente il permesso da Settings > Extensions.

---

## 8. Note sulla Sicurezza

L'isolamento OS è parte di una difesa a più livelli. YU AI Manager garantisce la sicurezza con i seguenti livelli:

1. **Analisi statica** (Fase 1) — Analisi AST del codice Extension all'installazione, rilevamento import pericolosi
2. **Permission gatekeeper** (Fase 2-3) — Controllo permessi tramite Proxy con accessi via ServiceRegistry
3. **Isolamento OS** (Fase 4) — Forzatura a livello kernel di file, rete e esecuzione processi

L'isolamento OS da solo non elimina tutti i rischi, ma combinato con gli altri livelli di difesa fornisce un ambiente per utilizzare in modo sicuro le Extension di terze parti.

Per l'installazione di Extension non fidate, si raccomanda l'utilizzo in ambiente Linux con isolamento OS abilitato.

## Containers

Usa Docker/Podman per isolamento processo:
- Rete segregata
- Filesystem sandbox
- Resource limits (CPU, RAM)

## Virtual Machines

VM per isolamento completo:
- Isolamento hardware
- Independent kernel
- No shared resources

## systemd ProtectSystem

Linux systemd restrizioni:
```ini
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
PrivateTmp=yes
```

## AppArmor / SELinux

Profile restrittivo:
```bash
sudo aa-enforce /etc/apparmor.d/yu-ai-manager
```

## File permissions

Principio least privilege:
```bash
chmod 0700 data/
chmod 0600 data/tags.db
chown app:app data/
```

## Network isolation

- Firewall restrict traffic
- Only expose port necessario
- VPN per remote access
