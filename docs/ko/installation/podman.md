# Podman 설정

YU AI Manager의 컨테이너 환경은 Docker와 Podman을 모두 지원합니다. 관리 스크립트(`scripts/yu-docker.sh`, `tools/docker-build.sh`)는 설치된 런타임을 자동 감지합니다.

---

## 사전 요구사항

- Podman 4.0 이상
- `podman compose` 플러그인 (Podman 4.7+) 또는 `podman-compose` (pip)

### Podman 설치

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install podman

# Fedora
sudo dnf install podman

# macOS (Homebrew)
brew install podman
podman machine init
podman machine start
```

### Compose 도구 설치

Podman에서 `docker-compose.yml`을 사용하려면 다음 중 하나가 필요합니다:

```bash
# 옵션 1: podman-compose (pip, 경량)
uv pip install podman-compose

# 옵션 2: podman compose 플러그인 (Podman 4.7+)
# Podman에 이미 포함되어 있을 수 있습니다. 확인:
podman compose version
```

---

## 기본 사용법

### 관리 스크립트 사용 (권장)

스크립트가 Docker 또는 Podman을 자동 감지하므로 Docker 사용법과 동일합니다:

```bash
# 초기 설정
./scripts/yu-docker.sh init

# 빌드
./scripts/yu-docker.sh build

# 시작
./scripts/yu-docker.sh up

# 로그
./scripts/yu-docker.sh logs

# 중지
./scripts/yu-docker.sh down
```

### 직접 명령어

```bash
# 빌드
podman build -t yu-ai-manager .

# 시작 (compose)
podman compose up yu-ai-manager -d

# 시작 (단독)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo 변형 빌드
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Docker와의 차이점

### 루트리스 모드

Podman은 기본적으로 루트리스 모드(루트 권한 없음)로 실행됩니다. 대부분의 경우 그대로 동작하지만 다음 사항에 유의하세요:

| 항목 | 영향 | 해결 방법 |
|------|------|-----------|
| 1024 미만 포트 | 루트리스 모드에서 바인드 불가 | 문제 없음 -- 이 프로젝트는 포트 5000 사용 |
| 디바이스 패스스루 | `/dev/hailort0` 등에 접근하려면 권한 필요 | `podman run --device`와 그룹 권한 사용, 또는 `sudo podman` |
| UID 매핑 | 컨테이너 `appuser` UID가 호스트 UID와 다름 | `podman unshare chown`으로 볼륨 권한 수정 |

```bash
# UID 매핑 확인
podman unshare cat /proc/self/uid_map

# 볼륨 권한 수정 (예시)
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo 디바이스 패스스루

```bash
# 루트리스 모드에서 /dev/hailort0에 접근하지 못할 수 있음
# 옵션 1: 사용자를 hailort 그룹에 추가
sudo usermod -aG hailort $USER

# 옵션 2: 루트풀로 실행
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### 네트워킹

Podman의 기본 네트워크는 `podman`이며 Docker의 `bridge`와 동일합니다. `docker-compose.debug.yml`에 정의된 커스텀 네트워크(예: `debug-net`)는 수정 없이 동작합니다.

```bash
# 네트워크 목록
podman network ls
```

### 볼륨

명명된 볼륨과 바인드 마운트 모두 지원됩니다. `docker-compose.yml`의 바인드 마운트(예: `./data:/app/data`)는 그대로 동작합니다.

### systemd 통합 (Linux 서버 배포)

Podman은 systemd와 쉽게 통합됩니다. 자동 시작을 설정하려면:

```bash
# 컨테이너 시작 후 systemd 유닛 생성
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# 활성화
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# 부팅 시 사용자 서비스 자동 시작 활성화 (linger)
loginctl enable-linger $USER
```

---

## Docker CLI 호환성 별칭 (선택사항)

Docker 지향 문서와 스크립트를 그대로 사용하려면:

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
alias docker=podman
alias docker-compose=podman-compose
```

관리 스크립트는 런타임을 자동 감지하므로 이 별칭은 필수가 아닙니다.

---

## 문제 해결

### `WARN[0000] "/" is not a shared mount` 경고

```bash
# 루트리스 Podman에서 발생할 수 있음. 무해하지만 억제하려면:
podman system migrate
```

### `podman compose`를 찾을 수 없음

```bash
# 4.7 이전의 Podman 버전에는 compose 플러그인이 포함되지 않음
# pip를 통해 podman-compose를 대신 설치
uv pip install podman-compose
```

### 컨테이너 내부에서 localhost에 접근할 수 없음

루트리스 Podman은 `host.containers.internal`을 사용합니다 (Docker의 `host.docker.internal`에 해당).

```bash
# 디버그 컨테이너에서 웹 서비스에 접근할 때
# docker-compose.debug.yml 네트워크(http://web:5000) 사용 -- 문제 없음
```

### 이미지 정리

```bash
# 사용하지 않는 이미지 제거
podman image prune -a

# 모든 리소스 제거
podman system prune -a
```

---

## 호환성 요약

| 파일 | Podman 호환 | 비고 |
|------|-------------|------|
| `Dockerfile` | OK | 표준 OCI 사양 |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | 디바이스 패스스루에 권한 필요 |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | 런타임 자동 감지 |
| `scripts/yu-docker.sh` | OK | 런타임 자동 감지 |
| `.dockerignore` | OK | Podman도 동일 파일 읽음 |
