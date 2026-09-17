# GitHub Integration

## 개요

GitHub Integration은 YU AI Manager에서 GitHub 저장소, Issue, Pull Request, Discussion, Release를 직접 관리할 수 있는 확장 기능입니다. 여러 GitHub 계정을 지원하며, 토큰은 암호화하여 안전하게 저장됩니다. 대시보드에서 알림과 저장소 통계를 빠르게 확인할 수 있고, AI 기반 Issue 분류 기능도 제공합니다.

## 설정

### GitHub Personal Access Token (PAT) 발급

1. GitHub에 로그인한 후 **Settings > Developer settings > Personal access tokens > Tokens (classic)** 으로 이동
2. **Generate new token (classic)** 클릭
3. 토큰 이름을 입력하고 만료 기간을 설정
4. 범위에서 **`repo`** 를 체크 (저장소 전체 접근 권한 필요)
5. **Generate token** 을 클릭하고 표시된 토큰을 복사

> **주의**: 토큰은 한 번만 표시됩니다. 페이지를 떠나기 전에 반드시 복사하세요.

### 계정 추가

1. 확장 기능 런처에서 **GitHub** 카드를 클릭하거나 `/ext/github`로 직접 이동
2. **Settings** 탭을 열기
3. **계정 추가** 클릭
4. 다음 정보를 입력:
   - **라벨**: 계정의 표시 이름 (예: "개인", "업무")
   - **토큰**: 위에서 발급받은 PAT
   - **저장소**: 모니터링할 저장소를 `owner/repo` 형식으로 입력 (여러 개 가능)
5. 저장 후 드롭다운에서 계정을 선택

## 기능

### 대시보드

계정을 선택하면 대시보드가 자동으로 로드됩니다.

- **알림**: 읽지 않은 GitHub 알림 목록 표시
- **저장소 통계**: 스타 수, 포크 수, 오픈 Issue 수를 카드 형태로 표시
- **요약 카드**: 모니터링 중인 모든 저장소의 현황을 한눈에 파악

### Issues

- 저장소 및 상태(open/closed)로 필터링
- Issue 상세 보기 (본문, 댓글, 라벨)
- 새 Issue 생성
- **분류 기능**: AI 자동 분류
  - `valid_bug` — 확인된 버그 보고
  - `needs_info` — 추가 정보 필요
  - `skip` — 조치 불필요
- **Issue 큐**: GitHub의 새 Issue를 자동 폴링하여 로컬에 큐잉. MCP 클라이언트(Claude Desktop) 연결 시 미읽은 Issue를 일괄 알림.

### Pull Requests

- Pull Request 목록 및 필터링
- 차이점 통계 표시 (추가 줄 수, 삭제 줄 수, 변경 파일 수)
- 상세 뷰에서 파일별 변경 내용 확인

### Discussions

- GraphQL API를 통해 Discussion 목록 조회
- 카테고리 배지 및 답변 완료 상태 표시

### Releases

- 모니터링 중인 저장소의 최신 Release 목록 표시
- Release 노트 확인

### Settings

- 계정 추가, 편집, 삭제 및 활성화/비활성화 전환
- API 속도 제한 잔량 표시
- 언어 필터 및 스케줄 간격 설정
- Issue 큐 폴링 간격, 무효 Issue 자동 닫기, MCP 연결 알림 설정
- Issue, PR, Discussion의 분류 프롬프트 편집 ([예시 보기](/help/github-triage-examples))

### Issue 큐

Issue 큐는 GitHub를 주기적으로 폴링하여 새로운 Issue를 로컬에 저장합니다.

- **폴링**: 스케줄러를 통해 자동 실행 (간격 설정 가능, 기본값 60분)
- **알림**: MCP 연결 시 미처리 Issue를 Claude Desktop에 일괄 알림
- **분류**: 큐에 들어온 각 Issue를 유효/무효로 분류 가능
- **자동 닫기**: 무효로 판정된 Issue를 템플릿 댓글과 함께 GitHub에서 자동 닫기
- **수동 폴링**: Settings에서 "Poll Now"를 클릭하면 즉시 가져오기

### 분류 프롬프트

Issue, PR, Discussion 분류 시 사용하는 AI 지시문을 맞춤 설정할 수 있습니다.

- 각 유형(Issue, PR, Discussion)마다 개별 편집 가능한 프롬프트 제공
- 기본 프롬프트가 제공되며 "기본값으로 복원"으로 언제든 복원 가능
- 다국어 및 다양한 스타일의 템플릿은 [분류 프롬프트 예시](/help/github-triage-examples) 참조
- 프롬프트는 config.json에 저장 (비밀 정보를 포함하지 않으므로 암호화 없음)

## MCP 연동

GitHub Integration은 Claude Code와 함께 사용할 수 있는 12개의 MCP 도구를 제공합니다:

- Issue 목록 조회 및 상세 보기
- Pull Request 목록 조회 및 상세 보기
- 알림 조회
- 분류 프롬프트 조회 및 업데이트
- Issue 큐 관리 (미처리 목록, 분류, 해제, 폴링)

MCP 도구를 사용하면 개발 중 편집기를 벗어나지 않고 GitHub 정보에 접근할 수 있습니다.

## 사용 팁

- **다중 계정**: 개인용과 업무용 계정을 분리하면 관리가 더 편리합니다
- **토큰 권한**: `repo` 범위로 모든 핵심 기능을 사용할 수 있습니다. 조직의 비공개 저장소에 접근하려면 해당 조직에서 SSO 인가가 별도로 필요할 수 있습니다
- **분류 활용**: Issue가 많은 저장소에서는 분류 기능으로 우선순위를 자동 지정하면 효율적입니다
- **속도 제한**: GitHub API에는 시간당 요청 한도가 있습니다. Settings 탭에서 잔여 한도를 확인할 수 있습니다
- **토큰 보안**: 토큰은 서버 측에서 암호화하여 저장됩니다. 평문으로 저장되지 않습니다
- **대시보드 갱신**: 계정을 전환하면 데이터가 자동으로 다시 로드됩니다
