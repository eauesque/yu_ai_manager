# Paramètres

## Paramètres du Serveur

| Élément | Description |
|------|------|
| Host | Adresse de liaison (fixé à 127.0.0.1 quand LAN OFF) |
| Port | Numéro de port du serveur Web |
| LAN Access | Permet l'accès depuis d'autres appareils du LAN si ON |
| PIN Auth | Exige la saisie d'un PIN à l'accès |
| Boss Mode | Écran de connexion PIN style journal |

## Paramètres de Scan

Ajout/suppression/réorganisation/activation-désactivation des dossiers enregistrés.

## Paramètres du Parseur

| Élément | Description |
|------|------|
| Extract A1111 | Extrait les métadonnées au format Stable Diffusion WebUI |
| Extract ComfyUI | Extrait les métadonnées de workflow ComfyUI |
| Normalize tags | Unifie les tags en minuscules |
| Compute hash | Calcule le hash des fichiers (pour la détection de doublons) |
| FTS | Active l'index de recherche en texte intégral |

## Clés API

Gestion des clés API pour les outils externes (serveur MCP, scripts, agents). Utilisées en authentification Bearer.

## Apparence

Personnalisation du thème, couleur d'accent, image de fond, effets sonores, etc.

## Magasin de Secrets Chiffré

Les valeurs sensibles comme le PIN, le mot de passe Bluesky, les secrets Webhook, etc. sont protégées par un chiffrement Fernet du paquet `cryptography`.

- **Format de chiffrement** : chaîne avec préfixe `enc:`
- **Compatibilité** : les valeurs en clair existantes fonctionnent telles quelles (chiffrement uniquement lors d'un nouvel enregistrement)
- **Installation** : `uv pip install cryptography` (la fonction de chiffrement est désactivée si non installé)

### Backends de Clé

La clé de chiffrement est obtenue selon l'ordre de priorité suivant :

1. **Passphrase** — en définissant la variable d'environnement `YU_SECRET_PASSPHRASE`, la clé est dérivée via PBKDF2-HMAC-SHA256 (600 000 itérations). Le sel est enregistré automatiquement dans `data/secret.salt`
2. **Keychain OS** — si le paquet `keyring` est installé, la clé est stockée dans Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **Fichier** — `data/secret.key` (compatibilité héritée, générée automatiquement la première fois)

```bash
# Exemple de configuration de passphrase
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Utilisation du keychain
uv pip install keyring
```

### Export/Import de Clé

Pour migrer vers une autre machine ou faire une sauvegarde, vous pouvez exporter/importer la clé de chiffrement au format JSON protégé par mot de passe.

- `POST /api/settings/secrets/export` — exporter en protégeant avec un mot de passe (8 caractères minimum)
- `POST /api/settings/secrets/import` — restaurer la clé depuis les données exportées et le mot de passe
- `POST /api/settings/secrets/migrate-keychain` — migrer du fichier vers le keychain
- `GET /api/settings/secrets/status` — vérifier l'état du backend

### Migration vers Keychain

Pour migrer la clé enregistrée en fichier vers le keychain, appelez `/api/settings/secrets/migrate-keychain`. Après migration, `data/secret.key` est supprimé automatiquement.

## Intégration 1Password CLI

Dans un environnement où le CLI `op` est installé, vous pouvez récupérer dynamiquement des secrets depuis le Vault 1Password.

### Configuration

1. Installer [1Password CLI](https://developer.1password.com/docs/cli/)
2. Se connecter avec `op signin`
3. Ajouter la mapping `op_secrets` dans `config.json` :

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Configurer en spécifiant `op_uri` via l'API Settings ou l'outil MCP :

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### Fonctionnement

- Si une clé est enregistrée dans `op_secrets`, le secret est récupéré via `op read`
- La valeur récupérée est mise en cache mémoire pendant 5 minutes
- Dans un environnement sans le CLI `op`, repli sur le magasin chiffré local
- Vérifier l'état d'authentification 1Password avec `GET /api/settings/op-status`

## Outils MCP Settings

Vous pouvez gérer les paramètres depuis un client MCP (Claude Desktop, etc.).

| Outil | Description |
|--------|------|
| `settings_get_schema` | Obtenir le schéma de tous les paramètres (type, description, catégorie) |
| `settings_get_all` | Obtenir toutes les valeurs des paramètres (secrets masqués) |
| `settings_get` | Obtenir une valeur de paramètre unique |
| `settings_set` | Mettre à jour une valeur (secrets automatiquement chiffrés) |
| `secrets_status` | Obtenir l'état du backend de clé de chiffrement |
| `secrets_export` | Exporter la clé en JSON protégé par mot de passe |
| `secrets_import` | Importer la clé depuis des données exportées |
