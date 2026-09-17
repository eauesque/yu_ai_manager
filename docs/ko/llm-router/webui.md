# LLM Router WebUI

`/llm-router`에서 열리는 관리 대시보드. 등록된 백엔드의 상태 확인 및 비활성화/활성화를 수행할 수 있습니다.

---

## 화면 구성

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← 요약 카드
├─────────┴─────────┴────────┴─────────┤
│  Backends 테이블                     │
├───────────────────────────────────────┤
│  Routing Aliases 테이블              │
└───────────────────────────────────────┘
```

### 요약 카드 (4개)

| 카드 | 내용 |
|---|---|
| **Backends** | 카탈로그에 등록된 백엔드 총수 |
| **Enabled** | 비활성화(disabled)되지 않은 백엔드 수 |
| **Models** | 전체 백엔드가 공개하는 모델의 합계 수 |
| **Routing aliases** | 설정 파일에 정의된 에일리어스 수 |

카드 값은 페이지 로드 시 `/api/llm_router/status`를 가져와 자동 렌더링됩니다.

---

## 백엔드 목록 테이블

각 행이 하나의 물리 백엔드 (Ollama 인스턴스 등)에 대응합니다.

### 열의 의미

| 열 | 설명 |
|---|---|
| **Alias** | 백엔드를 식별하는 고유 단축명 (예: `ollama-mac`, `mdns-pi5-hailo`). 라우팅 설정 및 에일리어스 해석의 키 |
| **Base URL** | 백엔드의 OpenAI 호환 엔드포인트 베이스 URL (예: `http://192.168.1.10:11434`) |
| **Status** | 백엔드 연결 상태. 상세는 후술 |
| **SLO** | 백엔드의 리소스 부하 상태 (`vision_idle` / `vision_active` / `unknown`). Hailo Vision 계열 백엔드에서 사용 |
| **Models** | 마지막 프로브에서 가져온 모델 수. 클릭하면 상세 목록을 펼칠 수 있는 구현 의존 경우 있음 |
| **Last Seen** | 마지막으로 정상 응답을 확인한 일시 (ISO 8601). `null`인 경우 한 번도 성공하지 못한 상태 |
| **Actions** | 개별 조작 버튼 (후술) |

### Status 해석

| 값 | 의미 |
|---|---|
| `ready` | 직전 프로브가 성공하고 모델 목록을 취득 완료 |
| `unreachable` | 연결 타임아웃 또는 에러 발생 |
| `unknown` | 아직 프로브를 실행하지 않은 상태 (시작 직후 등) |
| `probing` | 프로브 실행 중 (UI가 Refresh 중에 잠시 표시될 수 있음) |

> **힌트**: `unreachable` 백엔드는 라우팅 대상에서 제외되지만, 카탈로그에는 남아 있습니다. 네트워크 복구 후 Refresh All 또는 개별 Refresh를 실행하면 `ready`로 돌아옵니다.

### SLO 해석

| 값 | 의미 |
|---|---|
| `vision_idle` | Vision 태스크 아이들 상태. LLM 부하 낮음 |
| `vision_active` | Vision 태스크 동작 중. LLM 라우터가 다른 백엔드를 우선할 수 있음 |
| `unknown` | SLO 정보를 가져올 수 없음 (비 Hailo 백엔드 또는 취득 실패) |

---

## Refresh All 버튼

화면 우상단의 **Refresh All**을 클릭하면 전체 백엔드에 대해 강제 프로브를 실행하고 모델 목록 및 상태를 갱신합니다.

- 실행 중에는 버튼이 비활성화되며, 완료 후 다시 렌더링됨
- 내부 동작: `POST /api/llm_router/refresh` (본문 없음)를 호출하여 전체 백엔드의 `discover_all`을 실행
- 개별 백엔드의 Refresh는 Actions 열의 Refresh 버튼 (구현에 따라 존재)에서 실행 가능한 경우 있음

---

## 개별 백엔드의 disable / enable

### 조작 순서

1. 백엔드 목록 테이블의 **Actions** 열을 확인
2. 비활성화할 백엔드 행에서 **Disable** 버튼을 클릭
3. 버튼이 **Enable**으로 바뀌고, 행이 그레이 아웃됨
4. 다시 활성화하려면 **Enable**을 클릭

### 동작과 영구화

- 조작은 즉시 인메모리 카탈로그에 반영됨
- 동시에 `data/llm_router_state.json`에 아토믹 기록됨

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- 앱을 재시작해도 비활성화 상태는 유지됨
- mDNS로 동적 발견되는 백엔드가 시작 전에 비활성화되어 있었던 경우에도, 발견 후 자동 적용됨 (`_pending_disabled` 메커니즘)
- 기록 실패 시 인메모리 상태가 롤백되어, 디스크와 불일치가 발생하지 않음

### disabled 백엔드의 동작

- `/v1/chat/completions` 등의 OpenAI 호환 엔드포인트에서 라우팅 대상에서 제외됨
- disabled 백엔드에 직접 라우팅하려 하면 `503 Service Unavailable`이 반환됨
- WebUI 테이블에는 계속 표시됨 (상태 파악 및 재활성화를 위해)

---

## Routing Aliases 테이블

설정 파일에서 정의한 논리 모델명과 물리 모델 ID의 매핑을 표시합니다.

| 열 | 설명 |
|---|---|
| **Alias** | 클라이언트가 `model` 파라미터로 지정하는 논리명 (예: `default-llm`, `fast-chat`) |
| **Physical Model** | 실제로 요청을 처리하는 물리 모델 ID (형식: `백엔드alias/모델명`, 예: `ollama-mac/qwen2.5:7b`) |

### 에일리어스의 역할

에일리어스를 사용하면 클라이언트 코드를 변경하지 않고 백엔드나 사용 모델을 전환할 수 있습니다.

- 클라이언트는 `"model": "default-llm"`처럼 논리명으로 요청
- LLM Router가 `default-llm → ollama-mac/qwen2.5:7b`로 해석하여 프록시
- 백엔드를 다른 머신으로 이전하는 경우 에일리어스의 목적지만 변경하면 됨

에일리어스는 설정 파일에서 정적으로 정의되며, WebUI는 읽기 전용으로 표시합니다. 변경에는 설정 파일 편집과 앱 재시작이 필요합니다.

---

## 자주 하는 작업

### 백엔드가 unreachable일 때

1. 백엔드 서비스 (Ollama 등)가 시작되어 있는지 확인
2. **Refresh All** 또는 개별 Refresh를 실행
3. 그래도 해결되지 않으면 `last_error` 열 (또는 API 응답)에서 에러 내용을 확인

### mDNS로 자동 발견된 백엔드를 영구적으로 비활성화하고 싶을 때

1. 대상 백엔드의 Actions 열에서 **Disable**을 클릭
2. `data/llm_router_state.json`에 alias가 저장되므로, 재발견 후에도 비활성화 상태 유지

### 일시적으로 특정 백엔드의 부하를 중단하고 싶을 때

**Disable**로 즉시 제외 → 작업 완료 후 **Enable**로 복귀. 재시작 불필요.
