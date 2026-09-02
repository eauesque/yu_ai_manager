# SNS & Externe Integration

YU AI Manager kann mit externen Diensten wie Bluesky und GitHub integriert werden. Operationen erfolgen über MCP-Tools.

## Bluesky Integration

Verbinden Sie mit Bluesky-Konto um Bilder zu posten.

### Einrichtung

1. Settings > SNS Tab Bluesky Handle und App-Passwort eingeben
2. App-Passwort unter https://bsky.app/settings/app-passwords erstellen

### Wichtigste MCP-Tools

| Tool Name | Beschreibung |
|---|---|
| `bsky_post_image` | Bild zu Bluesky posten |
| `bsky_get_profile` | Profil-Informationen abrufen |
| `bsky_get_timeline` | Zeitleiste abrufen |
| `bsky_search_posts` | Beiträge suchen |
| `bsky_follow_user` | Benutzer folgen |
| `bsky_get_followers` | Follower-Liste abrufen |

### Verwendungsbeispiel (MCP)

```
bsky_post_image(image_path="/path/to/image.png", text="Heute's Generierung #AIArt")
```

## GitHub Integration

Arbeiten Sie mit GitHub-Repositorys um Dateien und Issues zu manipulieren.

### Einrichtung

Settings > API Keys Tab: GitHub Personal Access Token eingeben.

### Wichtigste MCP-Tools

| Tool Name | Beschreibung |
|---|---|
| `github_list_repos` | Repositories auflisten |
| `github_get_file` | Datei-Inhalt abrufen |
| `github_create_issue` | Issue erstellen |
| `github_list_issues` | Issues auflisten |
| `github_create_pr` | Pull Request erstellen |
| `github_get_commits` | Commit-Historie abrufen |

### Verwendungsbeispiel (MCP)

```
github_list_issues(repo="owner/my-project", state="open")
```

