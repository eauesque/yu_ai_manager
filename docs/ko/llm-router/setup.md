# LLM Router 설정

## config.json 추가

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Claude Code 연동

LLM Router 는 Anthropic 호환 `/v1/messages` 엔드포인트를 구현하고 있어
Claude Code (Anthropic 공식 CLI) 를 **그대로 로컬 LLM 용으로 사용**할 수
있습니다. 추가 프록시 (claude-code-router 등) 는 필요 없습니다.

### 1. yu_ai_manager 측 alias 설정

Claude Code 는 내부적으로 `claude-opus-4-*` / `claude-sonnet-4-*` /
`claude-haiku-4-*` 등의 모델명을 보냅니다. 이를 `config.json` 의 `aliases`
에서 로컬 카테고리 (`large` / `fast` / `vision`) 또는 물리 모델로 매핑합니다:

```json
{
  "llm_router": {
    "enabled": true,
    "aliases": {
      "claude-opus-4-7":           "large",
      "claude-sonnet-4-6":         "fast",
      "claude-haiku-4-5":          "fast",
      "claude-3-5-haiku-20241022": "fast"
    }
  }
}
```

| Claude Code 가 보내는 모델명 | 권장 매핑 대상 | 용도 |
|---|---|---|
| `claude-opus-*` | `large` (예: qwen2.5:72b / llama3.3:70b) | 메인 추론 |
| `claude-sonnet-*` | `fast` 또는 `large` | 균형 |
| `claude-haiku-*` | `fast` (예: qwen2.5:7b) | 백그라운드 작업 (요약·제목 생성 등) |

`large` / `fast` / `vision` 은 `core/llm_core` 카테고리 레지스트리 기반의
가상 백엔드이며, 등록된 모델 중에서 자동 선택됩니다 (`/llm-router` WebUI 에서 확인 가능).

### 2. Claude Code 측 설정

`~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`) 에 추가:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy"
  }
}
```

- `ANTHROPIC_AUTH_TOKEN` 은 loopback 접속에서는 검증되지 않지만 Claude Code 가
  변수 존재를 요구하므로 임의 문자열을 넣습니다
- LAN 의 다른 머신에서 접속할 경우 `http://<host>.local:5000/v1` 로 변경하고,
  `config.json` 의 `auth.mode` 를 `api_key` 로 바꿔 실제 토큰을 설정합니다

세션 단위로만 테스트할 때는 환경 변수로:

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 ANTHROPIC_AUTH_TOKEN=dummy claude
```

### 3. 백그라운드 작업 (haiku 상당) 만 다른 모델로

Claude Code 의 백그라운드 작업은 `ANTHROPIC_SMALL_FAST_MODEL` 로 덮어쓸 수 있습니다:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_SMALL_FAST_MODEL": "fast"
  }
}
```

메인은 alias 경유 (opus → large), 백그라운드는 명시적으로 `fast` 카테고리로 분기됩니다.

### 4. 동작 확인

```bash
# /v1/messages 가 응답하는지
curl -s http://localhost:5000/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}'

# Claude Code 에서
claude
> /model          # 현재 모델 확인
> hello           # 응답이 오면 로컬 경유로 동작 중
```

### 5. 자주 발생하는 문제

| 증상 | 원인 / 대처 |
|---|---|
| `model_not_found` 에러 | Claude Code 가 보낸 모델명이 alias / 카테고리 어느 쪽에도 일치하지 않음. `/llm-router` WebUI 의 요청 로그에서 모델명을 확인하고 alias 추가 |
| 응답이 매우 느림 | `large` 카테고리가 70B 급 모델을 잡음. alias 에서 구체적인 경량 모델로 직접 매핑 |
| `401 unauthorized` | `auth.mode` 가 `api_key` 인데 Claude Code 의 `ANTHROPIC_AUTH_TOKEN` 이 일치하지 않음 |
| 스트림이 도중에 끊김 | 백엔드 (Ollama 등) 타임아웃이 짧음. `config.json` 의 `backends[].timeout` 을 120 이상으로 |

### 6. 물리명 / 커스텀 alias 직접 지정

`aliases` 섹션에는 Claude 모델명 외의 이름도 자유롭게 추가 가능합니다:

```json
"aliases": {
  "local-fast":  "ollama-local/qwen2.5:7b",
  "local-coder": "ollama-mac/qwen2.5-coder:32b"
}
```

Claude Code 에서 `/model local-coder` 처럼 지정하면 직접 해당 모델로 라우팅됩니다.

### 7. 하이브리드 운용 (opus = 실제 Anthropic, sonnet/haiku = 로컬) 의 현황

"오케스트레이터는 Anthropic 의 opus, 서브 에이전트만 로컬" 이라는 분할 운용은
**현재의 Claude Code + LLM Router 에서는 권장하지 않습니다**. 이유:

- `ANTHROPIC_BASE_URL` 은 세션 전체에 적용되므로 "opus 요청만 Anthropic 본가로
  직통" 시키는 설정을 Claude Code 측에서 구성할 수 없음
- LLM Router 에 upstream passthrough 백엔드를 추가하는 것은 기술적으로 가능하지만,
  **경제성이 성립하지 않음**:
  - **Max/Pro 구독 사용자**: `ANTHROPIC_BASE_URL` 을 설정한 시점에 구독 인증
    경로에서 벗어나, passthrough 된 opus 요청만큼 API 단가로 과금됨 (오히려 더 비쌈)
  - **API 키 과금 사용자**: passthrough 해도 opus 의 토큰 단가는 변하지 않으며,
    오케스트레이터가 소비하는 opus 토큰이 지배적이므로 서브 에이전트만 로컬화해도
    절감 효과가 미미

**권장 방침**: 비용 절감이 목적이라면 **오케스트레이터까지 포함해 전부 로컬**
(예: `claude-opus-*` 도 `large` 카테고리로 alias) 로 돌리고, 로컬 측 모델 선정
(Qwen2.5-72B / Llama 3.3-70B / DeepSeek 등) 으로 품질을 확보하세요.
오케스트레이터와 구현 에이전트의 역할 분리 설계라면 70B 급 모델로도 충분히
운용 가능합니다.

향후 Claude Code 가 `ANTHROPIC_OPUS_BASE_URL` 같은 모델별 엔드포인트 분할을
지원하게 되면 이 절을 갱신합니다.

## Continue (VSCode) 연동

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## 노드 자동 발견 — `.local` 호스트명 지원 (가정 내 LAN)

가정 내 LAN에서 여러 머신 (mac mini + Pi5 + Windows GPU 머신 등)을 운용하는
경우, `base_url`에 IP 주소 대신 `.local` 호스트명을 사용하면 **DHCP로
IP가 변경되어도 그대로 동작**합니다. yu_ai_manager 측에 추가 구현은 불필요하며,
`httpx`가 OS의 resolver (Bonjour / Avahi / mDNSResponder)를 경유하여
자동으로 이름을 해석합니다.

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

샘플: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### 동작 요건

| OS | 필요 사항 |
|---|---|
| macOS | Bonjour (기본 동작, 추가 설치 불필요) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 이후 OS 기본으로 `.local` 해석 가능. 동작하지 않는 경우 Bonjour Print Services 설치) |

### 동작 확인

```bash
# 해석 가능 여부 테스트
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → 192.168.x.x 가 반환되면 OK
```

### 서브넷 간 / 기업 LAN / VPN 경유

mDNS는 L2 멀티캐스트로 동작하므로 **라우터 경유 / VPN 경유 /
기업 네트워크의 분리 VLAN에서는 도달하지 않습니다**. 이러한 환경에서는 기존대로
IP 주소를 직접 지정하세요:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

VLAN 분할 환경 등에서 mDNS reflector가 필요한 경우 LAN 관리자에게 문의하세요.
yu_ai_manager 측에서는 mDNS reflector / 프록시를 제공하지 않습니다.

### 알려진 제약

- **Windows의 mDNS 해석이 간혹 느림** (~1초): 백엔드 `timeout`을
  3초 이상으로 설정 권장
- **`.local` 접미사 필수**: `mac-mini` 단독으로는 NetBIOS / DNS 폴백이
  되므로 반드시 `mac-mini.local`로 작성
- **Ollama 자체는 mDNS advertise를 하지 않음**: 호스트명 해석만 가능하며, 포트
  (11434)는 수동 지정 필요. Ollama 측에서 advertise를 지원하면 완전 자동화될 예정
  (TODO.md mDNS Phase B/C 참조)

## 환경 변수

| 변수명 | 동작 |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | `1`로 Router 전체를 비활성화 |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | `1`로 5분 refresh 루프를 비활성화 |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | `none`/`loopback`/`api_key`를 오버라이드 |

## 다국어 문서

CLAUDE.md의 `docs/ 읽기 규칙`에 따라 `en/zh-tw/zh-cn/ko` 버전을
`ja/`를 기반으로 동기화합니다 (구현 후 별도 태스크; TODO.md 참조).

## 노드 자동 발견 (Phase B — v4.64.0 이후)

동일 LAN 상의 yu_ai_manager 노드는 mDNS (`_yu-ai._tcp.local.`)로 서로를 자동 발견합니다. `config.json`에 수동으로 백엔드를 작성하지 않아도 발견된 노드는 `mdns-<prefix>` alias로 `BackendCatalog`에 자동 등록됩니다.

### 구조

1. 시작 시 `core/mdns/`가 `_yu-ai._tcp.local.`을 advertise
2. 다른 노드의 TXT record를 구독하고, 필수 키 (version/node_id/llm_base_url)가 갖추어져 있는지 확인
3. 메이저 버전이 일치하는 노드에 대해 `http://<addr>:<web_port>/api/mdns/identity`에 HTTP GET하여 product/node_id/version 일치를 확인
4. 확인을 통과한 노드를 `BackendInfo(alias="mdns-<node_id[:8]>")`로 LLM Router에 등록
5. 이후 기존 probe loop이 정기 리프레시

### 전제 조건

- OS의 mDNS responder가 동작 중일 것 (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- 노드가 동일 L2 서브넷에 속해 있을 것 (라우터 경유 / VPN 경유에서는 Phase A의 수동 config 사용)
- UDP 5353이 로컬 방화벽에서 허용되어 있을 것
- **Ollama를 LAN에 공개할 것** — Ollama는 기본적으로 `127.0.0.1:11434`에 bind하므로 LAN의 다른 노드에서 도달할 수 없습니다. `OLLAMA_HOST=0.0.0.0:11434`를 환경 변수에 설정한 후 Ollama를 시작하세요 (macOS는 `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux는 systemd unit / `.bashrc`, Windows는 시스템 환경 변수). 설정되지 않은 경우 yu_ai_manager는 localhost only로 판단하여 `llm_base_url`을 advertise하지 않습니다 (시작 로그에 경고 출력)

### Ollama 자동 감지

`config.json`의 `llm_router.backends`에 localhost 항목이 없는 경우, yu_ai_manager는 시작 시 다음 순서로 Ollama를 탐색합니다:

1. `http://<LAN_IP>:11434/api/tags` — LAN에서 도달 가능한 Ollama
2. `http://localhost:11434/api/tags` — 감지되어도 LAN advertise는 하지 않음 (위의 경고 출력)

LAN IP에서 200이 반환되면 자동으로 `llm_base_url`로 TXT record에 게시합니다. 설정 없이 Ollama 동거 노드를 mDNS에 참여시키는 용도를 상정하고 있습니다. 비기본 포트 (11435 등)나 lmstudio / llamacpp는 계속 `config.json`에 명시가 필요합니다.

### `yu` 비동거 pure bare Ollama 노드의 취급 (방침)

`yu_ai_manager`가 실행되지 않는 pure bare Ollama 노드 (예: 가족의 mac에
Ollama만 설치되어 있거나 NAS의 Ollama 컨테이너 등)는 **자동 발견의 대상이
아닙니다**. `Ollama` 본체가 공식적으로 `_ollama._tcp.local.`을 advertise하는
기능이 없기 때문에 구조적으로 검출할 수단이 없습니다.

이러한 노드를 LLM Router에서 사용하려면 다음 중 하나로 **수동 설정**하세요:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- 환경에서 `.local` 호스트명을 사용할 수 있으면 (위의 "노드 자동 발견 — `.local` 호스트명 지원" 참조) 이를 권장
- 그렇지 않으면 고정 IP를 직접 기재

#### 자동 발견을 채택하지 않는 이유

설계 검토 시점 (2026-04-11)에 다음 3가지 안을 비교하여 (c) 수동 설정 안내를 선택했습니다:

| 안 | 내용 | 채택 여부 |
|---|---|---|
| (a) 시작 시 LAN 전체 `:11434` 스캔 | 시작 시 서브넷 내 호스트를 전수 probe | **미채택** — 네트워크 부하가 크고, 기업 / 다호스트 LAN에서 민폐가 되며, 포트 스캔으로 오인될 우려가 있고 edge-first 철학에 반함 |
| (b) 외부 Ollama 광고 daemon 상주 | 각 Ollama 호스트에 yu가 제공하는 경량 advertiser를 별도 상주 | **미채택** — 추가 상주 프로세스를 요구하는 것은 `yu_ai_manager` 본체를 설치하는 것과 동등한 부담. pure bare의 장점이 사라짐 |
| (c) 고정 IP / `.local` / 수동 backend 설정 안내 | `config.json`에 수기 작성 | **채택** — 추가 구현 제로, 동작이 명시적, 사용자가 의도치 않은 스캔에 말려들지 않음 |

향후 Ollama 본체가 `_ollama._tcp.local.`을 공식 advertise하거나 공식
service discovery 메커니즘을 추가한 경우, 그 시점에서 Phase D로 자동 발견
레이어를 재검토합니다.

### 비활성화

불필요한 네트워크 (Docker 격리, 기업 LAN, CI 등)에서는 비활성화할 수 있습니다:

- `config.json`에 `"mdns": {"enabled": false}` 추가
- 또는 환경 변수 `YU_AI_MDNS_DISABLED=1` 설정

### 알려진 동작

- **멀티홈 환경 (Wi-Fi + 유선)**: 기본값 (`bind_address: null`)에서는 양쪽 인터페이스에서 advertise되며, `PeerInfo.addresses`에 복수 IP가 포함됩니다. 단일 인터페이스로 제한하려면 `"bind_address": "192.168.x.y"`를 지정합니다.
- **alias 충돌**: `config.json`의 backend에서 alias를 `mdns-xxxxxxxx` 형식으로 지정한 경우, 수동 config가 우선되고 mDNS 발견분은 건너뜁니다.
- **서브넷 간**: mDNS는 기본적으로 L2 브로드캐스트 도메인 내에서만 동작합니다. 경계를 넘는 운용에는 Phase A의 `.local` 호스트명 지정을 사용하세요.
- **보안**: mDNS 자체에는 인증이 없습니다. 가정 내 LAN과 같은 신뢰할 수 있는 환경을 상정하고 있습니다. 공용 Wi-Fi나 다수 사용자 LAN에서는 비활성화를 권장합니다. `/api/mdns/identity` 검증으로 우발적인 오인식 노드나 호환되지 않는 구버전의 혼입은 방지됩니다.
