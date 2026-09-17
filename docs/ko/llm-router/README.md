# LLM Router

> 대상 버전: v4.55.0 이상

## LLM Router란

LLM Router 는 yu_ai_manager에 내장된 **OpenAI 호환 LLM 프록시**입니다.  
Ollama, LM Studio, llama.cpp 등 여러 로컬 LLM 백엔드를 묶어서,  
Claude Code, Continue, Open WebUI 등의 클라이언트에 **단일 엔드포인트**로 제공합니다.

```
클라이언트 (Claude Code / Continue 등)
          │  (OpenAI 호환 API)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── mDNS 자동 발견 백엔드 (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### 기능

| 기능 | 기능 |
|---|---|
| **여러 백엔드 번들링** | LAN 상의 여러 Ollama 인스턴스 등록 가능 |
| **별칭을 이용한 추상화** | `"model": "fast"`로 실제 모델명 숨김 |
| **mDNS 자동 발견** | 동일 LAN의 yu_ai_manager 노드를 설정 없이 자동 등록 |
| **Claude Code 연동** | Anthropic 호환 `/v1/messages` 구현. 추가 프록시 불필요 |
| **동적 비활성화/활성화** | WebUI에서 백엔드를 즉시 전환. 재시작 불필요 |
| **카테고리 기반 라우팅** | 가상 백엔드 `large` / `fast` / `vision`으로 최적 모델 자동 선택 |

---

## 아키텍처

```
클라이언트 (Claude Code / Continue 등)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── 별칭 해석 ──► 백엔드 + 모델명
    │
    ├─ 수동으로 등록된 백엔드 (config.json에 작성된 것)
    └─ mDNS 자동 발견 백엔드 (alias: "mdns-<prefix>")
```

**요청 흐름:**

1. 클라이언트가 `"model": "claude-opus-4-7"`로 요청
2. Router가 `aliases` 테이블에서 `"claude-opus-4-7"` → `"large"`로 해석
3. `large` 카테고리에서 유효한 백엔드 선택
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## 문서 색인

| 기능 | 기능 |
|---|---|
| [설정](setup.md) | config.json 작성법, Claude Code/Continue 연동, mDNS 설정 |
| [WebUI](webui.md) | `/llm-router` 대시보드 조작법 |
| [Hailo 자동 발견](hailo-auto-discovery.md) | Hailo NPU 탑재 피어의 자동 등록 |
| [피어 도달 불능 대처](mdns-peer-unreachable.md) | mDNS로 발견된 피어가 `unreachable`이 되는 경우 |

---

## Gateway Gateway와의 차이점

| | LLM Router | Gateway |
|---|---|---|
| **대상** | LLM (Ollama 등) 만 | SD WebUI, ComfyUI, Ollama를 함께 |
| **인증 경계** | 로컬은 우회 가능. LAN 외에는 api_key 필요 | 모든 백엔드에 scope 기반 Bearer 인증 |
| **엔드포인트** | `/v1/*` (OpenAI/Anthropic 호환) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **주요 용도** | AI 코딩 도구의 백엔드 | 생성 도구를 외부 클라이언트에 안전하게 공개 |

두 기능은 독립적으로 동작합니다. LLM만 사용하는 경우 LLM Router만으로 충분합니다.

---

## LAN Cowork와의 관계

[LAN Cowork](../lan-cowork/README.md)가 활성화되면,  
동일 LAN 상의 피어가 mDNS로 자동 발견되어, LLM Router에  
`mdns-<node_id[:8]>` 별칭으로 자동 등록됩니다.  
설정 없이 멀티노드 LLM 환경이 구성됩니다.
