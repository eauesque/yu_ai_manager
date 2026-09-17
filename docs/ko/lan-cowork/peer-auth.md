# 피어 PIN 인증 및 토큰 페어링

**구현 버전**: 4.92.0
**관련 파일**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## 개요

v4.92 이전에는 LAN의 피어 간 통신에서 `X-Peer-Id` 헤더만으로 상대방을 식별했습니다.
이 헤더는 같은 네트워크의 누구든 위조할 수 있어 보안이 취약했습니다.

v4.92부터 **PIN 승인 기반 토큰 페어링** 방식으로 전환했습니다.

- 최초 연결 시 "페어링 요청"을 전송
- 상대방 관리자가 관리 화면에서 승인하면 6자리 PIN 발급 (유효 5분)
- PIN을 입력하면 Bearer 토큰 발급 (유효 30일)
- 이후 통신은 `Authorization: Bearer <token>`으로 인증

기존 `X-Peer-Id` 헤더 방식은 설정을 통해 호환성을 유지할 수 있지만, DELETE 작업은 항상 새 인증 방식이 필요합니다.

---

## 페어링 흐름

```
[피어 A (요청측)]                      [피어 B (대상측)]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                           관리자가 /lan-cowork/peers에서 확인 및 승인
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (6자리 PIN, 유효 5분)               |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer 토큰, 유효 30일)             |
       |                                      |
       |--- 이후: Authorization: Bearer <token>
```

### 각 단계 설명

| 단계 | 엔드포인트 | 설명 |
|------|-----------|------|
| 1. 요청 전송 | `POST /api/lan/pair/request` | 피어 ID, 표시 이름, 공개 키 전송 |
| 2. 승인 대기 | — | 관리자가 `/lan-cowork/peers`에서 요청 확인 |
| 3. PIN 발급 | — | 관리자가 승인 버튼을 누르면 6자리 PIN 생성 (유효 5분) |
| 4. PIN 검증 | `POST /api/lan/pair/verify` | PIN 제출 후 Bearer 토큰 수령 |
| 5. 인증된 통신 | — | `Authorization: Bearer <token>` 헤더 첨부 |

---

## 관리 화면 (`/lan-cowork/peers`)

### 승인 대기 요청

새 피어가 페어링 요청을 보내면 관리 화면의 "승인 대기" 탭에 표시됩니다.

- **승인**: PIN을 생성하고 SSE를 통해 요청 측 피어에 알림
- **거부**: 요청을 삭제합니다. 요청 측 피어는 403을 수신

### 연결된 피어 목록

페어링된 모든 피어와 각 토큰의 만료일을 목록으로 표시합니다.

| 열 | 내용 |
|----|------|
| 표시 이름 | 피어 이름 |
| IP 주소 | 마지막으로 확인된 소스 IP |
| 만료일 | Bearer 토큰 만료일 (30일) |
| 최근 연결 | 마지막 하트비트 타임스탬프 |
| 작업 | 토큰 만료 버튼 |

### 토큰 폐기

"폐기" 버튼을 클릭하면 대상 피어의 Bearer 토큰이 즉시 무효화됩니다.
다음 통신 시도 시 피어는 401을 수신하고 자동으로 재페어링을 시도합니다.

---

## 설정 항목

설정은 `config.json`의 `lan_cowork` 섹션이나 설정 화면의 "LAN 협업" 탭에서 변경할 수 있습니다.

### `ip_check_mode`

소스 IP 주소 검증 방식을 지정합니다.

| 값 | 동작 |
|----|------|
| `strict` | 토큰 발급 시 IP와 완전히 일치하는 경우만 허용 (기본값) |
| `cidr` | `allowed_cidr`로 지정한 CIDR 범위 내 IP 허용 |
| `rfc1918` | 모든 사설 IP 주소 허용 (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

기존 `X-Peer-Id` 헤더 인증과의 호환성을 유지할지 지정합니다.

- `true`: `X-Peer-Id` 헤더만으로도 일부 작업 허용 (기본값: `true`)
- `false`: Bearer 토큰 없는 연결을 모두 거부

> **주의**: `DELETE` 메서드를 사용하는 작업 (스캔 중지, 강제 삭제 등)은 `allow_legacy_auth` 설정에 관계없이 항상 Bearer 토큰이 필요합니다.

### `protect_heartbeat`

하트비트 엔드포인트 (`/api/lan/heartbeat`)에도 인증을 요구할지 지정합니다.

- `true`: 하트비트에도 Bearer 토큰 필요
- `false`: 하트비트는 인증 없이 통과 (기본값: `false`)

하트비트는 자주 전송되므로 `false`로 설정하면 토큰 만료 감지 지연을 방지할 수 있습니다.

### `protect_events`

SSE 이벤트 스트림 (`/api/events/`)에도 인증을 요구할지 지정합니다.

- `true`: SSE 연결에도 Bearer 토큰 필요
- `false`: SSE는 인증 없이 통과 (기본값: `false`)

---

## 보안 참고 사항

### 토큰 해싱

발급된 Bearer 토큰은 데이터베이스에 **평문으로 저장되지 않습니다**.
scrypt (N=16384, r=8, p=1)로 해싱된 후 저장됩니다.
DB가 유출되더라도 원본 토큰을 복원할 수 없습니다.

### 로그 마스킹

- `Authorization: Bearer <token>` 헤더는 로그 출력 시 자동으로 `Bearer [REDACTED]`로 대체됩니다
- PIN 코드도 로그에 남지 않습니다

### 속도 제한

DoS 공격 및 무차별 대입을 방지하기 위해 다음 속도 제한이 적용됩니다:

| 엔드포인트 | 제한 |
|-----------|------|
| `POST /api/lan/pair/request` | 10건/분/IP |
| `POST /api/lan/pair/verify` | 30건/분/IP |

PIN은 5분 후 자동 만료되며, 하나의 요청에 대해 한 번만 검증할 수 있습니다.

---

## 문제 해결

### 페어링 요청이 수신되지 않음

- 원격 피어의 URL이 올바르게 설정되었는지 확인하세요
- 방화벽에서 포트가 차단되지 않았는지 확인하세요
- 원격 피어의 로그에서 `pair/request` 수신 상태를 확인하세요

### PIN이 만료됨

PIN 유효 기간은 5분입니다. 만료된 경우 관리 화면에서 "승인" 버튼을 다시 클릭하면 새 PIN이 발급됩니다.

### 토큰이 갑자기 사용 불가능해짐

가능한 원인:

1. 관리자가 관리 화면에서 토큰을 폐기했음
2. 30일 유효 기간이 만료됨
3. `ip_check_mode: strict` 설정에서 IP 주소가 변경됨

재페어링을 실행하세요.

### `allow_legacy_auth`를 `false`로 설정 후 연결 불가

기존 피어가 여전히 구 인증 방식을 사용 중이라면 모두 401을 수신합니다.
`allow_legacy_auth: false`로 변경하기 전에 각 피어에서 재페어링을 완료하세요.
