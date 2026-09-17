# SNS et Intégrations Externes

YU AI Manager peut s'intégrer à des services externes comme Bluesky et GitHub. Les opérations se font via les outils MCP.

## Intégration Bluesky

Vous pouvez intégrer un compte Bluesky pour publier des images.

### Configuration

1. Définissez le handle Bluesky et le mot de passe d'application dans l'onglet Settings > SNS
2. Le mot de passe d'application se crée sur https://bsky.app/settings/app-passwords

### Principaux Outils MCP

| Nom de l'outil | Description |
|---|---|
| `bsky_post_image` | Publier une image sur Bluesky |
| `bsky_get_profile` | Obtenir les informations de profil |
| `bsky_get_timeline` | Obtenir la timeline |
| `bsky_search_posts` | Rechercher des publications |
| `bsky_follow_user` | Suivre un utilisateur |
| `bsky_get_followers` | Obtenir la liste des followers |

### Exemple d'utilisation (MCP)

```
bsky_post_image(image_path="/path/to/image.png", text="今日の生成作品 #AIArt")
```

## Intégration GitHub

Vous pouvez intégrer un dépôt GitHub pour gérer fichiers et Issues.

### Configuration

Définissez le GitHub Personal Access Token dans l'onglet Settings > API Keys.

### Principaux Outils MCP

| Nom de l'outil | Description |
|---|---|
| `github_list_repos` | Obtenir la liste des dépôts |
| `github_get_file` | Obtenir le contenu d'un fichier |
| `github_create_issue` | Créer un Issue |
| `github_list_issues` | Obtenir la liste des Issues |
| `github_create_pr` | Créer une pull request |
| `github_get_commits` | Obtenir l'historique des commits |

### Exemple d'utilisation (MCP)

```
github_list_issues(repo="owner/my-project", state="open")
```
