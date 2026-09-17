# YU AI Manager -- 배포 가이드

> **[English](README.md) | [日本語](README.ja.md) | [繁體中文](README.zh-tw.md) | [简体中文](README.zh-cn.md)**

## 사전 요구 사항

- Docker Engine 20.10 이상
- Docker Compose V2 (`docker compose` 명령어)
- 프로젝트 루트에 `config.json` 파일

## 빠른 시작

```bash
# 1. 프로젝트 루트에 config.json 준비
cp config.json.example config.json
# config.json 편집 (pin, scan_roots 등 설정)

# 2. data 디렉토리 생성 (최초 1회만)
mkdir -p data

# 3. 빌드 및 시작
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. 브라우저에서 열기
# http://localhost (NGINX_PORT=80인 경우)
```

## 정지 / 재시작

```bash
# 정지
docker compose -f deploy/docker-compose.prod.yml down

# 재시작 (코드 변경 후)
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## 환경 변수

`deploy/.env.example`을 `deploy/.env`로 복사하고 필요에 따라 편집하세요.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NGINX_PORT` | `80` | 호스트에서 Nginx가 노출하는 포트 |
| `UPSTREAM_HOST` | `app` | Flask 컨테이너의 호스트명 (보통 변경 불필요) |
| `UPSTREAM_PORT` | `5000` | Flask 컨테이너의 포트 (보통 변경 불필요) |

## 볼륨 마운트

| 호스트 | 컨테이너 | 설명 |
|--------|----------|------|
| `data/` | `/app/data/` | 영구 SQLite DB (`tags.db`) |
| `config.json` | `/app/config.json` | 애플리케이션 설정 (읽기 전용) |
| `static/` | `/app/static/` | Nginx가 직접 서빙하는 정적 파일 |

### 서버 시작 전에 데이터 디렉터리가 존재해야 함

배포 담당자가 생성합니다. 서버는 생성하지 않습니다. 스탠드얼론 모드에서 yu-server는 `tags.db`가 없을 때 자동으로 생성하지만, 이를 보관하는 디렉터리는 **의도적으로 생성하지 않습니다**: `--db` 경로를 잘못 입력하면 새로운 빈 라이브러리가 생성되어 손실된 상태와 구별할 수 없게 되기 때문입니다. 디렉터리가 없으면 시작 시 거부되며 해석된 절대 경로가 표시됩니다.

Docker 사용자는 빠른 시작의 `mkdir -p data`에서 이것을 얻습니다. `deploy/yu-server.service`의 경우 `${YU_DB}`를 포함하는 디렉터리가 이미 존재해야 합니다. `deploy/systemd/yu-server.service`는 `WorkingDirectory`에서 상대 기본값 `data/tags.db`로 실행되므로, 그 디렉터리 아래에 `data/`를 생성해야 합니다. 데스크톱 빌드는 이를 자동으로 처리합니다 (`src-tauri/src/app_dirs.rs::ensure_data_dir`).

스탠드얼론은 또한 `--db-key` (또는 `YU_DB_KEY`)가 필수입니다: 서버에는 기본 키가 없으며 암호화되지 않은 데이터베이스 생성을 거부합니다. Python 버전이 SQLCipher를 통해 무조건적으로 `tags.db`를 열지만 평문 형식은 절대 열 수 없기 때문입니다.

### 바이너리보다 오래된 데이터베이스

데이터베이스의 스키마 버전이 바이너리가 기대하는 버전보다 낮고, 이를 이행할 수 있는 Python 백엔드가 어디에도 선언되지 않은 경우 yu-server는 **78**로 종료합니다. 재시도해도 해결되지 않으므로 `RestartPreventExitStatus=78`이 systemd의 재시도를 막습니다.

### 이행하기

서비스가 사용하는 데이터베이스를 대상으로 이행 도구를 실행하십시오:

```sh
cd /path/to/yu_ai_manager
YU_DB_KEY='<the key from server.env>' \
  uv run python scripts/migrate_db_cli.py --db /path/to/data/tags.db
```

이 도구는 이행만 합니다. 데이터베이스를 생성하지 않으며(스키마 버전 0을 보고하는 파일은 거부됩니다), `config.json`을 읽지 않고, 기본적으로 이행 전 백업을 만들 수 없으면 이행을 거부합니다. 종료 코드는 `0` 이미 최신이거나 이행 성공, `1` 이행 실패, `3` 백업 불가, `4` 데이터베이스를 열 수 없음(키 불일치·손상·권한), `5` 버전 0, `6` 다른 프로세스가 쓰기 잠금을 보유 입니다.

**키가 관건입니다.** v4.730.3까지 Python 쪽은 내장 키로 암호화된 데이터베이스만 열 수 있었습니다. 즉 `ExecStartPre`가 생성을 요구하는 `YU_DB_KEY`를 직접 생성한 서비스는 Python에서 전혀 이행할 수 없었습니다. `--db-key`를 넘기거나 `YU_DB_KEY`를 설정하면 이행할 수 있습니다.

### 자동화하기

`deploy/yu-db-migrate.service`는 서버가 시작되기 전에 그 명령을 한 번 실행합니다. 무인 기기가 사람을 기다리지 않고 복구되도록 하기 위함입니다:

```sh
install -m644 deploy/yu-db-migrate.service ~/.config/systemd/user/
sed -i "s|__SOURCE_DIR__|$PWD|; s|__UV__|$(command -v uv)|" \
  ~/.config/systemd/user/yu-db-migrate.service
systemctl --user daemon-reload
systemctl --user enable yu-db-migrate.service
```

두 플레이스홀더 모두 절대 경로로 치환해야 합니다. systemd는 `WorkingDirectory` 안의 환경 변수를 확장하지 않습니다. 또한 `ExecStart`에 맨 프로그램 이름을 쓰는 것은 허용하지만, `~/.local/bin`을 **포함하지 않는** 고정 PATH에 대해 해석하므로 unit은 검증을 통과한 뒤 `203/EXEC`로 실패합니다.

두 플레이스홀더 중 어느 것을 치환하지 않은 채 두어도 안전합니다. 그 경우 `ConditionPathExists`가 일치하지 않아 systemd는 이 unit을 실패가 아니라 건너뜀으로 기록하고, 서버는 기존과 동일하게 78로 거부합니다. `uv`를 나중에 삭제하거나 이동한 경우에도 같습니다. 이 unit은 인터프리터 자체도 조건으로 명시합니다 — 스크립트만 명시했을 때는 조건을 통과한 뒤 `203/EXEC`로 죽었습니다(실측). Python 트리가 없는 기기에서도 같은 일이 일어나며 이는 의도된 것입니다. 서버 unit은 이 unit을 `Wants=`로 묶으며 결코 `Requires=`로 묶지 않습니다. 이행의 실패나 건너뜀이 "데이터베이스 이행이 필요함"을 "의존성 실패"로 바꿔놓지 않게 하기 위함입니다.

`TimeoutStartSec=1800`은 의도적으로 넉넉합니다. 이행 사슬 자체는 빠르며, 스키마만 갖춘 빈 데이터베이스에서 측정한 결과 v1에서 v89까지 약 2.4초입니다. 다만 이는 하한이지 추정치가 아닙니다. 소요 시간의 대부분은 데이터를 변환하는 28개 단계가 차지하며, 그것은 장서량에 비례합니다. 값을 낮추기 전에 직접 측정하십시오 (`time uv run python scripts/migrate_db_cli.py …`). 도중에 중단된 이행은 도달한 단계 그대로 대장에 남습니다.

Python 백엔드를 실제로 함께 운영한다면 `server.env`에 `YU_PYTHON_URL`을 설정하십시오. 이것이 이행 주체의 선언이 되어, 오래된 데이터베이스는 거부 대신 한 번 경고하고 서비스를 계속합니다. 이는 Python이 정말로 그 자리에 있을 때에만 옳습니다.

그 밖의 시작 실패에는 5분 동안 5회의 시도가 주어집니다 (`StartLimitBurst`/`StartLimitIntervalSec`). 이행 중에는 쓰기 잠금이 유지되므로 그 사이의 시작은 실패하지만 재시도로 회복됩니다. 이행이 5회 시도보다 길어지면 systemd는 unit을 failed로 기록하므로, `systemctl --user reset-failed yu-server`로 해제한 뒤 다시 시작하십시오.

## PIN 인증 (프로덕션)

LAN에 노출할 때는 `config.json`에 PIN을 설정하세요. `0.0.0.0`에 바인딩할 때 PIN이 없으면 서버가 시작을 거부합니다.

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000,
    "lan": true
  },
  "pin": "your-secret-pin"
}
```

Docker 환경에서는 Nginx가 프론트엔드 역할을 하므로 Flask는 항상 `0.0.0.0:5000`에서 수신합니다. Nginx 포트 바인딩을 통해 외부 접근을 제어하세요.

## SSL/TLS 종단 (리버스 프록시 패턴)

이 Nginx 구성은 HTTP (포트 80)만 제공합니다. SSL/TLS를 사용하려면 다음 방법 중 하나를 선택하세요.

### 방법 1: 앞단에 리버스 프록시 배치

```
[클라이언트] --HTTPS--> [Cloudflare / Caddy / Traefik]
                              |
                          --HTTP--> [이 Nginx :80]
                                        |
                                    --> [Flask :5000]
```

### 방법 2: 이 Nginx에 직접 SSL 추가

`nginx.conf.template`를 편집하여 `listen 443 ssl;` 및 인증서 경로를 추가하세요. Let's Encrypt (certbot)와의 연동이 일반적입니다.

## 리버스 프록시 설정 (ProxyFix)

Nginx 등의 리버스 프록시를 통해 접근할 때, 애플리케이션이 클라이언트 IP, 프로토콜, 호스트를 올바르게 인식하도록 `config.json`을 설정하세요.

### 방법 1: trusted_proxy_ips 지정 (권장)

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

CIDR 표기법을 지원합니다. 신뢰할 수 있는 IP의 `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Forwarded-Host` 헤더가 자동으로 처리됩니다.

### 방법 2: behind_proxy 플래그 (간단)

```json
{
  "deploy": {
    "behind_proxy": true
  }
}
```

`trusted_proxy_ips`가 설정되지 않은 경우 루프백 주소 (`127.0.0.1`, `::1`)만 신뢰합니다. 프록시가 별도의 컨테이너에서 실행되는 경우 (예: Docker Compose) 방법 1을 사용하세요.

## 문제 해결

### 컨테이너가 시작되지 않는 경우

```bash
# 로그 확인
docker compose -f deploy/docker-compose.prod.yml logs app
docker compose -f deploy/docker-compose.prod.yml logs nginx
```

### DB 파일 권한 오류

`data/` 디렉토리의 권한을 확인하세요. 컨테이너 내 프로세스에 쓰기 권한이 필요합니다.

```bash
chmod 777 data/
```

### 정적 파일이 404를 반환하는 경우

빌드된 `static/dist/` 디렉토리가 존재하는지 확인하세요.

```bash
# 호스트에서 빌드
pnpm run build

# 또는 Docker 빌드에 포함
```

---

## WD-Tagger 원격 서버

LAN 상의 여러 머신에 분산 태깅을 수행하기 위한 독립형 추론 서버입니다. 이 스크립트는 YU AI Manager 메인 애플리케이션 없이 독립적으로 실행됩니다.

### 지원 백엔드

| 백엔드 | 실행 환경 | 필요 파일 | 용도 |
|--------|-----------|-----------|------|
| `onnx` | CPU / CUDA / ROCm | `model.onnx` | 범용 (어떤 머신에서도 실행 가능) |
| `hailo` | Hailo-10H NPU | `model.hef` | Pi 5 + Hailo-10H에서의 고속 추론 |
| `auto` | Hailo 우선, ONNX 폴백 | 둘 다 또는 하나 | 권장 |

### 설정

```bash
# 1. 필요 패키지 설치
pip install numpy Pillow

# ONNX 백엔드:
pip install onnxruntime          # CPU
pip install onnxruntime-gpu      # NVIDIA CUDA

# Hailo 백엔드:
# Hailo Developer Zone 또는 소스에서 hailo_platform wheel 설치

# 2. 모델 디렉토리 준비
mkdir -p models/wd-swinv2-tagger-v3
# HuggingFace에서 model.onnx와 selected_tags.csv 다운로드:
#   https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
# Hailo의 경우 model.hef도 배치 (ONNX에서 Dataflow Compiler로 변환)

# 3. 서버 시작
python hailo_tagger_server.py --model-dir ./models/wd-swinv2-tagger-v3

# 백엔드 명시적 지정:
python hailo_tagger_server.py --backend onnx --model-dir ./models/wd-swinv2-tagger-v3
python hailo_tagger_server.py --backend hailo --model-dir ./models/wd-swinv2-tagger-v3

# 인증 토큰 사용:
python hailo_tagger_server.py --token "my-secret" --model-dir ./models/wd-swinv2-tagger-v3

# JSON 설정 파일 사용:
python hailo_tagger_server.py --config tagger_config_example.json
```

### 설정 파일 예시 (`tagger_config_example.json`)

```json
{
  "port": 8080,
  "host": "0.0.0.0",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": ""
}
```

### YU AI Manager 설정

메인 YU AI Manager WebUI의 **Settings > Tagger** 탭에서 서버를 등록하세요.

1. "Add Server" > Type: `hailo_remote`
2. Endpoint URL: `http://<worker-ip>:8080`
3. Bearer Token: (설정한 경우에만)
4. Distribution mode: `parallel` (다중 머신 병렬 처리용)

### API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/health` | GET | 서버 상태 (backend, device, model) |
| `/tag` | POST | 이미지 태깅 (multipart/form-data, 필드: `image`) |

### 헬스 체크 예시

```bash
curl http://192.168.1.101:8080/health
# {"status": "idle", "backend": "onnx", "device": "onnx-cpu", "model": "wd-swinv2-tagger-v3", ...}
```

### 태깅 예시

```bash
curl -X POST http://192.168.1.101:8080/tag \
  -F "image=@test.png"
# {"tags": [{"tag": "1girl", "confidence": 0.97, "category": "general"}, ...], "elapsed_ms": 150}
```
