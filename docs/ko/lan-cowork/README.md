# LAN Cowork

> 대상 버전: v4.55.0 이상 (PIN 인증은 v4.92.0 이상)

## LAN Cowork란?

LAN Cowork는 네트워크상의 여러 yu_ai_manager 노드를 조화시키는 확장 기능입니다.  
각 머신이 독립적으로 작동하면서 무거운 처리 작업을 분산하거나 Fleet으로 일괄 관리할 수 있습니다.

```
┌──────────────┐     mDNS 디스커버리  ┌──────────────┐
│  Windows PC  │◄────────────────────►│   Mac Mini   │
│ (GPU 탑재)   │   PIN 페어링        │ (제어)       │
│              │◄────────────────────►│              │
│  분산 추론   │                     │  Fleet 관리  │
│ (tagger 등)  │                     │              │
└──────────────┘                     └──────────────┘
        ▲                                   ▲
        └───────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## 기능 목록

| 기능 | 설명 |
|---|---|
| **mDNS 자동 디스커버리** | 동일 LAN상의 노드를 설정 없이 자동 발견 |
| **PIN 페어링** | 관리자 승인 PIN 인증으로 피어 간 토큰 발급 |
| **분산 추론** | 여러 노드에서 tagger, CLIP, YOLO, Whisper 병렬 처리 |
| **생성 분산** | SD WebUI / ComfyUI 작업을 LAN 노드로 위임 |
| **Fleet 관리** | 중앙 노드에서 로그 조회 및 버전 업데이트 일괄 관리 |
| **피어 이벤트 릴레이** | 다른 노드의 이벤트를 자신의 SSE로 스트림 |
| **LLM 라우팅** | 발견된 피어를 LLM Router에 자동 등록 |

---

## 설정 단계

### 1. 활성화

`config.json`에 추가:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **참고**: 이 페이지에서는 이전에 활성화 키를 최상위 `{"lan_cowork": {...}}`로 안내했지만, 어떤 구현도 그 위치의 키를 읽지 않습니다. 위의 `extensions` 섹션이 올바른 위치입니다.

> **기본값은 백엔드에 따라 다릅니다:** Python 백엔드(hybrid)는 키가 없으면 **활성화됨**으로 처리하지만, Rust standalone 서버는 명시적으로 활성화하지 않으면 **비활성화됨**입니다. 활성화 후 네트워크에서 실제로 어떤 일이 일어나는지는 [네트워크 동작](network-behavior.md)을 참조하세요.

재시작 후:
- UDP 19850에서 다른 노드 발견 수신 대기
- mDNS를 통해 _yu-ai._tcp.local. 광고 시작

### 2. 노드 페어링

노드 A에서 노드 B로 연결하려면:

1. **노드 A WebUI** → `설정` → `LAN Cowork` → 노드 B URL 추가
2. 노드 A가 `POST /api/lan/pair/request` 전송
3. **노드 B WebUI** → `/lan-cowork/peers` → "승인 대기 중" 탭에서 승인
4. 6자리 PIN이 노드 A로 전송됨 (SSE 경유)
5. 노드 A가 PIN 입력 → Bearer 토큰 획득 (30일 유효)

> **주의**: 페어링은 단방향입니다. A→B와 B→A를 모두 실행하세요.

[피어 PIN 인증 및 토큰 페어링](peer-auth.md)을 참조하세요.

### 3. 동작 확인

```bash
# 발견된 피어 목록 (노드 A에서)
curl http://localhost:5000/api/mdns/peers

# LAN Cowork에서 인식된 피어
curl http://localhost:5000/api/lan/peers
```

---

## 기능별 설정

### 분산 추론

페어링 완료 후 분산 추론이 자동으로 사용 가능해집니다.

- `설정` → `LAN Cowork` → 각 노드의 추론 유형 (tagger/CLIP/YOLO/Whisper) 활성화
- 또는 `/mesh-inference` 페이지의 매트릭스에서 개별 설정

상세: [분산 추론 설정](../mesh-inference/setup.md)

### Fleet 관리

다른 노드를 관리할 "Chief" 노드 설정:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

상세: [Fleet 관리](../features/fleet-admin.md)

### 생성 분산 (SD / ComfyUI 작업 위임)

생성 작업을 GPU 탑재 노드에 자동 분배합니다. 설정 파일 백엔드 등록 또는 mDNS 자동 디스커버리를 통해 이용 가능합니다.  
노드 B에서 SD WebUI / ComfyUI가 실행 중이면 설정 후 즉시 이용 가능합니다.

---

## 네트워크 요구사항

| 포트 / 프로토콜 | 용도 | 필수 |
|---|---|---|
| UDP 5353 | mDNS (노드 디스커버리) | 동일 L2 LAN만 |
| UDP 19850 | LAN Cowork 디스커버리 | 동일 L2 LAN만 |
| TCP 5000 (기본값) | API, 페어링, 추론 | 피어 간 |

- mDNS는 라우터나 VPN을 넘어 작동하지 않음 (고정 IP 또는 `.local` 호스트명 사용)
- 방화벽에서 UDP 5353과 TCP 5000이 LAN에서 열려 있는지 확인

---

## 문서 목록

| 문서 | 내용 |
|---|---|
| [피어 PIN 인증](peer-auth.md) | 페어링 플로우, 토큰 관리, 보안 설정 |
| [분산 추론 설정](../mesh-inference/setup.md) | 여러 노드에서 추론 병렬화 단계 |
| [분산 추론 매트릭스](../mesh-inference/toggle.md) | WebUI에서 피어별, 유형별 활성화/비활성화 |
| [분산 추론 아키텍처](../mesh-inference/overview.md) | 내부 설계, 작업 탈취, 지속성 |
| [Fleet 관리](../features/fleet-admin.md) | 원격 로그 및 버전 업데이트 중앙 관리 |
| [mDNS 피어 API](../api/mdns-peers.md) | `/api/mdns/*` 엔드포인트 상세 |

---

## 보안

- mDNS는 인증이 없습니다. **가정용 LAN 또는 신뢰할 수 있는 네트워크만 사용**
- 공용 Wi-Fi 또는 공유 LAN에서는 `"mdns": {"enabled": false}`로 비활성화
- 피어 간 통신은 PIN 페어링의 Bearer 토큰 (scrypt 해시로 저장)으로 보호됨
- `ip_check_mode: strict`는 토큰이 발급된 IP만 허용 (기본값)
