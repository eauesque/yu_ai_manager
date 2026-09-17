# Source Code Browsing API

프로젝트 소스 코드를 읽기 전용으로 탐색하는 API입니다.
MCP 도구 및 외부 AI 에이전트가 코드베이스를 안전하게 조회하고 검색할 수 있도록 설계되었습니다.

## 보안 모델

세 가지 방어 계층으로 안전성을 보장합니다:

### 1. 경로 정규화 (트래버설 방지)

- 모든 경로는 `os.path.realpath()`로 정규화하고 접두사 매칭으로 프로젝트 루트와 대조 검증합니다.
- `../../etc/passwd`나 `../../../Windows/System32`와 같은 트래버설 공격을 차단합니다.
- 널 바이트 인젝션(`\x00`)도 감지하여 거부합니다.

### 2. 확장자 화이트리스트

읽기가 허용되는 파일 확장자:

| 카테고리 | 확장자 |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| 웹 | `.html`, `.css`, `.scss` |
| 설정 | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| 문서 | `.md`, `.txt`, `.rst` |
| 스크립트 | `.sh`, `.bat`, `.cmd`, `.ps1` |
| 기타 | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

확장자가 없는 다음 파일은 특별히 허용됩니다: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. 민감 파일 차단 목록

다음 패턴에 일치하는 파일은 거부됩니다:

| 패턴 | 이유 |
|---------|--------|
| `config.json`, `config_*.json` | PIN, API Key 등 인증 데이터 |
| `*.env`, `.env.*` | 환경 변수 (시크릿) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | 암호화 키 및 인증서 |
| `credentials*`, `*token*`, `*secret*` | 인증 데이터 |
| `*.db`, `*.sqlite*` | 데이터베이스 파일 |
| `pnpm-lock.yaml`, `package-lock.json` 등 | 잠금 파일 (대용량) |
| 이미지, 동영상, 폰트, 모델 파일 | 바이너리 파일 |

### 차단된 디렉토리

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### 읽기 제한

| 항목 | 제한 |
|------|-------|
| 파일 크기 | 1 MB |
| 읽기당 줄 수 | 2,000 |
| 트리 탐색 깊이 | 6 |
| 검색 결과 | 50 |

---

## 엔드포인트

### GET /api/source/tree

디렉토리 트리를 조회합니다.

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `path` | string | `""` (루트) | 상대 경로 |
| `depth` | int | `3` | 탐색 깊이 (1-6) |

#### 응답

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- 디렉토리가 먼저, 파일이 뒤에 표시됩니다 (이름순 정렬).
- `size`는 바이트 단위입니다 (파일만 해당).
- 지정된 `depth`에 도달하면 `children`이 생략됩니다.

---

### GET /api/source/read

줄 번호와 함께 파일 내용을 읽습니다.

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `path` | string | — (필수) | 상대 파일 경로 |
| `offset` | int | `0` | 시작 줄 (0 기반) |
| `limit` | int | `2000` | 최대 줄 수 |

#### 응답

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content`는 `{줄_번호}\t{줄_내용}` 형식입니다.
- `offset` + `limit`를 사용하여 긴 파일을 페이지 단위로 읽을 수 있습니다.

#### 오류 예시

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

소스 코드 내 텍스트 검색입니다.

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `q` | string | — (필수) | 검색 텍스트 (최소 2자) |
| `glob` | string | `""` (모든 파일) | 파일명 필터 (예: `*.py`) |
| `limit` | int | `30` | 최대 결과 수 (1-50) |

#### 응답

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- 검색은 대소문자를 구분하지 않습니다.
- `text`는 최대 200자로 잘립니다.

---

## MCP 도구

| 도구 | 설명 | 주요 파라미터 |
|------|-------------|----------------|
| `source_tree` | 디렉토리 트리 표시 | `path`: str = '', `depth`: int = 3 |
| `source_read` | 파일 내용 읽기 | `path`: str (필수), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | 텍스트로 소스 코드 검색 | `query`: str (필수), `glob`: str = '', `limit`: int = 30 |

### MCP 사용 예시

```
# 프로젝트 구조 확인
source_tree(path="", depth=2)

# 특정 파일 읽기
source_read(path="core/source_core/source_browser.py")

# 코드베이스 내 검색
source_search(query="def register_blueprints", glob="*.py")
```

### 범위 및 속도 제한

- **Scope Fence**: `read_only` 범위에서 사용 가능 (모든 프리셋에서 허용)
- **Budget Tracker**: `read` 카테고리 (속도 제한 없음)
- **HITL Gate**: 레벨 0 (승인 불필요)

---

## 구현 파일

| 파일 | 역할 |
|------|------|
| `core/source_core/source_browser.py` | 보안 계층 + 비즈니스 로직 |
| `routes/source_api.py` | Flask API 엔드포인트 (Blueprint) |
| `mcp_server/source_tools.py` | MCP 도구 등록 |
