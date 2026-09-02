# 배포 및 운영 가이드

YU AI Manager를 프로덕션 환경에서 운영하기 위한 절차를 정리했습니다.

## 1. 개요

운영 패턴은 주로 3가지입니다.

| 패턴 | 용도 | 구성 |
|------|------|------|
| 직접 실행 | 개인 사용/개발 | Python + venv로 실행 |
| Docker | 서버 운영 | docker-compose로 Quart + Nginx |
| 리버스 프록시 | 외부 공개 | 기존 웹 서버 뒤에 배치 |

어떤 경우든 데이터는 `data/tags.db` (SQLite)에 저장됩니다. 외부 DB 서버는 필요 없습니다.

---

## 2. 직접 실행 (개발/개인 사용)

### 설정

```bash
# 리포지토리 가져오기
git clone <repository-url> && cd yu_ai_manager

# Python 가상환경 생성
python -m venv venv

# 가상환경 활성화
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# 의존 패키지 설치
uv pip install -r requirements.txt

# 프론트엔드 빌드
pnpm install && pnpm run build

# 실행
python web_ui.py --db data/tags.db
```

브라우저에서 `http://localhost:5000`을 열어 주세요.

### launch-args.txt를 통한 인수 설정

`launch-args.txt.example`을 `launch-args.txt`로 복사하여 편집하면, 시작 시 인수를 고정할 수 있습니다. CLI 인수가 우선됩니다.

```txt
# 포트 변경
--port 5100
# LAN 공개 (0.0.0.0 바인드)
--lan
# PIN 인증
--pin 1234
```

### systemd 서비스화 (Linux)

```ini
# /etc/systemd/system/yu-ai-manager.service
[Unit]
Description=YU AI Manager
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/yu_ai_manager
ExecStart=/opt/yu_ai_manager/venv/bin/python web_ui.py --db data/tags.db --lan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yu-ai-manager
```

### Windows 서비스화

`start.bat`를 작업 스케줄러에 등록하는 것이 가장 간단합니다. 「로그온 시 실행」으로 설정해 주세요.

---

## 3. Docker 배포

### 퀵스타트

```bash
# 설정 파일 준비
cp config.json.example config.json
# config.json 편집 (pin, scan_roots 등)

mkdir -p data

# 빌드 및 실행
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

`http://localhost`로 접속할 수 있습니다 (Nginx 경유).

### docker-compose.prod.yml 구성

- **app**: Quart 애플리케이션 (포트 5000, 내부 전용)
- **nginx**: 리버스 프록시 (포트 80을 외부 공개)

### 볼륨 마운트

| 호스트 | 컨테이너 | 용도 |
|-------|---------|------|
| `data/` | `/app/data/` | DB 파일의 영속화 |
| `config.json` | `/app/config.json` | 설정 파일 (읽기 전용) |
| `static/` | `/app/static/` | Nginx가 직접 배신하는 정적 파일 |

이미지 폴더는 `config.json`의 `scan_roots`에서 지정한 경로를 추가 마운트해 주세요.

```yaml
# docker-compose.prod.yml에 추가
volumes:
  - /path/to/images:/images:ro
```

### 환경 변수

`deploy/.env.example`을 `deploy/.env`로 복사하여 편집합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NGINX_PORT` | `80` | Nginx의 공개 포트 |
| `UPSTREAM_HOST` | `app` | Quart 컨테이너 이름 (변경 불필요) |
| `UPSTREAM_PORT` | `5000` | Quart 포트 (변경 불필요) |

### Podman을 사용하는 경우

Docker 대신 Podman으로도 동작합니다. `podman compose` 또는 `podman-compose`를 설치하고 동일한 명령어를 사용해 주세요. 자세한 내용은 `docs/en/installation/podman.md`를 참조하세요.

---

## 4. 리버스 프록시 설정

### Nginx 설정 요점

`deploy/nginx.conf.template`에 실용적인 설정이 포함되어 있습니다. 요점은 다음과 같습니다.

- **정적 파일**: `/static/`을 Nginx에서 직접 배신 (Quart를 바이패스)
- **SSE**: `/api/events/`는 `proxy_buffering off`로 버퍼링 비활성화
- **업로드 상한**: `client_max_body_size 100m` (Quart 측과 일치시킴)
- **Gzip**: JSON, CSS, JS를 압축

### SSL/TLS (Let's Encrypt)

Docker 구성의 Nginx는 HTTP 전용입니다. HTTPS가 필요한 경우 2가지 방법이 있습니다.

**방법 1: 전단 프록시 (권장)**

Cloudflare, Caddy, Traefik 등을 전단에 배치하여 HTTPS를 종단시킵니다.

```
클라이언트 --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**방법 2: Nginx에 직접 SSL 추가**

`nginx.conf.template`에 `listen 443 ssl;`과 인증서 경로를 추가하고, certbot으로 Let's Encrypt 인증서를 발급받습니다.

### Trusted Proxy 설정

리버스 프록시 경유의 경우, `config.json`에서 신뢰할 IP를 지정해 주세요.

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

이를 통해 `X-Forwarded-For` / `X-Forwarded-Proto` 헤더가 올바르게 처리됩니다. CIDR 표기를 지원합니다.

---

## 5. 인증 설정

4종류의 인증을 사용할 수 있습니다. 용도에 따라 조합해 주세요.

### PIN 인증 (브라우저 접속용)

```json
{ "pin": "your-secret-pin" }
```

LAN에 공개하는 경우 (`--lan` 또는 `0.0.0.0` 바인드) PIN 설정이 필수입니다. PIN 미설정으로 `0.0.0.0`에 바인드하면 시작이 거부됩니다.

### API 키 인증 (프로그램에서의 접속)

Settings 화면에서 API 키를 발행하고 요청 헤더에 첨부합니다.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

API 키 인증에서는 CSRF 헤더 (`X-Requested-With`)가 불필요합니다.

### Trusted Proxy 인증

리버스 프록시가 `X-Remote-User` 헤더를 부여하는 구성에서 사용할 수 있습니다. `trusted_proxy_ips` 설정이 필수입니다.

### LAN 공유 모드

`/s/` 경로로 게스트용 공유 링크를 발행할 수 있습니다. PIN을 건너뛰고 토큰으로 개별 인증합니다.

---

## 6. 백업과 복구

정기적으로 백업해야 할 파일은 다음 3종류입니다.

| 파일 | 내용 |
|------|------|
| `data/tags.db` | 모든 메타데이터/태그/설정을 포함하는 SQLite DB |
| `config.json` | 애플리케이션 설정 |
| `data/secret.key`, `data/secret.salt` | 암호화 키 (설정 암호화에 사용) |

### 백업 절차

```bash
# DB 복사 (운영 중에도 안전)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# 설정과 암호화 키
cp config.json data/secret.key data/secret.salt backup/
```

### 복구 절차

백업 파일을 원래 위치에 배치하고 서버를 재시작하기만 하면 됩니다. DB 마이그레이션은 시작 시 자동으로 적용됩니다.

암호화 키 (`secret.key`, `secret.salt`)를 분실하면, 암호화된 설정값 (API 자격 증명 등)을 복호화할 수 없게 됩니다. 반드시 백업해 주세요.

---

## 7. 업그레이드 절차

```bash
# 1. 서버 중지
# 2. 코드 업데이트
git pull

# 3. 의존 패키지 업데이트
source venv/bin/activate  # 또는 .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. 프론트엔드 재빌드
pnpm install && pnpm run build

# 5. 서버 시작
python web_ui.py --db data/tags.db
```

DB 스키마 마이그레이션은 시작 시 자동으로 실행됩니다. 수동 작업은 필요 없습니다.

Docker의 경우 재빌드하기만 하면 됩니다.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. 모니터링/로그

### 로그 스트리밍

Settings > Logs 탭에서 실시간 로그를 확인할 수 있습니다. SSE (`/api/logs/stream`)로 브라우저에 스트리밍됩니다.

과거 로그는 `/api/logs/recent`로 가져올 수 있습니다.

### 헬스체크

`/api/server-info` 엔드포인트에서 가동 상황을 확인할 수 있습니다.

```bash
curl http://localhost:5000/api/server-info
```

버전, DB 스키마 버전, 타임존 등의 정보가 반환됩니다. 모니터링 도구의 헬스체크에는 이 엔드포인트를 사용해 주세요.

### MCP를 통한 진단

MCP 클라이언트 (Claude Desktop 등)에서 `debug_health_check` 도구를 호출하면, DB 무결성 검사/검색 동작 확인/카운트 검증을 일괄 실행할 수 있습니다.
