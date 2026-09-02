# SNS e integración externa

YU AI Manager puede integrarse con servicios externos como Bluesky y GitHub. Se opera mediante herramientas MCP.

## Integración con Bluesky

Puede publicar imágenes integrándose con su cuenta de Bluesky.

### Configuración

1. Configure el handle de Bluesky y el App Password en Settings > pestaña SNS
2. El App Password se emite en https://bsky.app/settings/app-passwords

### Principales herramientas MCP

| Nombre de la herramienta | Descripción |
|---|---|
| `bsky_post_image` | Publica una imagen en Bluesky |
| `bsky_get_profile` | Obtiene información de perfil |
| `bsky_get_timeline` | Obtiene la línea de tiempo |
| `bsky_search_posts` | Busca publicaciones |
| `bsky_follow_user` | Sigue a un usuario |
| `bsky_get_followers` | Obtiene la lista de seguidores |

### Ejemplo de uso (MCP)

```
bsky_post_image(image_path="/path/to/image.png", text="Obra generada hoy #AIArt")
```

## Integración con GitHub

Puede integrarse con repositorios de GitHub para operar con archivos e Issues.

### Configuración

Configure un GitHub Personal Access Token en Settings > pestaña API Keys.

### Principales herramientas MCP

| Nombre de la herramienta | Descripción |
|---|---|
| `github_list_repos` | Obtiene la lista de repositorios |
| `github_get_file` | Obtiene el contenido de un archivo |
| `github_create_issue` | Crea un Issue |
| `github_list_issues` | Obtiene la lista de Issues |
| `github_create_pr` | Crea un pull request |
| `github_get_commits` | Obtiene el historial de commits |

### Ejemplo de uso (MCP)

```
github_list_issues(repo="owner/my-project", state="open")
```
