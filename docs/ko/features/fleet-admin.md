# Fleet 관리

LAN Cowork의 Fleet Admin 기능은 네트워크상의 여러 yu-ai-manager 노드를 중앙에서 관리하기 위한 기능입니다.

## 개요

- **머신 정보 수집**: 각 노드의 CPU / RAM / GPU / 디스크 / 버전 / 가동 시간을 중앙에 집계
- **원격 로그 조회**: 중앙 노드의 UI에서 임의 피어의 로그를 SSE로 라이브 스트리밍
- **버전 업데이트 배포**: 중앙에서 지정 피어에 `git pull --ff-only` + graceful restart 지시

## 전제 조건

- LAN Cowork 확장이 활성화되어 있을 것（`extensions["builtin-lan-cowork"].enabled = true`）
- 피어 간 페어링이 완료되어 있을 것
- git 저장소로 clone되어 있을 것（업데이트 기능 사용 시）
- Python 가상 환경에 `psutil>=5.9`가 설치되어 있을 것

## 설정

### 치프 노드 설정

`config.json`에 다음을 추가：

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<페어링된 peer_id>"
        ],
        "allow_log_stream_from": [
          "<페어링된 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### 일반 노드 설정

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<치프의 peer_id>"
        ],
        "allow_log_stream_from": [
          "<치프의 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Fleet UI 접근

치프 노드의 브라우저에서 `/ext/lan_cowork/fleet/ui`에 접근합니다.

일반 노드에서는 이 URL이 404를 반환합니다.

## 탭 기능

### 개요

- 전체 노드 카드 표시（CPU / RAM / GPU / 디스크 사용률 바 포함）
- 온라인 / 오프라인 / 정보 취득 실패 상태 표시
- 치프 노드에는 `[CHIEF]` 뱃지
- 30초마다 자동 갱신 + 수동 갱신 버튼
- 여러 치프 감지 시 경고 배너

### 로그

- 임의 피어의 로그를 SSE로 라이브 표시（tail -f 스타일）
- 레벨 필터（DEBUG / INFO / WARNING / ERROR）
- 검색 박스（클라이언트 측 필터）
- 자동 스크롤 ON/OFF
- 일시 정지 / 재개

### 업데이트

- 버전 / git commit / 브랜치 비교 표
- 개별 노드의 「Pull & Restart」 버튼
- 여러 노드 일괄 업데이트（dispatch）
- 진행 표시（precheck → fetching → pulling → restarting → online）
- 치프 자신은 일괄 업데이트에서 제외（개별 버튼만 사용）

## 보안

인가는 두 계층 구조를 사용합니다：

1. **페어링（신원 확인）**: Bearer token으로 호출자 신원 파악
2. **Allowlist（권한）**: 작업마다 명시적으로 peer_id 인가 필요

페어링 완료 = 전체 권한 부여가 아닙니다.

### Allowlist 설정 예시

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- 문자열과 `{peer_id: ...}` 형식 모두 사용 가능
- 자신의 peer_id는 자동으로 추가됩니다（설정 불필요）

## 치프 자동 강등

동일 네트워크에 `chief = true`인 노드가 여러 개 기동된 경우, 나중에 기동된 노드가 `chief_observation_sec`초 관찰 후 자동으로 강등됩니다.

강등 후 치프로 복귀하려면 설정 변경 후 재시작이 필요합니다（자동 승격 없음）.

## git 업데이트 제약

- `git pull --ff-only`만 사용합니다（merge/rebase 사용 안 함）
- fast-forward 불가능한 경우 즉시 `failed` 반환（워킹 트리는 변경되지 않음）
- 워킹 트리가 dirty한 경우 업데이트를 거부합니다

## 문제 해결

| 증상 | 원인 | 해결 방법 |
|---|---|---|
| `/fleet/ui`가 404 반환 | `chief = true` 미설정 | config.json 확인 후 재시작 |
| `/fleet/info`가 500 반환 | psutil 미설치 | `uv pip install psutil>=5.9` |
| `git_not_available` 오류 | git 없음 또는 PATH 오류 | git 설치 확인 |
| 업데이트 후 `postcheck_online` 타임아웃 | 재시작에 3분 이상 소요 | `postcheck_timeout_sec` 연장 |
| 여러 치프 감지 배너가 사라지지 않음 | 이전 치프 프로세스가 남아 있음 | 이전 치프 재시작 |

## API 참조

### 모든 노드 공통

| 엔드포인트 | 설명 |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | 머신 정보（Bearer 인증 필수） |
| `GET /ext/lan_cowork/fleet/logs/stream` | 자신의 로그 SSE（allowlist 인가） |
| `POST /ext/lan_cowork/fleet/update` | git pull + 재시작（allowlist 인가） |
| `GET /ext/lan_cowork/fleet/update/status` | 업데이트 작업 상태 조회 |

### 치프 노드 전용

| 엔드포인트 | 설명 |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | 전체 피어 정보 집계 |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | 지정 피어 로그 SSE 릴레이 |
| `POST /ext/lan_cowork/fleet/update/dispatch` | 여러 피어 일괄 업데이트 |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | dispatch 진행 조회 |
| `GET /ext/lan_cowork/fleet/ui` | Fleet 관리 UI |
