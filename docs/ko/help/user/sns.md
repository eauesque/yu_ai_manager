# SNS Share & Bluesky Monitor

## 개요

SNS Share는 YU AI Manager에서 AI 생성 이미지를 Bluesky와 X (Twitter)에 직접 공유할 수 있는 확장 기능입니다. 게시 텍스트는 맞춤 설정 가능한 템플릿에서 자동 생성되며, 이미지 메타데이터의 변수가 자동으로 확장됩니다. Bluesky Monitor는 알림 모니터링 기능을 추가하여 AI 기반 분류와 자동 응답이 가능합니다.

## 설정

### Bluesky App Password 발급

1. [bsky.app](https://bsky.app)에 로그인한 후 **설정 > App Passwords**로 이동
2. **App Password 추가** 클릭
3. 이름을 입력(예: "YU AI Manager")하고 **App Password 생성** 클릭
4. 표시된 비밀번호를 복사

> **주의**: App Password는 한 번만 표시됩니다. 대화 상자를 닫기 전에 반드시 복사하세요. Bluesky 메인 비밀번호는 절대 사용하지 마세요.

### YU AI Manager에서 설정

1. 네비게이션 메뉴에서 **Settings**를 열기
2. **SNS** 탭으로 전환
3. 다음 정보를 입력:
   - **Bluesky 핸들**: 핸들 이름(예: `yourname.bsky.social`)
   - **App Password**: 위에서 발급받은 App Password
   - **게시 템플릿**: 게시 텍스트 템플릿([템플릿 변수](#템플릿-변수) 참조)
4. **저장** 클릭

### 연결 테스트

인증 정보를 저장한 후 **연결 테스트**를 클릭하여 Bluesky 인증을 확인합니다. 성공하면 핸들 이름과 표시 이름이 표시됩니다.

## 기능

### Bluesky에 공유

이미지 상세 보기에서 Bluesky에 직접 이미지를 공유할 수 있습니다.

1. 이미지 상세 모달을 열기
2. **SNS** 버튼 클릭
3. 생성된 게시 텍스트를 확인하고 편집
4. **Bluesky에 게시** 클릭

- 게시 텍스트는 설정된 템플릿에서 메타데이터 변수를 확장하여 생성됩니다
- 이미지는 Bluesky의 1 MB 업로드 제한에 맞춰 자동으로 압축 및 리사이즈됩니다
- 게시는 **300 grapheme**으로 제한됩니다(초과 시 자동으로 잘립니다)
- 이미지 첨부 여부를 선택할 수 있습니다

### X (Twitter)에 공유

Web Intent(브라우저에서 X의 작성 페이지를 여는 방식)를 통해 이미지 정보를 X에 공유합니다.

1. 이미지 상세 모달을 열기
2. **SNS** 버튼 클릭
3. **X에 공유** 클릭

새 브라우저 탭에서 X의 작성 페이지가 열리며, 템플릿에서 생성된 텍스트가 자동 입력됩니다. 게시 전에 텍스트를 편집할 수 있습니다. X에서는 이미지가 자동 첨부되지 않으므로 수동으로 첨부해야 합니다.

### Bluesky Monitor

Bluesky Monitor는 Bluesky 알림을 폴링하여 로컬에 큐잉하고 분류 및 응답을 수행합니다.

#### 알림 유형

- **멘션**: 게시물에서 당신이 멘션됨
- **답글**: 당신의 게시물에 답글이 달림
- **인용**: 당신의 게시물이 인용됨
- **팔로우**: 누군가 당신을 팔로우함
- **좋아요**: 당신의 게시물에 좋아요가 눌림
- **리포스트**: 당신의 게시물이 리포스트됨

#### 폴링

알림은 설정 가능한 간격으로 자동 가져옵니다(기본값: 30분, 최소: 5분). Settings 또는 MCP 도구에서 즉시 폴링을 트리거할 수도 있습니다.

#### 큐 시스템

각 알림은 **pending**(미처리) 상태로 큐에 들어갑니다. 이후 다음 상태로 전환할 수 있습니다:

- **notified** -- MCP 클라이언트(Claude Desktop)에 알림됨
- **dismissed** -- 조치 불필요로 해제됨

#### 분류

AI 기반 분류로 각 알림에 대응이 필요한지 판단합니다:

- **valid** -- 대응 필요(질문, 버그 보고, 협업 요청 등)
- **invalid** -- 무시 가능(일반적인 칭찬, 스팸, 봇 콘텐츠 등)

알림 유형(멘션, 답글, 인용)별로 맞춤 설정 가능한 분류 프롬프트가 있습니다. 기본 프롬프트가 제공되며 언제든 복원할 수 있습니다.

#### 자동 응답

valid로 판정된 멘션, 답글, 인용에 대해 템플릿 기반 자동 답장을 보낼 수 있습니다:

- Monitor 설정에서 자동 응답을 활성화
- 알림 유형별로 응답 템플릿을 맞춤 설정
- 응답은 300 grapheme으로 제한됩니다

#### 자동 해제

팔로우, 좋아요, 리포스트는 자동으로 해제하여 큐의 노이즈를 줄일 수 있습니다. 각 유형은 Settings에서 개별적으로 전환 가능합니다.

#### MCP 연결 시 알림

MCP 클라이언트(Claude Desktop)가 연결되면 미처리 알림이 일괄 보고되므로 개발 세션 중에 확인할 수 있습니다.

### Settings

SNS 설정은 Settings 페이지의 **SNS** 탭에서 수행합니다:

- **Bluesky 인증 정보**: 핸들과 App Password(비밀번호는 암호화 저장, 마스킹 표시)
- **게시 템플릿**: 변수 플레이스홀더가 포함된 템플릿 텍스트
- **Monitor 설정**:
  - 폴링 간격(분)
  - 팔로우, 좋아요, 리포스트 자동 해제
  - 자동 응답 활성화/비활성화
  - 멘션, 답글, 인용의 분류 프롬프트
  - 멘션, 답글, 인용의 자동 응답 템플릿

## MCP 연동

SNS Share & Bluesky Monitor는 15개의 MCP 도구를 제공합니다:

**공유 (6개 도구)**:
- `share_to_bluesky` -- 이미지를 Bluesky에 게시
- `get_x_share_url` -- X Web Intent URL 가져오기
- `get_sns_preview` -- 템플릿 확장 미리보기
- `test_bluesky_connection` -- API 연결 테스트
- `get_sns_config` / `save_sns_config` -- SNS 설정 조회 및 저장

**알림 큐 (5개 도구)**:
- `bsky_get_pending_notifications` -- 미처리 알림 가져오기
- `bsky_get_notification_queue` -- 필터 적용된 큐 항목 가져오기
- `bsky_triage_notification` -- 분류 결과 설정(valid/invalid)
- `bsky_send_auto_response` -- 알림에 답장 보내기
- `bsky_poll_notifications` -- 즉시 폴링 트리거

**Monitor 설정 (4개 도구)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- Monitor 설정 조회 및 저장
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- 분류 프롬프트 및 응답 템플릿 조회 및 저장

## 템플릿 변수

게시 템플릿에서 사용할 수 있는 변수:

| 변수 | 설명 |
|---|---|
| `{positive_short}` | 포지티브 프롬프트(처음 100자) |
| `{positive}` | 포지티브 프롬프트 전문 |
| `{negative_short}` | 네거티브 프롬프트(처음 50자) |
| `{model}` | 모델 이름 |
| `{seed}` | 시드 값 |
| `{steps}` | 샘플링 스텝 수 |
| `{cfg}` | CFG 스케일 |
| `{sampler}` | 샘플러 이름 |
| `{size}` | 이미지 크기 |
| `{tags}` | 상위 5개 태그 |
| `{filename}` | 파일 이름 |

기본 템플릿: `{positive_short}`

## 사용 팁

- **App Password 보안**: Bluesky 메인 비밀번호가 아닌 App Password를 반드시 사용하세요. App Password는 bsky.app 설정에서 언제든 해지할 수 있습니다
- **속도 제한**: Bluesky API에는 속도 제한이 있습니다. 연속적인 게시를 피하세요. 이미지 업로드도 속도 제한에 포함됩니다
- **Grapheme 계산**: Bluesky는 300자 제한에 문자 수가 아닌 grapheme 클러스터를 사용합니다. CJK 문자는 1 grapheme으로 계산됩니다
- **이미지 압축**: 1 MB를 초과하는 이미지는 자동으로 리사이즈됩니다. 이미지 준비에 실패하면 텍스트만으로 게시됩니다
- **Monitor 폴링 간격**: 알림 빈도에 맞춰 폴링 간격을 설정하세요. 알림이 많은 계정은 짧은 간격이 효과적입니다
- **자동 해제**: 팔로우, 좋아요, 리포스트의 자동 해제를 활성화하면 조치가 필요한 알림에 집중할 수 있습니다
- **분류 프롬프트**: 커뮤니케이션 스타일과 받는 상호작용 유형에 맞게 분류 프롬프트를 맞춤 설정하세요
