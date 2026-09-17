# SNS 與外部整合

YU AI Manager 可透過 MCP 工具與 Bluesky、GitHub 等外部服務整合。

## Bluesky 整合

可將圖片直接從 YU AI Manager 發佈至 Bluesky。

### 設定

1. 在 Settings > SNS 分頁中輸入 Bluesky 帳號和應用程式密碼
2. 在 https://bsky.app/settings/app-passwords 建立應用程式密碼

### 主要 MCP 工具

| 工具名稱 | 說明 |
|---|---|
| `bsky_post_image` | 將圖片發佈至 Bluesky |
| `bsky_get_profile` | 取得個人資料 |
| `bsky_get_timeline` | 取得時間軸 |
| `bsky_search_posts` | 搜尋貼文 |
| `bsky_follow_user` | 追蹤使用者 |
| `bsky_get_followers` | 取得追蹤者清單 |

## GitHub 整合

與 GitHub 儲存庫、Issue 和 Pull Request 互動。

### 設定

在 Settings > API Keys 中設定 GitHub Personal Access Token。

### 主要 MCP 工具

| 工具名稱 | 說明 |
|---|---|
| `github_list_repos` | 列出儲存庫 |
| `github_get_file` | 取得檔案內容 |
| `github_create_issue` | 建立 Issue |
| `github_list_issues` | 列出 Issue |
| `github_create_pr` | 建立 Pull Request |
| `github_get_commits` | 取得提交歷史 |
