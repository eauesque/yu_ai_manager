# MCP 통합 가이드 — LLM에서 YU AI Manager 조작하기

YU AI Manager에는 LLM 애플리케이션이 자연어로 이미지 라이브러리를 조작할 수 있는 내장 **MCP (Model Context Protocol)** 서버가 있습니다.

이 애플리케이션에는 채팅 UI가 내장되어 있지 않습니다.
자연어로 상호작용하려면 선호하는 MCP 호환 클라이언트에서 연결하세요.

---

## MCP란?

MCP (Model Context Protocol)는 LLM 애플리케이션이 외부 도구와 데이터 소스에 접근할 수 있게 하는 표준 프로토콜입니다.
YU AI Manager는 MCP 서버 역할을 하며, LLM 클라이언트 (예: Claude Desktop)가 연결하여 자연어 지시를 API 조작으로 변환합니다.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM 클라이언트  │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline 등)    │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web Server          │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## 지원 MCP 클라이언트

다음은 대표적인 MCP 호환 클라이언트입니다. 설정 절차는 모두 유사합니다.

| 클라이언트 | 제공자 | 특징 |
|---|---|---|
| **Claude Desktop** | Anthropic | Claude 직접 접근. 네이티브 MCP 지원 |
| **Claude Code** | Anthropic | 개발자용 터미널 기반 클라이언트 |
| **Cline** | VS Code Extension | 에디터 통합. 멀티 LLM 지원 |
| **Open WebUI** | 오픈 소스 | 셀프 호스팅. Ollama 등 로컬 LLM과 조합 가능 |

참고: MCP 호환 클라이언트의 수는 빠르게 증가하고 있습니다.
stdio 전송을 지원하는 모든 클라이언트가 연결 가능합니다.

## 설정

### 1. YU AI Manager 시작

MCP 서버는 Web 서버의 API를 통해 동작하므로, YU AI Manager가 먼저 실행 중이어야 합니다.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. API 키 발급 (권장)

API 키를 발급하면 LAN 공유 또는 PIN 인증 사용 시 MCP 서버가 PIN 인증을 우회할 수 있습니다.

API 키는 설정 -> API 키에서 발급할 수 있습니다.

PIN 없이 실행하는 경우 (`config_test.json`) API 키는 불필요합니다.

### 3. MCP 클라이언트에 연결 설정 추가

#### Claude Desktop

`claude_desktop_config.json`을 편집합니다:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

프로젝트 루트의 `.mcp.json`에 설정을 추가하거나 `claude mcp add` 명령을 사용합니다:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

Cline의 MCP 설정을 통해 동일한 정보를 입력합니다.

#### 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web 서버 URL |
| `YU_API_KEY` | - | 없음 | API 키 (PIN 환경에서 필수) |
| `YU_DEBUG_MODE` | - | `0` | `1`로 설정하면 디버그 도구 추가 |

## 사용 예시

연결 후, LLM에 자연어 지시를 내려 이미지 라이브러리를 조작할 수 있습니다.

### 검색 및 열람

```
"파란 눈의 소녀 이미지 최신 20개를 보여줘"
"NovelAI로 생성된 이미지만 필터링해줘"
"지난주 스캔된 이미지 통계를 보여줘"
```

### 정리 및 분류

```
"이 10개 이미지에 별 5개 평가를 줘"
"'landscape' 태그가 있는 이미지를 '풍경 컬렉션'에 추가해줘"
"평가 3점 이하인 이미지를 모두 보여줘"
```

### 분석 및 어노테이션

```
"최근 추가된 이미지의 품질을 평가하고 어노테이션에 저장해줘"
"이미지 ID 12345의 모든 어노테이션을 보여줘"
"source agent:claude인 어노테이션을 검색해줘"
```

### 스캔 조작

```
"새로운 이미지를 스캔해줘"
"스캔 진행 상황을 확인해줘"
"스캔 오류를 보여줘"
```

## 사용 가능한 도구

MCP 서버는 다음 도구를 LLM에 노출합니다:

### 검색 및 열람 (4개 도구)

| 도구 이름 | 설명 |
|---|---|
| `search_images` | 태그, 날짜, 형식, 평가 등으로 이미지 검색 |
| `get_image_detail` | 이미지의 모든 메타데이터 조회 |
| `get_library_stats` | 라이브러리 통계 (파일 수, 태그 수, 소스 분포 등) |
| `find_similar` | 지각 해시를 사용한 유사 이미지 검색 |

### 컬렉션 (4개 도구)

| 도구 이름 | 설명 |
|---|---|
| `list_collections` | 컬렉션 목록 |
| `create_collection` | 컬렉션 생성 |
| `delete_collection` | 컬렉션 삭제 |
| `add_to_collection` / `remove_from_collection` | 이미지 추가/제거 |

### 태그 및 평가 (2개 도구)

| 도구 이름 | 설명 |
|---|---|
| `rate_images` | 여러 이미지에 별점 일괄 설정 |
| `set_tags` | 여러 이미지에 태그 일괄 추가/제거 |

### 어노테이션 (4개 도구)

| 도구 이름 | 설명 |
|---|---|
| `set_annotations` | AI 분석 결과를 어노테이션으로 저장 |
| `get_annotations` | 이미지의 어노테이션 조회 |
| `search_annotations` | 소스, 키, 신뢰도별 어노테이션 검색 |
| `delete_annotations` | 어노테이션 삭제 |

### 스캔 (3개 도구)

| 도구 이름 | 설명 |
|---|---|
| `trigger_scan` | 스캔 시작 |
| `get_scan_status` | 스캔 진행 상황 확인 |
| `get_scan_errors` | 스캔 오류 목록 |

### 기타

프롬프트 라이브러리, 백업, MCP 클라이언트 관리 도구도 포함되어 있습니다.

## FAQ

### Q: 앱에 채팅 기능이 없나요?

A: 없습니다. YU AI Manager는 이미지 메타데이터 관리에 특화되어 있으며, 대화형 AI 인터페이스는 MCP 호환 클라이언트에 위임합니다. Claude Desktop 등의 클라이언트를 병행하여 실행하면 자연어로 모든 조작을 수행할 수 있습니다.

### Q: 어떤 LLM을 사용해야 하나요?

A: MCP 클라이언트가 지원하기만 하면 어떤 LLM이든 가능합니다.
안정적인 도구 인수 처리를 위해서는 Claude나 GPT-4 급의 대규모 모델이 가장 일관된 성능을 보이는 경향이 있습니다.

### Q: 로컬 LLM을 사용할 수 있나요?

A: 네, Open WebUI + Ollama 등의 조합으로 MCP를 지원하는 로컬 LLM도 사용 가능합니다. 다만 도구 호출 정확도는 모델의 능력에 따라 다릅니다.

### Q: YU AI Manager에 MCP 클라이언트 기능도 있나요?

A: `MCP Client` Extension (Tools 페이지)은 YU AI Manager를 **다른 MCP 서버**에 연결합니다. 이 가이드는 반대 방향: 외부 LLM -> YU AI Manager를 설명합니다.
