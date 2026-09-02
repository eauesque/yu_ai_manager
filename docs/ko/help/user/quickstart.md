# 5분 만에 시작하는 YU AI Manager

## YU AI Manager란

YU AI Manager는 AI 생성 이미지 (Stable Diffusion / NovelAI / ComfyUI 등)의 메타데이터를 일원 관리할 수 있는 WebUI 애플리케이션입니다. 이미지에 임베디드된 프롬프트와 모델 정보를 자동 추출하여, 태그 검색/열람/정리를 효율화합니다.

---

## 동작 환경

| 항목 | 요건 |
|------|------|
| Python | 3.11 이상 |
| Node.js | 18 이상 (프론트엔드 빌드용) |
| OS | Windows 10/11, macOS, Linux |
| 브라우저 | Chrome / Firefox / Edge (최신 버전 권장) |

---

## 설치 절차

### 1. 리포지토리 클론

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Python 가상환경 생성

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Python 의존 패키지 설치

```bash
uv pip install -r requirements.txt
```

> `uv`가 설치되어 있지 않은 경우 `pip install uv`로 먼저 설치해 주세요.

### 4. 프론트엔드 빌드

```bash
pnpm install
pnpm run build
```

> `pnpm`이 설치되어 있지 않은 경우 `npm install -g pnpm`으로 먼저 설치해 주세요.

이것으로 설치가 완료됩니다.

---

## 최초 실행

### 1. 서버 시작

```bash
# venv를 활성화하지 않은 경우 먼저 활성화
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. 브라우저에서 접속

실행 후, 브라우저에서 다음 URL을 엽니다:

```
http://localhost:5000
```

*(메인 화면 스크린샷)*

---

## 처음에 해야 할 일

### Step 1: 이미지 폴더를 스캔 등록하기

AI 생성 이미지가 저장된 폴더를 등록하여 메타데이터를 읽어들입니다.

1. 화면 우측 상단의 햄버거 메뉴에서 **Settings**를 엽니다
2. **Scan** 탭을 선택합니다
3. 스캔 대상 폴더의 경로를 추가합니다
4. 폴더 추가 후 자동으로 스캔이 시작됩니다

*(스캔 폴더 등록 화면 스크린샷)*

스캔 중에는 화면 상단에 프로그레스 바가 표시됩니다. 이미지 수가 많은 경우 몇 분이 걸릴 수 있지만, 스캔 중에도 검색/열람이 가능합니다.

### Step 2: 썸네일 그리드에서 이미지 보기

스캔이 완료되면 메인 페이지에 썸네일 그리드가 표시됩니다.

*(썸네일 그리드 표시 스크린샷)*

- **스크롤**: 가상 스크롤로 대량의 이미지를 부드럽게 표시합니다
- **정렬**: 화면 상단의 정렬 메뉴에서 날짜순/평점순 등으로 전환할 수 있습니다
- **우클릭**: 컨텍스트 메뉴에서 즐겨찾기 등록이나 컬렉션 추가가 가능합니다

### Step 3: 태그 검색으로 이미지 필터링

검색 바에 태그를 쉼표로 구분하여 입력하면, 해당하는 이미지만 표시됩니다.

```
1girl, blue_eyes, school_uniform
```

*(태그 검색 화면 스크린샷)*

- **자동 완성**: 입력 중에 후보 태그가 표시됩니다
- **필터**: 날짜 범위, 파일 형식, 별 평점 등으로 필터링이 가능합니다
- **프롬프트 내 검색**: 프롬프트 텍스트 전문을 검색하는 것도 가능합니다

### Step 4: 상세 모달에서 이미지 정보 확인

썸네일을 클릭하면 상세 모달이 열립니다.

*(상세 모달 스크린샷)*

- **Info 탭**: 프롬프트, 네거티브 프롬프트, 모델명, 생성 파라미터 등을 확인합니다
- **AI Analysis 탭**: WD-Tagger에 의한 자동 태그 부여 결과를 표시합니다 (설정된 경우)
- **별 평점**: 이미지에 1~5의 별 평점을 매길 수 있습니다
- **즐겨찾기**: 하트 아이콘으로 즐겨찾기에 등록합니다
- **태그 편집**: 사용자 태그의 추가/삭제가 가능합니다
- **키보드 조작**: 좌우 화살표 키로 전후 이미지로 이동합니다

---

## 자주 사용하는 조작 요약

| 하고 싶은 것 | 조작 |
|-------------|------|
| 이미지 찾기 | 검색 바에 태그 입력 |
| 이미지 상세 보기 | 썸네일 클릭 |
| 즐겨찾기에 추가 | 상세 모달의 하트 아이콘 또는 우클릭 메뉴 |
| 별 평점 매기기 | 상세 모달의 별 아이콘 |
| 이미지를 컬렉션에 추가 | 우클릭 메뉴 > 컬렉션에 추가 |
| 여러 이미지 선택 | Ctrl+클릭 (또는 Shift+클릭)으로 범위 선택 |
| 새 폴더 스캔 | Settings > Scan 탭 |

---

## 다음 단계

기본 조작에 익숙해지면 다음 기능도 시도해 보세요.

### Settings (설정)

Settings 페이지에서는 외관 커스터마이즈, 타임존 설정, LAN 공개 설정 등을 할 수 있습니다.
자세한 내용은 [Settings 가이드](settings.md)를 참조해 주세요.

### Bridge (이미지 생성 도구 연동)

SD WebUI / ComfyUI / NovelAI API와 연동하여 프롬프트를 송수신할 수 있습니다.
자세한 내용은 [Bridge 가이드](bridges.md)를 참조해 주세요.

### Extensions (확장 기능)

WD-Tagger (자동 태그 부여), 프롬프트 라이브러리, 채팅 로그 뷰어 등 다수의 확장 기능을 사용할 수 있습니다. Settings > Extensions 탭에서 관리할 수 있습니다.

### 시맨틱 검색

CLIP 모델을 설정하면 「해변에서 석양을 보고 있는 소녀」와 같은 자연어로 이미지 검색이 가능합니다.
자세한 내용은 [검색 가이드](search.md)를 참조해 주세요.

### MCP 서버

Claude Desktop 등의 AI 에이전트에서 YU AI Manager를 조작할 수 있습니다. stdio 트랜스포트로 연결합니다.

---

## 문제 해결

문제가 발생한 경우 [문제 해결 가이드](troubleshooting.md)를 참조해 주세요.

자주 발생하는 문제:

- **`uv` 명령어를 찾을 수 없음**: `pip install uv`로 설치합니다
- **`pnpm` 명령어를 찾을 수 없음**: `npm install -g pnpm`으로 설치합니다
- **포트 5000이 사용 중**: `python web_ui.py --port 5100`으로 다른 포트를 지정합니다
- **이미지가 표시되지 않음**: 스캔 폴더의 경로가 올바른지, 이미지 파일의 실체가 존재하는지 확인합니다
