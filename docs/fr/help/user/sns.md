# SNS Share & Bluesky Monitor

## Vue d'ensemble

SNS Share est une extension permettant de partager directement les images générées par IA depuis YU AI Manager vers Bluesky ou X (Twitter). Le texte de publication est généré automatiquement à partir de modèles personnalisables, et les variables de métadonnées d'image sont développées automatiquement. Bluesky Monitor ajoute une fonction de surveillance des notifications, avec triage par IA et réponses automatiques possibles.

## Configuration

### Obtenir un App Password Bluesky

1. Connectez-vous à [bsky.app] et ouvrez **Paramètres > App Passwords**
2. Cliquez sur **Ajouter un App Password**
3. Saisissez un nom (ex : « YU AI Manager ») et cliquez sur **Créer un App Password**
4. Copiez le mot de passe affiché

> **Attention** : le App Password ne s'affiche que sur cet écran. Copiez-le impérativement avant de fermer la boîte de dialogue. N'utilisez jamais le mot de passe principal Bluesky.

### Configuration dans YU AI Manager

1. Ouvrez **Settings** depuis le menu de navigation
2. Basculez sur l'onglet **SNS**
3. Saisissez les informations suivantes :
   - **Handle Bluesky** : nom de handle (ex : `yourname.bsky.social`)
   - **App Password** : le App Password obtenu ci-dessus
   - **Modèle de publication** : modèle de texte de publication (voir [Variables de modèle](#variables-de-modèle))
4. Cliquez sur **Enregistrer**

### Test de Connexion

Après avoir enregistré les informations d'authentification, cliquez sur **Test de connexion** pour vérifier l'authentification avec Bluesky. En cas de succès, le handle et le nom d'affichage s'affichent.

## Fonctionnalités

### Partage sur Bluesky

Vous pouvez partager directement des images sur Bluesky depuis la vue détaillée d'image.

1. Ouvrez la modale de détail de l'image
2. Cliquez sur le bouton **SNS**
3. Vérifiez/éditez le texte de publication généré
4. Cliquez sur **Publier sur Bluesky**

- Le texte de publication est généré à partir du modèle configuré, en développant les variables de métadonnées
- Les images sont automatiquement compressées et redimensionnées selon la limite d'upload de 1 Mo de Bluesky
- La publication est limitée à **300 graphèmes** (le surplus est tronqué automatiquement)
- Vous pouvez choisir d'attacher ou non une image

### Partage sur X (Twitter)

Utilisation de Web Intent (ouverture de l'écran de publication X dans le navigateur) pour partager les informations d'image sur X.

1. Ouvrez la modale de détail de l'image
2. Cliquez sur le bouton **SNS**
3. Cliquez sur **Partager sur X**

Un nouvel onglet du navigateur ouvre l'écran de publication X, et le texte généré à partir du modèle est pré-rempli automatiquement. Vous pouvez éditer le texte avant publication. Sur X, les images ne sont pas attachées automatiquement, il faut attacher l'image manuellement.

### Bluesky Monitor

Bluesky Monitor interroge les notifications Bluesky, les met en file locale pour triage et réponse.

#### Types de Notifications

- **Mention** : vous avez été mentionné dans une publication
- **Réponse** : il y a eu une réponse à votre publication
- **Citation** : votre publication a été citée
- **Follow** : quelqu'un vous suit
- **Like** : votre publication a reçu un like
- **Repost** : votre publication a été republiée

#### Polling

Les notifications sont récupérées automatiquement à intervalle configurable (défaut : 30 min, minimum : 5 min). Vous pouvez aussi déclencher un polling immédiat depuis Settings ou via l'outil MCP.

#### Système de File

Chaque notification entre dans la file avec le statut **pending** (non traitée). Elle peut ensuite passer aux statuts suivants :

- **notified** -- déjà notifié au client MCP (Claude Desktop)
- **dismissed** -- rejeté comme ne nécessitant pas d'action

#### Triage

Le classement par IA détermine si chaque notification nécessite une action :

- **valid** -- action requise (question, rapport de bug, demande de collaboration, etc.)
- **invalid** -- ignorable (éloges génériques, spam, contenu bot, etc.)

Des prompts de triage personnalisables existent pour chaque type de notification (mention, réponse, citation). Des prompts par défaut sont fournis, restaurables à tout moment.

#### Réponse Automatique

Pour les mentions/réponses/citations jugées valid, vous pouvez envoyer des réponses automatiques basées sur des modèles :

- Activer la réponse automatique dans les paramètres Monitor
- Personnaliser le modèle de réponse pour chaque type de notification
- Les réponses sont limitées à 300 graphèmes

#### Rejet Automatique

Les follows, likes et reposts peuvent être rejetés automatiquement pour réduire le bruit dans la file. Chaque type est activable individuellement dans Settings.

#### Notification Lors de la Connexion MCP

Lorsqu'un client MCP (Claude Desktop) se connecte, les notifications non traitées sont rapportées en groupe, permettant vérification pendant la session de développement.

### Paramètres

Les paramètres SNS se font dans l'onglet **SNS** de la page Settings :

- **Informations d'authentification Bluesky** : handle et App Password (mot de passe chiffré, affichage masqué)
- **Modèle de publication** : texte de modèle avec placeholders de variables
- **Paramètres Monitor** :
  - Intervalle de polling (minutes)
  - Rejet automatique des follows/likes/reposts
  - Activation/désactivation des réponses automatiques
  - Prompts de triage pour mention/réponse/citation
  - Modèles de réponse automatique pour mention/réponse/citation

## Intégration MCP

SNS Share & Bluesky Monitor dispose de 15 outils MCP :

**Partage (6 outils)** :
- `share_to_bluesky` -- publier une image sur Bluesky
- `get_x_share_url` -- obtenir l'URL Web Intent X
- `get_sns_preview` -- prévisualisation du développement du modèle
- `test_bluesky_connection` -- test de connexion API
- `get_sns_config` / `save_sns_config` -- obtention/enregistrement de la configuration SNS

**File de notifications (5 outils)** :
- `bsky_get_pending_notifications` -- obtenir les notifications non traitées
- `bsky_get_notification_queue` -- obtenir les éléments de file avec filtre
- `bsky_triage_notification` -- définir le résultat du triage (valid/invalid)
- `bsky_send_auto_response` -- envoyer une réponse à une notification
- `bsky_poll_notifications` -- déclencher immédiatement le polling

**Paramètres Monitor (4 outils)** :
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- obtention/enregistrement des paramètres Monitor
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- obtention/enregistrement des prompts de triage et modèles de réponse

## Variables de Modèle

Variables utilisables dans le modèle de publication :

| Variable | Description |
|---|---|
| `{positive_short}` | Prompt positif (100 premiers caractères) |
| `{positive}` | Prompt positif complet |
| `{negative_short}` | Prompt négatif (50 premiers caractères) |
| `{model}` | Nom du modèle |
| `{seed}` | Valeur de seed |
| `{steps}` | Nombre d'étapes d'échantillonnage |
| `{cfg}` | Échelle CFG |
| `{sampler}` | Nom du sampler |
| `{size}` | Taille de l'image |
| `{tags}` | Top 5 tags |
| `{filename}` | Nom du fichier |

Modèle par défaut : `{positive_short}`

## Conseils

- **Sécurité App Password** : utilisez toujours un App Password, pas le mot de passe principal Bluesky. Le App Password peut être révoqué à tout moment depuis les paramètres bsky.app
- **Limite de taux** : l'API Bluesky a des limites de taux. Évitez les publications consécutives. Les uploads d'images comptent aussi dans la limite de taux
- **Comptage de graphèmes** : Bluesky utilise des grappes de graphèmes, pas un comptage de caractères, pour la limite de 300. Les caractères CJK comptent comme 1 graphème
- **Compression d'images** : les images de plus de 1 Mo sont redimensionnées automatiquement. En cas d'échec de préparation d'image, la publication se fait en texte seul
- **Intervalle de polling du Monitor** : configurez l'intervalle selon le volume de notifications. Les comptes avec beaucoup de notifications bénéficient d'un intervalle court
- **Rejet automatique** : en activant le rejet automatique des follows/likes/reposts, vous pouvez vous concentrer sur les notifications nécessitant une action
- **Prompts de triage** : personnalisez les prompts de triage selon votre style de communication et les types d'interactions que vous recevez
