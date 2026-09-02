# API: /api/mdns (피어 발견)

> 대상 버전: v4.64.0 이후 (Hailo 확장은 v4.66.0 이후)

LAN 상의 yu_ai_manager 노드가 mDNS (`_yu-ai._tcp.local.`)로 서로를 발견하기 위한 API입니다. 엔드포인트는 2개입니다.

---

## GET /api/mdns/identity

### 개요

노드의 자기소개 엔드포인트. 다른 노드가 피어 검증 시 호출하여, mDNS로 어드버타이즈한 정보가 진짜 yu_ai_manager 인스턴스의 것인지 확인합니다.

### 인증

**인증 바이패스 (불필요).** 피어 간 상호 검증에 사용하므로 의도적으로 인증을 해제했습니다. 응답에는 mDNS로 이미 공개된 정보만 포함됩니다. 시크릿이나 기밀 정보는 일절 포함되지 않습니다.

### 응답

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `product` | string | 항상 `"yu_ai_manager"` |
| `node_id` | string | 노드의 고유 UUID |
| `version` | string | 앱 버전 (VERSION 파일에서 읽음) |
| `capabilities` | string[] | 이용 가능한 기능 목록. 현재는 `"hailo"`만 해당 |
| `hailo_ollama_url` | string (생략 가능) | Hailo-Ollama의 LAN 액세스 URL. LAN IP를 특정할 수 없는 경우 포함되지 않음 |

**`capabilities`에 `"hailo"`가 포함되는 조건:** LLM Router 카탈로그에 `"hailo-local"` 백엔드가 등록되어 있는 경우.

**`hailo_ollama_url`이 포함되는 조건:** 카탈로그에 `"hailo-ollama-local"`이 등록되어 있고, LAN IP를 특정할 수 있는 경우. 루프백 주소 (`127.0.0.1` 등)는 LAN IP로 변환됩니다.

---

## GET /api/mdns/peers

### 개요

이 노드가 발견한 LAN 피어의 목록을 반환합니다. mDNS 서브시스템의 상태 확인 및 디버그용입니다.

### 인증

**인증 바이패스 (불필요).** 응답에는 mDNS로 이미 LAN에 브로드캐스트된 정보만 포함됩니다.

### 응답 (통상 시)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `running` | bool | mDNS 서브시스템이 가동 중인지 여부 |
| `status` | string | 서브시스템의 상태 문자열 |
| `self_node_id` | string | 자신의 node_id |
| `peers` | object[] | 발견된 피어의 목록 (아래 표 참조) |

**peers 각 요소:**

| 필드 | 타입 | 설명 |
|---|---|---|
| `node_id` | string | 피어의 고유 UUID |
| `hostname` | string | mDNS 호스트명 |
| `version` | string | 피어의 앱 버전 |
| `llm_base_url` | string \| null | 피어의 LLM 엔드포인트 URL |
| `llm_provider` | string \| null | LLM 프로바이더명 (예: `"ollama"`) |
| `capabilities` | string[] | 피어의 capability 목록 |
| `web_port` | int \| null | 피어의 Web UI 포트 |
| `addresses` | string[] | 피어의 LAN IP 주소 목록 |
| `hailo_ollama_url` | string \| null | 피어의 Hailo-Ollama URL |
| `first_seen` | float \| null | 최초 발견 시각 (Unix 타임스탬프) |
| `last_seen` | float \| null | 마지막 확인 시각 (Unix 타임스탬프) |

### 응답 (mDNS 미초기화 시)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

`running: false`인 경우 mDNS가 비활성화되었거나 초기화에 실패한 것입니다. 설정 및 시작 로그를 확인하세요.

---

## 디버그 모드

환경 변수 `TAGDB_DEBUG_TRUSTED_PEERS=1`을 설정하고 시작하면, `/api/mdns/peers`의 응답에 추가 필드가 포함됩니다.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| 필드 | 설명 |
|---|---|
| `trusted_ips` | 신뢰 IP 레지스트리에 등록된 IP 목록 |
| `bridge.managed_aliases` | mDNS 브리지가 관리하는 에일리어스 목록 |
| `bridge.config_aliases` | config에서 정적으로 정의된 에일리어스 목록 |
| `bridge.cooldown_seconds_remaining` | node_id 앞 8문자를 키로 한 쿨다운 잔여 초수 |

**주의:** `trusted_ips`는 공격 대상 리스트가 될 수 있으므로, 기본적으로 비공개입니다. 프로덕션 환경에서는 `TAGDB_DEBUG_TRUSTED_PEERS=1`을 설정하지 마세요.

---

## mDNS 발견 플로우

```
다른 노드 시작
    │
    ▼
mDNS _yu-ai._tcp.local. 어드버타이즈
    │
    ▼
LlmRouterMdnsBridge가 on_peer_added()를 수신
    │
    ▼
GET /api/mdns/identity로 HTTP 검증
    │
    ├─ 성공 → PeerRegistry / BackendCatalog에 등록
    └─ 실패 → 쿨다운 후 재시도
```

---

## 관련 파일

- `routes/mdns_identity.py` — 엔드포인트 구현
- `core/mdns/` — mDNS 서비스 / 주소 유틸리티
- `core/llm_router/state.py` — BackendCatalog
- `core/web/trusted_peer_registry.py` — 신뢰 IP 레지스트리
- `docs/ko/mesh-inference/overview.md` — 메시 추론 아키텍처 전체
