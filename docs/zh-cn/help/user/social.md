# SNS 与外部集成

YU AI Manager 可通过 MCP 工具与 Bluesky、GitHub 等外部服务集成。

## Bluesky 集成

可将图片直接从 YU AI Manager 发布到 Bluesky。

### 设置

1. 在 Settings > SNS 标签页中输入 Bluesky 账号和应用密码
2. 在 https://bsky.app/settings/app-passwords 创建应用密码

### 主要 MCP 工具

| 工具名称 | 说明 |
|---|---|
| `bsky_post_image` | 将图片发布到 Bluesky |
| `bsky_get_profile` | 获取个人资料 |
| `bsky_get_timeline` | 获取时间线 |
| `bsky_search_posts` | 搜索帖子 |
| `bsky_follow_user` | 关注用户 |
| `bsky_get_followers` | 获取关注者列表 |

## GitHub 集成

与 GitHub 仓库、Issue 和 Pull Request 交互。

### 设置

在 Settings > API Keys 中设置 GitHub Personal Access Token。

### 主要 MCP 工具

| 工具名称 | 说明 |
|---|---|
| `github_list_repos` | 列出仓库 |
| `github_get_file` | 获取文件内容 |
| `github_create_issue` | 创建 Issue |
| `github_list_issues` | 列出 Issue |
| `github_create_pr` | 创建 Pull Request |
| `github_get_commits` | 获取提交历史 |
