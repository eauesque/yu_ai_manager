# 커스텀 UI 개발 가이드

이 가이드는 YU AI Manager 프론트엔드를 완전히 교체할 수 있는 커스텀 UI 시스템에 대해 설명합니다.

## 목차

- [개요](#개요)
- [아키텍처](#아키텍처)
- [시작하기](quickstart.md) -- 최소한의 커스텀 UI 만들기
- [디자인 가이드](design-guide.md) -- CSS 디자인, 테마, 반응형 레이아웃, 컴포넌트
- [템플릿 가이드](templates.md) -- Jinja2 패턴, i18n, 페이지 구조
- [고급 기능](advanced.md) -- SSE 실시간 업데이트, 배치 작업, 보안
- [API 레퍼런스](api-reference.md) -- 전체 API 문서 링크

## 개요

YU AI Manager는 백엔드 API와 프론트엔드를 완전히 분리하고 있습니다. 프론트엔드를 커스텀 구현으로 교체하는 것이 간단합니다. `ui/<name>/` 디렉토리에 배치하기만 하면 커스텀 UI가 활성화됩니다.

### 기능

- **전체 UI 교체**: 검색, 통계, 설정 등 모든 페이지를 원하는 디자인으로 교체 가능
- **테마 커스터마이징**: CSS 변수만 덮어써서 색상 스킴을 변경 가능
- **부분 교체**: 필요한 페이지만 커스터마이징하고 나머지는 기본 UI로 폴백
- **AI 생성 UI**: API 문서를 Claude나 ChatGPT에 전달하여 자동으로 UI 생성 가능

### 아키텍처

```
yu_ai_manager/
├── ui/
│   ├── default/              # 레퍼런스 UI (내장)
│   │   ├── manifest.json     # UI 메타데이터 (필수)
│   │   ├── templates/        # Jinja2 HTML 템플릿
│   │   │   ├── index.html    # 메인 검색 페이지
│   │   │   ├── stats.html    # 통계 대시보드
│   │   │   ├── tools.html    # 도구 페이지
│   │   │   ├── settings.html # 설정 페이지
│   │   │   ├── story.html    # Your Story 페이지
│   │   │   ├── inspect.html  # 메타데이터 인스펙터
│   │   │   └── _nav.html     # 공유 네비게이션 바 (include)
│   │   └── static/           # CSS, JS, 이미지
│   │       ├── css/          # 스타일시트
│   │       ├── dist/         # TypeScript 빌드 출력
│   │       └── favicon.svg   # 파비콘
│   ├── custom/               # 커스텀 UI (gitignored, 자동 감지)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # 추가 UI (임의 이름)
│       ├── manifest.json
│       └── ...
├── routes/                   # 서버사이드 API 라우트
│   ├── pages.py              # 페이지 라우팅 정의
│   └── ...                   # 각종 API 엔드포인트
└── docs/api/                 # API 문서
```

### UI 해결 순서

서버는 시작 시 다음 우선순위에 따라 사용할 UI를 결정합니다:

| 우선순위 | 조건 | 동작 |
|----------|------|------|
| 1 | `config.json`에 `"ui": "my-theme"` 포함 | 지정된 `ui/my-theme/` 사용 |
| 2 | `ui/custom/`에 유효한 `manifest.json` 존재 | 자동 감지하여 `ui/custom/` 사용 |
| 3 | 위 조건 모두 해당하지 않음 | `ui/default/`로 폴백 |

### manifest.json

모든 커스텀 UI에는 `manifest.json`이 필요합니다:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | 예 | UI 식별자 (디렉토리 이름과 일치 권장) |
| `version` | 예 | 시맨틱 버전 |
| `description` | 아니오 | UI 설명 |
| `author` | 아니오 | 작성자 이름 |
| `api_version` | 아니오 | 지원하는 API 버전 (`"1"`) |
| `type` | 아니오 | `"full"` (기본값) 또는 `"theme"` |

### 정적 파일 서빙

커스텀 UI 내의 `static/` 디렉토리는 Flask `/static/` URL에 매핑됩니다:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

HTML에서 참조:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI 관리 API

설정 페이지의 "UI" 탭이나 API를 통해 UI를 관리할 수 있습니다:

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/ui/list` | 설치된 UI 목록 |
| POST | `/api/ui/switch` | 활성 UI 전환 (재시작 필요) |
| POST | `/api/ui/install` | URL에서 UI 설치 (localhost만 가능) |
| DELETE | `/api/ui/<name>/uninstall` | UI 제거 (localhost만 가능) |

### MCP 도구

MCP (Model Context Protocol)를 통해서도 UI를 관리할 수 있습니다:

- `list_uis()` -- 설치된 UI 목록
- `switch_ui(name)` -- 활성 UI 전환
- `install_ui(url)` -- URL에서 UI 설치
- `uninstall_ui(name)` -- UI 제거
