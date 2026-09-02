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
