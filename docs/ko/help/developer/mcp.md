# MCP 연동

YU AI Manager에는 MCP (Model Context Protocol) 서버가 내장되어 있어
Claude Desktop, Claude Code, Cline 등의 AI 클라이언트에서 직접 조작할 수 있습니다.
137개 이상의 도구를 제공하여 이미지 관리부터 AI 분석까지 모든 기능에 접근할 수 있습니다.

## 지원 MCP 클라이언트

| 클라이언트 | 연결 방법 | 비고 |
|------------|-----------|------|
| Claude Desktop | stdio / HTTP | 권장 클라이언트 |
| Claude Code | stdio | CLI 환경 |
| Cline (VS Code) | stdio | VS Code 확장 |
| Open WebUI | HTTP/SSE | 웹 기반 |

## 로컬 연결 (stdio)

같은 머신에서 Claude Desktop / Claude Code로 연결하려면:

1. 설정 > API Keys 탭에서 API 키를 생성합니다
2. 클라이언트 설정 파일에 다음을 추가합니다

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## LAN 연결 (HTTP/SSE)

LAN의 다른 머신에서 연결하려면:

1. YU AI Manager에서 LAN 접근을 활성화합니다
2. API 키를 생성합니다
3. 설정 > API Keys 탭의 "MCP Connection Snippet"에서 연결 설정을 복사합니다

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## 사용 가능한 도구 (카테고리별)

### 이미지 검색 및 관리

| 도구 | 설명 |
|------|------|
| `search_images` | 태그, 날짜, 평가 등으로 필터 검색 |
| `get_image_detail` | 상세 이미지 메타데이터 조회 |
| `get_library_stats` | 라이브러리 통계 (파일 수, 태그 분포 등) |
| `find_similar` | 지각적 해싱을 사용한 유사 이미지 감지 |
| `rate_images` | 배치 별점 설정 |
| `set_tags` | 태그 추가 또는 제거 |
| `set_annotations` | 어노테이션 설정 |
| `get_annotations` | 어노테이션 조회 |

### 컬렉션

| 도구 | 설명 |
|------|------|
| `list_collections` | 컬렉션 목록 |
| `create_collection` | 컬렉션 생성 |
| `add_to_collection` | 컬렉션에 이미지 추가 |
| `remove_from_collection` | 컬렉션에서 이미지 제거 |
| `delete_collection` | 컬렉션 삭제 |

### 스캔

| 도구 | 설명 |
|------|------|
| `trigger_scan` | 스캔 실행 |
| `get_scan_status` | 스캔 진행률 확인 |
| `list_scan_roots` | 스캔 루트 목록 |
| `add_scan_root` | 스캔 루트 추가 |
| `scan_directory` | 특정 디렉토리 스캔 |

### AI 분석

| 도구 | 설명 |
|------|------|
| `analyze_image` | AI 이미지 분석 (단일) |
| `analyze_batch` | AI 이미지 분석 (배치) |
| `wd_tagger_tag_file` | WD-Tagger 추론 (단일) |
| `wd_tagger_batch` | WD-Tagger 추론 (배치) |
| `semantic_search` | CLIP 시맨틱 검색 |
| `s2t_transcribe_video` | 음성 인식 |

### Bridge 연동

| 도구 | 설명 |
|------|------|
| `sd_generate` | SD WebUI로 이미지 생성 |
| `sd_list_models` | SD WebUI 모델 목록 |
| `comfyui_generate` | ComfyUI로 이미지 생성 |
| `comfyui_generate_json` | ComfyUI 워크플로 JSON 실행 |

### 프롬프트 라이브러리

| 도구 | 설명 |
|------|------|
| `create_prompt` | 프롬프트 생성 |
| `search_prompts` | 프롬프트 검색 |
| `get_prompt` | 프롬프트 조회 |
| `update_prompt` | 프롬프트 업데이트 |

### 설정

| 도구 | 설명 |
|------|------|
| `settings_get_schema` | 설정 스키마 조회 |
| `settings_get` | 설정 값 조회 |
| `settings_set` | 설정 값 업데이트 |
| `secrets_status` | 암호화 키 상태 확인 |

### Agent Safety

| 도구 | 설명 |
|------|------|
| `agent_kill` / `agent_resume` | Kill Switch 제어 |
| `agent_status` | 안전 메커니즘 상태 |
| `agent_journal` | 작업 저널 검색 |
| `agent_undo` | 작업 실행 취소 |
| `agent_circuit_breaker_status` | Circuit Breaker 상태 |
| `agent_budget_status` | Budget tracker 상태 |
| `agent_scope_set` | 스코프 설정 |
| `agent_anomaly_status` | 이상 감지 상태 |

### 기타

| 도구 | 설명 |
|------|------|
| `find_duplicates` | 중복 파일 감지 |
| `search_chat_logs` | 채팅 로그 검색 |
| `search_md_files` | Markdown 파일 검색 |
| `help_search` | 도움말 문서 검색 |
| `share_to_bluesky` | Bluesky에 게시 |
| `list_trophies` | 트로피 목록 |
| `get_monthly_report` | 월간 보고서 |

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `YU_BASE_URL` | 서버 URL | `http://localhost:5000` |
| `YU_API_KEY` | API 키 | (필수) |
| `YU_DEBUG_MODE` | 디버그 도구 활성화 | `0` |

`YU_DEBUG_MODE=1`을 설정하면 직접 DB 쿼리 및 상태 검사와 같은 디버그 전용 도구가 추가됩니다.

## 문제 해결

### 연결할 수 없음

1. YU AI Manager가 실행 중인지 확인
2. API 키가 올바른지 확인 (`sk_` 접두사 필수)
3. `YU_BASE_URL`이 올바른지 확인
4. LAN 연결의 경우 LAN 접근이 활성화되어 있는지 확인

### 도구를 찾을 수 없음

- Extension이 비활성화되면 해당 도구를 사용할 수 없습니다
- `list_extensions`로 활성화 상태를 확인하세요

### 타임아웃

- 대규모 라이브러리의 검색 및 배치 작업은 시간이 걸릴 수 있습니다
- `limit` 파라미터를 사용하여 결과 수를 제한하세요
