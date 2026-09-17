# 시작하기

YU AI Manager는 AI 생성 이미지의 메타데이터를 관리하는 WebUI 애플리케이션입니다.

## 설치

### 필요 환경

- Python 3.11 이상
- Node.js 18 이상 (프론트엔드 빌드용)

### 설정 절차

```bash
# 리포지토리 클론
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# uv 설치 (최초 1회)
pip install uv

# Python 가상 환경 생성 및 의존 패키지 설치
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# 프론트엔드 빌드
pnpm install
pnpm run build

# 옵션: 시맨틱 검색 가속화 (대규모 라이브러리용)
uv pip install faiss-cpu
```

## 실행 방법

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

브라우저에서 `http://localhost:5000`에 접속해 주세요.

## 초기 설정

1. **스캔 폴더 등록**: Settings > Scan 탭에서 AI 이미지가 저장된 폴더를 추가합니다
2. **스캔 실행**: 폴더 추가 후 자동으로 스캔이 시작됩니다
3. **이미지 열람**: 메인 페이지에서 이미지를 검색하고 열람할 수 있습니다

## LAN 공개

다른 기기에서 접속하고 싶은 경우:

1. Settings > Server 탭에서 「LAN Access」를 ON으로 설정합니다
2. PIN 인증을 설정합니다 (LAN 공개 시 필수)
3. 서버를 재시작합니다

LAN 내의 다른 기기에서 `http://<서버 IP>:5000`으로 접속할 수 있습니다.
