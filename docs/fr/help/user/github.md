# GitHub Integration

## Vue d'ensemble

GitHub Integration est une extension permettant de gérer centralement les dépôts, Issues, Pull Requests, Discussions et Releases GitHub depuis YU AI Manager. Supporte plusieurs comptes GitHub et stocke les tokens de façon sécurisée avec chiffrement. Permet d'obtenir rapidement les notifications et statistiques de dépôts dans le tableau de bord, et dispose également d'une fonctionnalité de triage d'Issues par IA.

## Configuration

### Obtention d'un Personal Access Token (PAT) GitHub

1. Se connecter à GitHub et ouvrir **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Cliquer sur **Generate new token (classic)**
3. Saisir un nom de token et définir la date d'expiration
4. Cocher **`repo`** dans les portées (nécessaire pour l'accès complet aux dépôts)
5. Cliquer sur **Generate token** et copier le token affiché

> **Note** : Le token ne s'affiche qu'une fois sur cet écran. Copier impérativement avant de fermer la fenêtre.

### Ajout d'un compte

1. Cliquer sur la carte **GitHub** depuis le launcher Extensions, ou accéder directement à `/ext/github`
2. Ouvrir l'onglet **Settings**
3. Cliquer sur **Ajouter un compte**
4. Saisir les informations suivantes :
   - **Étiquette** : Nom d'affichage du compte (ex : « Personnel », « Travail »)
   - **Token** : PAT obtenu ci-dessus
   - **Dépôts** : Dépôts à surveiller au format `owner/repo` (plusieurs possibles)
5. Après sauvegarde, sélectionner le compte dans la liste déroulante

## Fonctionnalités

### Tableau de bord

Après la sélection d'un compte, le tableau de bord se charge automatiquement.

- **Notifications** : Liste des notifications GitHub non lues
- **Statistiques des dépôts** : Nombre d'étoiles, forks, Issues ouvertes en format carte
- **Cartes récapitulatives** : Vue d'ensemble des dépôts surveillés

### Issues

- Filtrage par dépôt et état (open/closed)
- Affichage détaillé des Issues (contenu, commentaires, labels)
- Création de nouvelles Issues
- **Fonctionnalité de triage** : Classement automatique des Issues par IA
  - `valid_bug` — Rapport de bug valide
  - `needs_info` — Informations supplémentaires nécessaires
  - `skip` — Aucune action nécessaire
- **File d'attente d'Issues** : Polling automatique des nouvelles Issues GitHub et mise en file locale. Notification groupée des non-lus lors de la connexion du client MCP (Claude Desktop).

### Pull Requests

- Liste et filtrage des PR
- Affichage des statistiques de diff (lignes ajoutées/supprimées/fichiers modifiés)
- Vérification du contenu des modifications par fichier en vue détaillée

### Discussions

- Récupération de la liste des discussions via l'API GraphQL
- Affichage des badges de catégorie et de réponse

### Releases

- Liste des dernières releases des dépôts surveillés
- Consultation des notes de release

### Settings

- Ajout, modification, suppression et basculement activation/désactivation des comptes
- Affichage du quota restant de l'API GitHub
- Configuration des filtres de langue et de l'intervalle de planification
- Configuration de l'intervalle de polling de la file d'Issues, fermeture automatique des Issues invalides, notifications de connexion MCP
- Modification des prompts de triage pour Issues, PR, Discussions (voir [exemples](/help/github-triage-examples))

### File d'attente d'Issues

La file d'attente d'Issues effectue un polling périodique de GitHub et sauvegarde les nouvelles Issues localement.

- **Polling** : Exécution automatique par le planificateur (intervalle configurable, défaut 60 minutes)
- **Notifications** : Lors de la connexion MCP, notification groupée des Issues non traitées à Claude Desktop
- **Triage** : Classification de chaque Issue entrante en valide/invalide
- **Fermeture automatique** : Fermeture automatique sur GitHub des Issues jugées invalides avec commentaire de template
- **Polling manuel** : Cliquer sur « Poll Now » dans Settings pour une récupération immédiate

### Prompts de triage

Les instructions IA pour le triage des Issues, PR et Discussions peuvent être personnalisées.

- Prompts éditables individuellement pour chaque type (Issue, PR, Discussion)
- Prompts par défaut fournis, restaurables à tout moment
- Voir les [exemples de prompts de triage](/help/github-triage-examples) pour les templates multilingues et multi-styles

## Intégration MCP

12 outils MCP sont disponibles dans GitHub Integration, permettant une opération directe depuis Claude Code.

- Récupération et affichage détaillé des Issues
- Récupération et affichage détaillé des PR
- Récupération des notifications
- Récupération et mise à jour des prompts de triage
- Gestion de la file d'Issues (liste non traitée, triage, rejet, polling)

Les outils MCP permettent de consulter les informations GitHub sans quitter l'IDE lors de l'édition de code.

## Conseils

- **Comptes multiples** : Séparer les comptes par usage (personnel/travail, etc.) facilite la gestion
- **Permissions du token** : La portée `repo` couvre toutes les fonctionnalités de base. Pour accéder aux dépôts privés d'une organisation, une autorisation SSO d'organisation séparée est nécessaire
- **Utilisation du triage** : Pour les dépôts avec de nombreuses Issues, le triage automatique par la fonctionnalité de triage est efficace
- **Limite de débit** : L'API GitHub a une limite de requêtes par heure. Vérifier le quota restant dans l'onglet Settings
- **Sécurité des tokens** : Les tokens sont stockés chiffrés côté serveur. Ils ne sont jamais stockés en clair
- **Mise à jour du tableau de bord** : Basculer entre les comptes recharge automatiquement les données
