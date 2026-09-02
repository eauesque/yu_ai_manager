# 분산 추론 설정 가이드

> 대상 버전: v4.67.0 이상

## 분산 추론이란?

여러 yu_ai_manager 노드가 협력하여 태그 지정, CLIP, YOLO 및 음성 인식과 같은 추론 처리를 **병렬로 분산**하는 기능입니다. 대용량 파일 스캔을 여러 머신에서 공유하거나 Hailo NPU가 탑재된 Pi5에 태그 지정을 위임할 수 있습니다.

```
┌──────────────┐   이미지 배치   ┌──────────────┐
│   로컬       │ ──────────────► │  Pi5 (Hailo) │  tagger × 200 이미지
│   (스캔)     │ ──────────────► │  GPU 머신    │  tagger × 300 이미지
│              │ ──────────────► │    로컬      │  tagger × 100 이미지
└──────────────┘   작업          └──────────────┘
                  공유
```

---

## 필수 조건

각 노드에서 다음 조건이 충족되어야 합니다:

1. yu_ai_manager가 실행 중
2. **LAN Cowork 확장이 활성화됨** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. 노드들이 **서로 페어링됨** ([피어 인증 가이드](../lan-cowork/peer-auth.md))
4. 사용할 추론 엔진이 각 노드에 설정됨 (ONNX / Hailo / Whisper 등)

---

## 설정 단계

### 단계 1: 각 노드에서 LAN Cowork 활성화

모든 노드의 `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

재시작 후 노드들이 mDNS를 통해 자동으로 서로를 발견합니다.

### 단계 2: 페어링 완료

모든 노드 쌍 간에 페어링을 수행합니다(양방향).
상세: [피어 PIN 인증 및 토큰 페어링](../lan-cowork/peer-auth.md)

### 단계 3: 분산 추론 매트릭스 확인

모든 노드에서 `/mesh-inference`를 엽니다.

페어링된 노드는 행으로, 추론 유형은 열로 표시됩니다:

| 노드 | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| 로컬 | ☑ 활성화 | ☑ 활성화 | ☑ 활성화 | ☑ 활성화 |
| pi5-hailo | ☑ 활성화 | ☑ 활성화 | — 사용 불가 | — 사용 불가 |
| gpu-win | ☑ 활성화 | ☑ 활성화 | ☑ 활성화 | ☑ 활성화 |

- **☑ 활성화**: 이 노드를 추론에 사용
- **☐ 비활성화**: 건너뛰기 (수동으로 전환 가능)
- **—**: 이 노드가 대상 추론 엔진을 지원하지 않음 (작동 불가)

### 단계 4: 작동 확인

태그 지정 배치를 실행하고 로그에 여러 노드가 사용되는지 확인합니다:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## 추론 유형별 요구사항

| 유형 | 필수 엔진 | 설명 |
|---|---|---|
| `tagger` | ONNX (WD14 등) 또는 Hailo NPU | 이미지에 대한 Danbooru 스타일 태그 지정 |
| `clip` | ONNX CLIP 또는 Hailo | 이미지에 대한 의미론적 임베딩 벡터(의미 검색용) |
| `yolo` | ONNX YOLO | 이미지의 객체 감지 |
| `whisper` | faster-whisper 또는 원격 | 오디오/비디오에 대한 음성 텍스트 변환 |

구성된 엔진이 없는 노드는 해당 유형에 대해 "—"가 표시되고 해당 유형으로 라우팅되지 않습니다.

---

## 역할 설계 예시

### 예시 1: Pi5 + Hailo NPU를 태그 지정 전용으로 사용

Pi5를 태그 지정용으로만 할당하여 다른 노드의 부하를 줄입니다.

매트릭스 구성:
- Pi5: tagger ☑, 기타 ☐
- 로컬: clip ☑, yolo ☑, whisper ☑, tagger ☐ (Pi5에 위임)

### 예시 2: 고속 대량 스캔

GPU 머신과 로컬 머신 모두에서 tagger를 활성화하여 작업 공유를 통해 파일을 자동으로 분담합니다. 수동 분할이 필요 없습니다.

### 예시 3: 로컬 전용 모드 (임시)

`/mesh-inference`의 "로컬 전용 모드" 버튼을 클릭하여 모든 원격 피어를 한 번에 비활성화합니다. 네트워크 단절 시 유용합니다.

---

## 문제 해결

### 피어가 매트릭스에 표시되지 않음

1. `/api/lan/peers`로 피어가 인식되는지 확인
2. 페어링이 완료되었는지 확인 ([peer-auth.md](../lan-cowork/peer-auth.md))
3. 원격 노드에서 LAN Cowork이 활성화되었는지 확인

### 특정 노드로의 라우팅이 작동하지 않음

- 매트릭스에서 해당 노드의 대상 유형이 ☑으로 표시되는지 확인
- `/api/lan/peers` 응답에서 해당 노드에 대해 `status: "online"`이 표시되는지 확인
- 원격 노드의 하트비트가 수신되는지 확인 (로그에서 `heartbeat` 검색)

### 모든 처리가 로컬에서 수행됨

모든 원격 피어가 오프라인이거나 비활성화된 경우 자동 로컬 폴백이 발생합니다.
이것은 정상적인 작동입니다 (오류가 아닙니다).

### `no_enabled_peers` 오류

해당 유형이 모든 노드에서 비활성화되었습니다.
매트릭스에서 해당 유형에 대해 최소 1개 노드를 활성화하세요.

---

## 관련 문서

- [분산 추론 아키텍처](overview.md) — 작업 공유 및 DisableAwareStrategy 내부 설계
- [분산 추론 매트릭스](toggle.md) — WebUI 작동 세부사항
- [LAN Cowork 개요](../lan-cowork/README.md) — LAN Cowork 전체 구성
- [피어 PIN 인증](../lan-cowork/peer-auth.md) — 페어링 절차
