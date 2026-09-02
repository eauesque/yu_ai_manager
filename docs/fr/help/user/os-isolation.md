# Guide d'isolation au niveau OS

Fonctionnalité limitant l'impact des Extensions (plug-ins) sur le système via les mécanismes de sécurité de l'OS.

## 1. Qu'est-ce que l'isolation OS

Quand vous installez une application sur smartphone, il s'affiche « Cette application demande l'accès à la caméra ». L'isolation OS repose sur la même idée.

Basé sur les permissions déclarées par l'Extension (lecture/écriture de fichiers, communication réseau, exécution de commandes externes, etc.), **le noyau OS bloque physiquement les opérations non autorisées**.
Aucune technique dans le code Python ne peut contourner les restrictions au niveau noyau.

> **Note** : Cette fonctionnalité est principalement destinée à utiliser en toute sécurité des Extensions tierces. Les Extensions `builtin-*` sont traitées comme fiables (L0) et fonctionnent sans restriction.

---

## 2. Plateformes supportées

| OS | Méthode d'isolation | Maturité |
|----|---------|--------|
| **Linux** | AppArmor (Mandatory Access Control) | Recommandé, prêt pour la production |
| **macOS** | sandbox-exec (Seatbelt) | Expérimental (déprécié par Apple) |
| **Windows** | Restricted Token + Job Object | Restrictions de ressources de base |

AppArmor sur Linux offre le niveau d'achèvement le plus élevé et constitue l'environnement recommandé.

---

## 3. Configuration Linux (AppArmor)

### 3.1 Qu'est-ce qu'AppArmor

AppArmor est un module de sécurité intégré au noyau Linux. Il définit dans des profils « quels fichiers peuvent être lus/écrits », « si la communication réseau est autorisée » pour chaque processus, et le noyau l'applique.

Il est souvent activé par défaut sur Ubuntu / Debian, mais une activation manuelle peut être nécessaire sur certaines distributions comme Raspberry Pi OS.

### 3.2 Configuration automatique

```bash
sudo bash scripts/setup-apparmor.sh
```

Ce script effectue les opérations suivantes :

1. **Vérification/installation des paquets AppArmor** — Installation automatique de `apparmor`, `apparmor-utils` si absents
2. **Ajout des paramètres noyau** — Ajout de `lsm=apparmor` dans `/boot/firmware/cmdline.txt` (avec backup)
3. **Installation des règles sudoers** — Configuration pour exécuter uniquement la commande `apparmor_parser` sans mot de passe (privilège minimal)
4. **Activation du service AppArmor** — Configuration du démarrage automatique avec systemd

> **Pour les environnements non Raspberry Pi OS** : Dans les environnements utilisant GRUB, ajouter manuellement `lsm=apparmor` dans `GRUB_CMDLINE_LINUX` de `/etc/default/grub` et exécuter `sudo update-grub`.

### 3.3 Redémarrage

```bash
sudo reboot
```

### 3.4 Vérification du fonctionnement

```bash
# Le module noyau est-il activé ?
cat /sys/module/apparmor/parameters/enabled
# → "Y" signifie activé

# Liste des profils chargés
sudo aa-status
```

### 3.5 Activation dans config.json

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

## 4. Référence des paramètres de configuration

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

| Clé | Type | Défaut | Description |
|------|------|-----------|------|
| `enabled` | bool | `false` | Activer/désactiver l'isolation OS globalement |
| `linux.apparmor` | bool | `true` | Utiliser les profils AppArmor |
| `macos.sandbox_exec` | bool | `false` | Utiliser macOS sandbox-exec (expérimental) |
| `windows.restricted_token` | bool | `true` | Démarrer les processus avec token restreint |
| `windows.job_object` | bool | `true` | Limiter les ressources avec Job Object |
| `windows.job_limits.memory_mb` | int | `512` | Mémoire maximum par Extension (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Limite d'utilisation CPU par Extension (%) |
| `windows.job_limits.max_processes` | int | `10` | Nombre maximum de processus que l'Extension peut créer |

---

## 5. Correspondance permissions Extension et règles AppArmor

Les profils AppArmor sont automatiquement générés en fonction des permissions déclarées dans `extension.json`.

| Permission Extension | Contrôle AppArmor |
|---------------|-------------------|
| `db:read` | Lecture uniquement du répertoire `data/` |
| `db:write` | Lecture/écriture du répertoire `data/` |
| `fs:read:scan_roots` | Lecture des scan roots configurés |
| `fs:write:any` | Lecture/écriture de tous les chemins |
| `network:local` | TCP/Unix sockets (UDP refusé) |
| `network:internet` | TCP/UDP/Unix sockets tous autorisés |
| `subprocess` | Exécution de `/usr/bin/`, `/bin/`, etc. |
| Pas de permission réseau | TCP/UDP explicitement refusés, seuls les Unix sockets IPC autorisés |
| Pas de permission subprocess | Exécution de `/usr/bin/`, `/bin/`, etc. explicitement refusée |

Le répertoire de l'Extension elle-même (`extensions/<name>/`) est toujours accessible en lecture/écriture.

---

## 6. Vérification via API

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Exemple de réponse (Linux / AppArmor activé) :

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

Si `available` est `false`, le champ `setup` contient les instructions de configuration.

---

## 7. Dépannage

### AppArmor ne s'active pas

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" ou fichier inexistant
```

**Solution** :
- Raspberry Pi OS : Vérifier que `lsm=apparmor` est dans `/boot/firmware/cmdline.txt` et redémarrer
- Environnement GRUB : Vérifier `GRUB_CMDLINE_LINUX="... lsm=apparmor"` dans `/etc/default/grub`, puis `sudo update-grub && sudo reboot`

### « sudoers not configured » affiché au démarrage de l'Extension

```bash
sudo bash scripts/setup-apparmor.sh
```

### L'Extension ne fonctionne pas par manque de permissions

Ajouter les permissions nécessaires dans `permissions.required` de `extension.json`, ou les attribuer manuellement depuis Settings > Extensions.

### Vérification manuelle du profil AppArmor

```bash
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>
sudo aa-status | grep yu_ai_ext
```

---

## 8. Notes sur la sécurité

L'isolation OS fait partie d'une défense en profondeur. YU AI Manager assure la sécurité sur plusieurs niveaux :

1. **Analyse statique** (Phase 1) — Analyse AST du code de l'Extension à l'installation
2. **Gardien des permissions** (Phase 2-3) — Contrôle des accès via ServiceRegistry avec proxy de vérification des permissions
3. **Isolation OS** (Phase 4) — Restriction forcée des fichiers, réseau et exécution de processus au niveau noyau

L'isolation OS seule n'élimine pas tous les risques, mais combinée aux autres couches de défense, elle fournit un environnement pour utiliser les Extensions tierces en toute sécurité.

Pour les Extensions de sources non fiables, l'utilisation dans un environnement Linux avec isolation OS activée est recommandée.
