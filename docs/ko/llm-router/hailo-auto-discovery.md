# Hailo LLM 자동 발견

**대응 버전**: v4.66.0 이후

## 개요

yu_ai_manager는 Pi5의 Hailo NPU에서 동작하는 LLM 엔드포인트를
`config.json` 편집 없이 자동으로 발견하여 사용할 수 있도록 합니다.
Pi5를 LAN에 연결하기만 하면, 다른 yu_ai_manager 노드에서 Hailo LLM을
호출할 수 있습니다.

## 감지 대상 2계통

| 엔드포인트 | 설명 | 기본 URL 패턴 |
|---|---|---|
| **yu extension Hailo LLM** | yu_ai_manager 내장 `builtin-hailo-genai` extension이 제공하는 OpenAI 호환 LLM | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | 외부 바이너리 `/usr/bin/hailo-ollama`가 제공하는 OpenAI 호환 LLM (기본 `:8000`) | `http://<host>:8000/v1/` |

둘 다 동시에 동작해도 모두 자동 등록됩니다. HailoRT 5.3.0+에서
`HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED`를 설정하면 HailoRT scheduler가
물리 디바이스를 round-robin으로 공유하므로, 동시에 사용해도 충돌하지 않습니다.

## 로컬 자동 등록 (Phase A)

yu_ai_manager 시작 시 다음 2가지를 독립적으로 감지합니다:

1. **yu extension**: `hailo_platform.genai.LLM`이 import 가능하고,
   `/dev/hailo0` 또는 `/dev/h1x-0` 중 하나가 존재 → `hailo-local`
   backend로 catalog에 자동 등록
   (v4.66.1에서 Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 실기가
   `/dev/h1x-0`으로 공개되는 것에 대응)
2. **hailo-ollama**: `localhost:8000/v1/models`에 HTTP probe (2초 타임아웃)
   → 200 응답이 오면 `hailo-ollama-local` backend로 자동 등록

이미 `config.json`의 `llm_router.backends`에 동일 이름의 alias가 있으면
해당 설정이 우선됩니다 (덮어쓰지 않음).

## mDNS 자동 광고 (Phase B)

Phase A의 감지 결과에 따라 yu_ai_manager는 mDNS TXT 레코드로 다른 노드에
Hailo capability를 광고합니다:

- `capabilities=llm,hailo` — yu extension이 이용 가능함을 표시
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` — hailo-ollama가 동작 중인
  경우에만 (LAN 도달 가능한 IP로 변환됨)

다른 yu_ai_manager 노드가 mDNS를 통해 이를 수신하면 `/api/mdns/identity`
엔드포인트에서 identity 검증을 수행한 후, 다음 alias로 추가 backend를
자동 등록합니다:

- `mdns-<node_id[:8]>-hailo` — yu extension Hailo LLM (`capabilities`에
  `hailo`가 포함된 경우, peer의 `web_port` + addresses에서 URL 도출)
- `mdns-<node_id[:8]>-hailo-ollama` — 외부 hailo-ollama (`hailo_ollama_url`이
  광고된 경우, TXT에 게시된 URL을 그대로 사용)

## 설정

기본으로 활성화됨. `config.json`에서 다음과 같이 비활성화할 수 있습니다:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: `false`로 설정하면 hailo-ollama 자동 감지를 완전히 비활성화.
  yu extension 측 감지는 별도로 제어됩니다 (extension 로드 여부로 자동 판정)
- **`port`**: hailo-ollama의 포트 번호 (기본 8000). 1~65535 범위 외는 기본값으로
  폴백되며 warning 로그를 출력합니다

## 보안 주의사항

**hailo-ollama에는 인증 기능이 없습니다**. mDNS로 광고하면 **LAN 상의
모든 노드가 hailo-ollama의 추론 리소스를 자유롭게 소비할 수 있는 상태**가 됩니다.

| 엔드포인트 | 인증 | 실질적인 LAN 공개 범위 |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | yu의 web auth chain (PIN/session/api-key) | yu에 인증 가능한 클라이언트만 |
| hailo-ollama (`hailo_ollama_url`) | **없음** | **LAN 상의 모든 노드** |

가정 내 LAN이나 신뢰할 수 있는 VLAN 이외의 환경 (공용 Wi-Fi 등)에서는
`hailo_ollama.enabled: false`로 자동 광고를 비활성화하세요.

## LLM Router WebUI에서의 표시

v4.65.0의 `/llm-router` 대시보드에 자동 등록된 backend가 표시됩니다:

- `hailo-local` / `hailo-ollama-local` — 로컬 감지 (source: `static` 배지)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` — mDNS로 발견 (source: `mdns` 배지)

모두 Disable 토글로 일시적으로 비활성화 가능합니다. 비활성화 상태는
`data/llm_router_state.json`에 영구 저장되며, 재시작 후에도 유지됩니다
(v4.65.0에서 구현).

## 오감지 안전장치

Phase A 감지에는 2가지 안전장치가 있습니다:

1. **자기 probe 회피**: `hailo_ollama.port`가 yu 자신의 web port와 동일한 값으로
   설정된 경우, probe를 완전히 건너뜁니다 (yu가 자기 자신을
   hailo-ollama로 오인하는 것을 방지)
2. **기존 backend 우선**: `config.json`에 동일한 `localhost:<port>/v1`
   backend가 이미 등록된 경우, probe를 건너뛰어 사용자의 의도를 존중합니다

## TODO 잔여 항목

- (P3) 다국어 번역 (`en`, `zh-tw`, `zh-cn`, `ko`) — v4.65.0 LLM Router WebUI
  번역 잔여분과 함께 일괄 대응 예정
- (P3) Pi5 실기 결합 테스트 — 2노드 구성에서의 Playwright 16항목 상당
- (P3) IPv6 지원 — 현재 `_pick_lan_ip`는 IPv4만 반환
- (P3) 복수 Hailo 디바이스 대응 — 고정 alias `hailo-local` 전제. USB 동글
  다수 연결 등의 경우 index suffix 설계 검토
- (P3) `BackendCatalog.remove_backend()` — 현재 `_mark_unreachable`는
  status 업데이트만 수행하고 catalog에서 삭제하지 않음

## 관련 문서

- [LLM Router 설정](./setup.md)
- 설계 사양: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- 구현 계획: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 — Trusted peer auth (실기 인증 구멍 수정)

v4.66.0의 Hailo 자동 발견에서는 yu의 `/ext/hailo-genai/*` extension이
web auth chain 하에 있기 때문에, LLM Router driver (Bearer도 session도
가지고 있지 않음)가 probe/dispatch하려 하면 인증 middleware의 honeypot
HTML이 반환되어 JSON parse에 실패하고 `unreachable` 상태로 고정되는 문제가
있었습니다.

### 구조

- 신규 `TrustedPeerRegistry`가 `127.0.0.1` / `::1`을 init 시 seed
- `LlmRouterMdnsBridge`가 peer의 verify (`/api/mdns/identity`에 HTTP
  GET + node_id 일치 확인)에 성공하면, 해당 peer의 advertised
  addresses를 모두 registry에 추가
- `auth_chain.check_trusted_peer`가 `/ext/<name>/v1/*` 경로를 받았을 때,
  remote_addr가 registry에 있으면 PIN auth를 bypass
- 기존 API key / session / cookie 인증 경로는 그대로 유지

### Quick lock과의 관계

- **loopback** (yu 자신의 self-probe): quick_lock 중에도 항상 pass
- **peer IP**: quick_lock 중에는 요청을 reject (`check_quick_lock`이
  503을 반환). "사용자가 의도적으로 잠근" 상태를 peer도 존중

이로 인해 다음이 기대대로 동작합니다:

- pi2의 `hailo-local` self-probe (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Windows에서 본 pi2의 `mdns-<id>-hailo` cross-node dispatch
  (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### 설정

설정 파일 변경 불필요. mDNS가 비활성화된 환경에서도 loopback seed는
동작하므로, self-probe 수정만은 무조건 얻을 수 있습니다.

### 디버그

`TAGDB_DEBUG_TRUSTED_PEERS=1` 환경 변수를 설정하고 yu를 시작하면,
`/api/mdns/peers` 응답에 `trusted_ips` 필드가 추가됩니다.
프로덕션 운용에서는 설정하지 마세요 (trust 리스트는 "공격 대상 리스트"이므로,
unauthenticated 엔드포인트에의 노출을 방지).

### Security boundary

"신뢰할 수 있는 LAN 전제" 운용 규칙 (v4.64.0 mDNS Phase B 시점과 동일 전제).
LAN에 물리적 접근이 가능한 악의적 노드로부터의 보호는 대상 외 — 해당 경우에는
`/llm-router` WebUI의 disable 토글이나 quick_lock으로 대처합니다.

상세는 `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md`.
