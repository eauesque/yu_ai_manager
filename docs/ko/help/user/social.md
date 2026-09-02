# SNS 및 외부 연동

YU AI Manager는 MCP 도구를 통해 Bluesky, GitHub 등 외부 서비스와 연동할 수 있습니다.

## Bluesky 연동

YU AI Manager에서 직접 Bluesky에 이미지를 게시할 수 있습니다.

### 설정

1. Settings > SNS 탭에서 Bluesky 핸들과 앱 비밀번호를 입력
2. https://bsky.app/settings/app-passwords 에서 앱 비밀번호를 생성

### 주요 MCP 도구

| 도구 이름 | 설명 |
|---|---|
| `bsky_post_image` | Bluesky에 이미지 게시 |
| `bsky_get_profile` | 프로필 정보 가져오기 |
| `bsky_get_timeline` | 타임라인 가져오기 |
| `bsky_search_posts` | 게시물 검색 |
| `bsky_follow_user` | 사용자 팔로우 |
| `bsky_get_followers` | 팔로워 목록 가져오기 |

## GitHub 연동

GitHub 저장소, Issue 및 Pull Request와 상호작용합니다.

### 설정

Settings > API Keys에서 GitHub Personal Access Token을 설정하세요.

### 주요 MCP 도구

| 도구 이름 | 설명 |
|---|---|
| `github_list_repos` | 저장소 목록 가져오기 |
| `github_get_file` | 파일 내용 가져오기 |
| `github_create_issue` | Issue 생성 |
| `github_list_issues` | Issue 목록 가져오기 |
| `github_create_pr` | Pull Request 생성 |
| `github_get_commits` | 커밋 이력 가져오기 |
