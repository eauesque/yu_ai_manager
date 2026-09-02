# SNS・外部連携

YU AI Manager は Bluesky や GitHub などの外部サービスと連携できます。MCP ツールを通じて操作します。

## Bluesky 連携

Bluesky アカウントと連携して画像を投稿できます。

### 設定

1. Settings > SNS タブで Bluesky ハンドルとアプリパスワードを設定
2. アプリパスワードは https://bsky.app/settings/app-passwords で発行

### 主な MCP ツール

| ツール名 | 説明 |
|---|---|
| `bsky_post_image` | 画像を Bluesky に投稿 |
| `bsky_get_profile` | プロフィール情報を取得 |
| `bsky_get_timeline` | タイムラインを取得 |
| `bsky_search_posts` | 投稿を検索 |
| `bsky_follow_user` | ユーザーをフォロー |
| `bsky_get_followers` | フォロワーリストを取得 |

### 使用例（MCP）

```
bsky_post_image(image_path="/path/to/image.png", text="今日の生成作品 #AIArt")
```

## GitHub 連携

GitHub リポジトリと連携してファイルや Issue を操作できます。

### 設定

Settings > API Keys タブで GitHub Personal Access Token を設定してください。

### 主な MCP ツール

| ツール名 | 説明 |
|---|---|
| `github_list_repos` | リポジトリ一覧を取得 |
| `github_get_file` | ファイル内容を取得 |
| `github_create_issue` | Issue を作成 |
| `github_list_issues` | Issue 一覧を取得 |
| `github_create_pr` | プルリクエストを作成 |
| `github_get_commits` | コミット履歴を取得 |

### 使用例（MCP）

```
github_list_issues(repo="owner/my-project", state="open")
```
