# YU AI Manager

AI 생성 이미지의 메타데이터 관리 WebUI입니다.

## 개요

AI 생성 이미지에 포함된 메타데이터(프롬프트·모델·시드 등)를 추출·검색·관리하는 WebUI 도구입니다.

**이런 것들을 할 수 있습니다:**

- 폴더나 ZIP 아카이브를 통째로 스캔하여 이미지를 자동 등록
- 프롬프트·태그·모델명·시드값 등으로 횡단 검색·필터링
- 마음에 드는 이미지를 SD / ComfyUI / NovelAI에 즉시 전송하여 재생성
- WD-Tagger로 자동 태그 지정, Ollama/OpenAI로 내용 분석
- LAN 상의 다른 디바이스(스마트폰 등)에서 QR 코드로 접근

**지원 소스**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## 동작 환경

- Windows / Linux / macOS

> **수동 설치 불필요** `start.sh` / `start.bat`가 필요한 모든 도구를 프로젝트 아래에 부트스트랩합니다(시스템 쓰기·관리자 권한 없음).

## 설정·시작

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

초기 실행 시 자동 설정:

| 도구 | 획득 방법 |
| --- | --- |
| `uv` | `./bin/uv`에 자동 DL |
| Python 3.11+ | `uv`가 자동 설치 |
| Node.js 22 LTS | 선택사항 — `./bin/node/`로의 DL 확인(약 30 MB) |
| pnpm | Node.js 설치 시 `corepack`을 통해 활성화 |
| ffmpeg | 선택사항 — Windows/macOS는 `./bin/ffmpeg/`로의 DL 확인(약 80 MB), Linux는 distro의 `apt`/`dnf`/`pacman` 명령 안내 |

`YU_AUTO_INSTALL=1`로 설정하면 비대화형 환경(CI 등)에서도 프롬프트를 건너뛰고 전체 자동 설치합니다. ffmpeg는 동영상 분석·S2T·OCR 등의 확장 기능 전용이므로 본체 실행에는 불필요합니다.

2번째 이후부터는 종속성이나 TypeScript 소스가 업데이트되었을 때만 재설치·재빌드합니다.

`launch-args.txt`에 `--db`, `--port`, `--lan`, `--pin` 등을 기재하면 영구 설정할 수 있습니다.

## 주요 기능

### 스캔·등록
- PNG / WebP / JPEG 메타데이터 자동 추출
- ZIP / 7z 아카이브를 전개하지 않고 투과 스캔
- 드래그 앤 드롭으로 파일 추가

### 검색·열람
- 프롬프트·태그·모델명·시드값의 전문 검색
- 정규식 검색, 복합 조건 필터
- pHash 유사 이미지 검색, CLIP 의미론적 검색

### 정리·관리
- 즐겨찾기, 별 평가(1~5), 메모(어노테이션)
- 컬렉션(그룹 분류)
- 통계 대시보드·월간 리포트·트로피 시스템

### 생성 도구 연동(Bridge)
- SD WebUI / Forge / ComfyUI / NovelAI로의 프롬프트 즉시 전송
- 클립보드를 통한 전송도 지원

### AI 보조
- WD-Tagger에 의한 자동 태그 지정
- Ollama / OpenAI를 사용한 이미지 내용 분석
- 음성 텍스트 변환(S2T)

### 네트워크·공유
- LAN 공유 모드(QR 코드로 스마트폰에서 접근)
- MCP 서버(AI 에이전트에서 조작)
- Fleet 관리(여러 인스턴스의 일괄 관리)

### 커스터마이제이션
- 커스텀 UI·Extension 시스템
- 테마 지원(라이트 / 다크)
- Tauri 데스크톱 앱(브라우저 불필요)

## 다국어 지원

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## 문서

- [빠른 시작](docs/ko/help/user/quickstart.md)
- [사용 사례 모음](docs/ko/help/user/use-cases.md)
- [API 레퍼런스](docs/ko/api/README.md)
- [성능 튜닝](docs/ko/help/user/performance-tuning.md)
- [배포](docs/ko/help/user/deployment.md)
- [Extension 개발](docs/ko/plugin-development/getting-started.md)
- [커스텀 UI](docs/ko/custom-ui/README.md)
- [MCP 도구](docs/ko/api/MCP_TOOLS_REFERENCE.md)
- [전체 문서 목록](docs/ko/README.md)

## 개발·커스터마이제이션

[DEVELOPMENT.ko.md](DEVELOPMENT.ko.md) 참조 ([English](DEVELOPMENT.en.md))

## 문제가 생겼을 때 AI에 물어보기

### 시작되지 않는 경우

Claude Code Desktop 등의 AI 에이전트에 이 프로젝트의 폴더를 작업 디렉토리로 연 후, 다음과 같이 말씀해주세요:

> `start.bat`(또는 `start.sh`)를 실행해도 멈춥니다. 조사해주세요.

> **보충**: Claude Code Desktop에서는 대화를 시작하기 전에 프로젝트 폴더를 지정해야 합니다.

### 시작 후의 문제·설정·사용법

**스텝 1 — 컨텍스트 획득**

도움말 페이지(`/help`)를 열고 **「AI 컨텍스트 복사」** 버튼을 누르세요.
로그인된 브라우저 세션을 사용하여 `GET /api/ai-context`를 fetch하고, JSON을 클립보드에 복사합니다(http:// LAN 환경에서도 동작).

> **보충(API 키를 가지고 있는 경우)**: admin 범위의 API 키가 있으면 `Authorization: Bearer <key>` 헤더를 붙여서 직접 `GET /api/ai-context`를 호출할 수 있습니다.

**스텝 2 — AI에 전달**

복사한 JSON을 AI 채팅에 붙여넣고 계속해서 질문을 쓰세요:

> 〔붙여넣은 JSON〕
> 이를 바탕으로 〔문제 설명〕을 해결해주세요.

`/api/ai-context`에는 현재 버전·활성화된 기능·설정 힌트·API 목록·CSRF 규칙이 포함되어 있으며, AI가 정확하게 지원하기 위해 필요한 정보가 모두 갖춰져 있습니다.

## FAQ

[docs/ko/FAQ.md](docs/ko/FAQ.md) ([English](docs/en/FAQ.md))

## 버그 보고

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## 라이선스

MIT License — [LICENSE](LICENSE) / [구어 번역](docs/ko/LICENSE.md) ([English](docs/en/LICENSE.md))
