# 테스트 유지보수 플레이북

오래된 테스트 기반 또는 환경 의존성으로 인해 pytest가 멈출 때 가장 먼저 확인해야 할 요점들을 정리한 가이드.

## 목적

- `failed`와 `skipped`를 구분하기
- 정상적인 환경 의존성 skip과 수리해야 할 오래된 테스트를 구별하기
- broad run (`pytest tests -q --maxfail=1`)이 멈출 때의 최단 경로 확립

## 기본 명령어

정상적인 전체 확인:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

skip 이유도 확인:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

shared test server를 엄격하게 처리:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

라이선스 감시:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## 현재 skip 읽는 방법

2026-04-21 시점의 broad run에서 skip의 주된 원인은 다음 5가지 계열로 치우쳐 있습니다.

### 1. Shared Test Server 미시작

가장 많은 skip. `tests/conftest.py`의 shared server는 최선을 다해 시작하는 방식이며, 시작에 실패하면 브라우저/서버 의존 그룹이 fail이 아닌 skip으로 낮춰집니다.

대표적인 이유:

- `Shared test server unavailable on port <PORT>`

주요 대상:

- `tests/api/`
- 브라우저 UX 리뷰 계열
- LAN Cowork / Fleet 브라우저/서버 의존 테스트
- `TARGET_URL` / `BASE` / `TARGET`을 사용하는 live browser test
- `page` fixture가 아닌 커스텀 Playwright/WebKit fixture를 사용하는 감시 계열 테스트

정상 실행에서는 **정상적인 skip**입니다. 다만 다음의 경우 조사 필요:

- shared server와 무관한 unit test까지 같은 이유로 skip되는 경우
- 이전에 통과하던 shared server 계열이 갑자기 대량 skip화하는 경우
- `PYTEST_STRICT_AUTOSTART_SERVER=1`로도 원인이 보이지 않는 경우

### 2. OS 고유 테스트

Linux 전용 sandbox / AppArmor / process isolation 계열. Windows에서는 skip이 올바릅니다.

대표 사례:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

대표적인 이유:

- `Linux only`
- `AppArmor is Linux-specific`

이는 **정상적인 skip**입니다.

### 3. 선택적 의존성, 외부 컴포넌트 부재

특정 패키지나 외부 노드가 없는 환경에서는 실행되지 않는 테스트 그룹.

대표 사례:

- mDNS 실기 E2E: `optional zeroconf package is not installed`
- 브라우저 시작: `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / 외부 추론 노드 미연결

이는 **정상적인 skip**입니다. 수리 대상이 아니라 선행 환경이 갖춰지지 않았을 뿐입니다.

### 4. 테스트 데이터 부족

이미지, 검색 결과, 대화 로그, 다중 데이터 등이 필요한 브라우저 테스트로서 경량 DB에서는 성립 불가능하므로 skip됩니다.

대표적인 이유:

- `No search results available in database`
- `DB에 이미지가 없어 skip`
- `2개 이상의 파일 필요`
- `No prompts to test copy`

이는 **대체로 정상적인 skip**입니다. 다만 fixture가 필수 데이터를 제공해야 하는 테스트라면 낡음을 의심해야 합니다.

### 5. 속도 제한, 외부 API 보호

일부 통합은 외부 서비스나 속도 제한을 존중하여 skip합니다.

대표적인 이유:

- `속도 제한에 도달하여 skip됨`

이는 **정상적인 skip**입니다.

### 6. 장시간 fuzz / burn-in

`tests/fuzz/` 하단의 burn-in은 일상적인 회귀 확인이 아닌 내구성 및 충돌 내성 추가 확인에 사용됩니다.

기본값으로 `pytest.ini`의 marker 식에 의해 제외됩니다.

실행하려면:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

필요한 경우:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

이는 **정상 broad run에 섞이지 않습니다**.

## 비정상으로 취급해야 할 패턴

다음 항목들은 「skip이니까 문제없다」고 치부하지 말고 테스트 유지보수 대상으로 봐야 합니다.

### A. 이전에 통과하던 경량 테스트가 setup skip으로 빠짐

예시:

- app/client fixture 기반으로만 완성되어야 할 API smoke가 shared server 전제에 말려든 경우
- migration / schema / DB helper의 unit test가 runtime global state 초기화 전제로 실패하는 경우

이 경우 test harness와 구현의 전제 어긋남을 의심하세요.

### B. broad run은 통과하는데 단독 실행에서만 실패

전형적인 경우:

- process-global state에 의존
- broad run 중 우연히 선행 테스트가 초기화한 부수 효과에 올라타 있음

단독 실행도 재현 가능한 상태로 돌려놓으세요.

### C. skip 이유가 모호함

나쁜 예:

- `failed`
- `not ready`
- `something wrong`

skip 이유는 「무엇이 부족해서 건너뛰었는가」를 단문으로 작성해야 합니다.

## 수리의 우선순위

1. broad run을 멈추게 하는 hard failure 수리
2. 단독 실행에서만 깨지는 오래된 테스트 수리
3. 브라우저/서버 의존 skip을 fail이 아닌 안전한 skip으로 정향
4. 선택적 의존성이나 실기 의존은 optional skip 유지

## 이번 정비로 고정한 사항

- 브라우저/서버 의존을 shared server unavailable일 때 fail이 아닌 skip으로 통일
- 라이선스 감시는 전체 venv가 아닌 `requirements*.txt` 선언 의존만 봄
- test DB는 현재 검색 스키마의 path FTS 전제 충족
- migration 54 / 55는 스키마 진화나 runtime state 미초기화에 취약하지 않도록 수정

## 헷갈릴 때의 판단 기준

- 선행 환경이 없으면 → skip 괜찮음
- 현행 구현을 따라가지 못하는 낡은 기댓값 → 테스트 수리
- broad run의 부수 효과에 의존 → 구현이나 테스트 수리
- unit test가 process-global state 요구 → 설계 의심
