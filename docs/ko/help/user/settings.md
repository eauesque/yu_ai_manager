# 설정

## 서버 설정

| 항목 | 설명 |
|------|------|
| Host | 바인드 주소 (LAN OFF 시 127.0.0.1 고정) |
| Port | 웹 서버 포트 번호 |
| LAN Access | ON으로 설정하면 LAN 내 다른 기기에서 접속 가능 |
| PIN Auth | 접속 시 PIN 입력을 요구 |
| Boss Mode | 신문 스타일의 PIN 로그인 화면 |

## 스캔 설정

등록 폴더의 추가, 삭제, 정렬, 활성/비활성 전환을 관리합니다.

## 파서 설정

| 항목 | 설명 |
|------|------|
| Extract A1111 | Stable Diffusion WebUI 형식의 메타데이터를 추출 |
| Extract ComfyUI | ComfyUI 워크플로 메타데이터를 추출 |
| Normalize tags | 태그를 소문자로 통일 |
| Compute hash | 파일 해시 계산 (중복 탐지용) |
| FTS | 전문 검색 인덱스를 활성화 |

## API 키

외부 도구 (MCP 서버, 스크립트, 에이전트) 용 API 키를 관리합니다.
Bearer 인증으로 사용합니다.

## 외관

테마, 액센트 색상, 배경 이미지, 사운드 효과 등을 커스터마이즈합니다.

## 암호화 시크릿 스토어

PIN, Bluesky 비밀번호, Webhook 시크릿 등의 기밀 값은 `cryptography` 패키지의 Fernet 암호화로 보호됩니다.

- **암호화 형식**: `enc:` 접두사가 붙은 문자열
- **호환성**: 기존 평문 값은 그대로 동작 (새로 저장할 때만 암호화)
- **설치**: `uv pip install cryptography` (미설치 시 암호화 기능 비활성화)

### 키 백엔드

암호화 키는 다음 우선순위로 가져옵니다:

1. **패스프레이즈** — 환경 변수 `YU_SECRET_PASSPHRASE`를 설정하면 PBKDF2-HMAC-SHA256 (600,000 iterations)으로 키를 도출합니다. 솔트는 `data/secret.salt`에 자동 저장됩니다
2. **OS 키체인** — `keyring` 패키지가 설치되어 있는 경우, Windows Credential Manager / macOS Keychain / Linux Secret Service에 키를 보관합니다
3. **파일** — `data/secret.key` (기존 호환, 최초 자동 생성)

```bash
# 패스프레이즈 설정 예시
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# 키체인 사용
uv pip install keyring
```

### 키 내보내기/가져오기

다른 머신으로 이전하거나 백업용으로, 비밀번호 보호 JSON 형식으로 암호화 키를 내보내기/가져오기할 수 있습니다.

- `POST /api/settings/secrets/export` — 비밀번호 (8자 이상)로 보호하여 내보내기
- `POST /api/settings/secrets/import` — 내보내기 데이터와 비밀번호로 키 복원
- `POST /api/settings/secrets/migrate-keychain` — 파일에서 키체인으로 이전
- `GET /api/settings/secrets/status` — 백엔드 상태 확인

### 키체인으로 이전

파일에 저장된 키를 키체인으로 이전하려면 `/api/settings/secrets/migrate-keychain`을 호출합니다. 이전 후 `data/secret.key`는 자동 삭제됩니다.

## 1Password CLI 통합

`op` CLI가 설치된 환경에서는 1Password Vault에서 시크릿을 동적으로 가져올 수 있습니다.

### 설정

1. [1Password CLI](https://developer.1password.com/docs/cli/)를 설치합니다
2. `op signin`으로 로그인합니다
3. `config.json`에 `op_secrets` 매핑을 추가합니다:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Settings API 또는 MCP 도구에서 `op_uri`를 지정하여 설정합니다:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### 동작

- `op_secrets`에 키가 등록되어 있는 경우, `op read`로 시크릿을 가져옵니다
- 가져온 값은 5분간 메모리 캐시됩니다
- `op` CLI가 없는 환경에서는 로컬 암호화 스토어로 폴백합니다
- `GET /api/settings/op-status`로 1Password의 인증 상태를 확인할 수 있습니다

## Settings MCP 도구

MCP 클라이언트 (Claude Desktop 등)에서 설정을 관리할 수 있습니다.

| 도구 | 설명 |
|------|------|
| `settings_get_schema` | 전체 설정의 스키마 (타입, 설명, 카테고리)를 가져옴 |
| `settings_get_all` | 전체 설정값을 가져옴 (시크릿은 마스킹) |
| `settings_get` | 단일 설정값을 가져옴 |
| `settings_set` | 설정값을 업데이트 (시크릿은 자동 암호화) |
| `secrets_status` | 암호화 키 백엔드의 상태를 가져옴 |
| `secrets_export` | 비밀번호 보호 JSON으로 키를 내보내기 |
| `secrets_import` | 내보내기 데이터에서 키를 가져오기 |
