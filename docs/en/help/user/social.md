# SNS & External Integrations

YU AI Manager can integrate with external services such as Bluesky and GitHub via MCP tools.

## Bluesky Integration

Post images to Bluesky directly from YU AI Manager.

### Setup

1. Go to Settings > SNS tab and enter your Bluesky handle and app password
2. Create an app password at https://bsky.app/settings/app-passwords

### Key MCP Tools

| Tool | Description |
|---|---|
| `bsky_post_image` | Post an image to Bluesky |
| `bsky_get_profile` | Get profile information |
| `bsky_get_timeline` | Get your timeline |
| `bsky_search_posts` | Search posts |
| `bsky_follow_user` | Follow a user |
| `bsky_get_followers` | Get follower list |

### Example (MCP)

```
bsky_post_image(image_path="/path/to/image.png", text="My AI art #AIArt")
```

## GitHub Integration

Interact with GitHub repositories, issues, and pull requests.

### Setup

Set your GitHub Personal Access Token in Settings > API Keys.

### Key MCP Tools

| Tool | Description |
|---|---|
| `github_list_repos` | List repositories |
| `github_get_file` | Get file contents |
| `github_create_issue` | Create an issue |
| `github_list_issues` | List issues |
| `github_create_pr` | Create a pull request |
| `github_get_commits` | Get commit history |

### Example (MCP)

```
github_list_issues(repo="owner/my-project", state="open")
```
