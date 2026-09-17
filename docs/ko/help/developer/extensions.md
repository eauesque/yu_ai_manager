# Extensions

YU AI Manager는 Extension 시스템을 통해 기능을 추가할 수 있습니다.
현재 6개 카테고리에 걸쳐 43개의 내장 Extension이 포함되어 있습니다.

## 내장 Extension 목록

### 메타데이터 추출 (metadata)

| Extension | 설명 |
|-----------|------|
| builtin-a1111 | Automatic1111 / SD WebUI PNG/WebP/WebM 메타데이터 추출 |
| builtin-novelai-v3 | NovelAI V3 이하 메타데이터 추출 |
| builtin-novelai-v4 | NovelAI V4 메타데이터 추출 (Character Prompts, Vibe Transfer) |
| builtin-comfyui | ComfyUI 워크플로 JSON 파싱 |
| builtin-annotations | 파일 어노테이션 저장, 검색, 배치 작업 |
| builtin-ratings | 별점 평가 시스템 (1-5점) |
| builtin-tag-dictionary | Danbooru 태그 사전 검색, 가져오기, 분할 |

### Bridge 연동 (bridge)

| Extension | 설명 |
|-----------|------|
| builtin-sd-webui-bridge | SD WebUI / Forge 연동 (이미지 생성, 모델 관리) |
| builtin-nai-bridge | NovelAI API 연동 (이미지 생성) |
| builtin-comfyui-bridge | ComfyUI 연동 (워크플로 실행) |

### 프롬프트 (prompt)

| Extension | 설명 |
|-----------|------|
| builtin-prompt-library | 프롬프트 라이브러리 및 정리 |
| builtin-prompt-syntax | 프롬프트 구문 강조 및 오류 감지 (NAI/SD/DP) |
| builtin-prompt-simulator | Dynamic Prompts 시뮬레이터, 가중치 계산, 변환 |
| builtin-sd-nai-convert | SD <-> NovelAI 프롬프트 양방향 변환 |

### AI (ai)

| Extension | 설명 |
|-----------|------|
| builtin-analysis | AI 이미지 분석 (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | WD-Tagger 자동 태깅 (ONNX + VLM 엔진) |
| builtin-ocr | VLM OCR -- 텍스트 추출, 구조화 분석, 번역 |
| builtin-clip-search | CLIP 시맨틱 이미지 검색 엔진 |
| builtin-clip-onnx | CLIP ONNX Runtime 인코더 백엔드 |
| builtin-clip-coreml | CLIP Core ML 인코더 (Apple Neural Engine) |
| builtin-hailo-semantic-search | Hailo-10H 시맨틱 검색 |
| builtin-hailo-yolo-detect | Hailo-10H YOLO 객체 감지 |
| builtin-hailo-genai | Hailo-10H GenAI (LLM/VLM/S2T) |
| builtin-speech-to-text | 음성 인식 (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | 오디오 분석 (Whisper local / OpenAI API) |
| builtin-video-analysis | 동영상 AI 분석 (multi-keyframe + Gemini) |
| builtin-inference | ONNX Runtime 프로바이더 감지 및 GPU 가속 |

### 라이브러리 (library)

| Extension | 설명 |
|-----------|------|
| builtin-favorites-manager | 즐겨찾기 및 컬렉션 관리 |
| builtin-freeze-pullback | Freeze & Pull-back 동영상 생성 (Ken Burns 효과) |
| builtin-download | 선택한 이미지의 배치 ZIP 다운로드 |
| builtin-chatlog | 채팅 로그 가져오기 및 뷰어 (Claude / ChatGPT) |
| builtin-md-viewer | Markdown 파일 뷰어 (FTS5 전문 검색) |
| builtin-cross-search | 크로스 검색 (MD, 채팅 로그, 프롬프트, 텍스트) |
| builtin-lan-share | LAN 컬렉션 공유 (시간 제한 토큰 인증) |
| builtin-stats | 통계 인사이트 (타임라인, 마일스톤) |
| builtin-trophy | 트로피 및 업적 시스템 |
| builtin-export | 내보내기 후크 (CSV 출력용 레코드 변환) |

### 시스템 (system)

| Extension | 설명 |
|-----------|------|
| builtin-auto-scan-watcher | 파일 변경 자동 감지 및 증분 업데이트 |
| builtin-mcp-client | 외부 MCP 서버 연결 관리 |
| builtin-backup | DB 백업, 복원, 스케줄러 |
| builtin-sns-share | SNS 공유 (Bluesky, X/Twitter) |
| builtin-webhook | Webhook 디스패처 (이벤트 기반 HTTP 전달) |
| builtin-debug-check | 디버그 진단 CLI |
| builtin-github-integration | GitHub Issue 모니터링・분류・PR/Discussion/Release 추적 |

## Extension 관리

설정 > Extensions 탭에서 다음 작업을 할 수 있습니다:

- **활성화/비활성화**: 스위치로 즉시 전환
- **새로 설치**: Git 리포지토리 URL을 지정하여 설치
- **마켓플레이스**: 공개 Extension 검색 및 원클릭 설치
- **업데이트**: Git 기반 Extension을 최신 버전으로 업데이트
- **제거**: 서드파티 Extension 제거

### API를 통한 관리

```bash
# Extension 목록
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# 활성화/비활성화 전환
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Git에서 설치
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension 샌드박스

서드파티 Extension은 샌드박스로 보호됩니다.

### 신뢰 수준

| 수준 | 대상 | 제한 |
|------|------|------|
| L0 (TRUSTED) | `builtin-*` | 제한 없음 |
| L2 (UNTRUSTED) | 기타 | DB/FS/네트워크 제한 적용 |

### 샌드박스 단계

1. **Capability Token**: HMAC-SHA256 서명 토큰을 통한 권한 관리. 24시간 만료
2. **SandboxedDB / SandboxedFS**: `db:read`만 있는 Extension은 SELECT 쿼리로 제한. 경로 기반 규칙으로 파일 접근 제어
3. **SandboxedHTTPClient / ImportGuard**: SSRF 방지, 런타임 import 모니터링, SHA-256 변조 감지
4. **프로세스 격리 (Linux)**: L2 Extension은 별도 프로세스에서 실행. Unix 소켓 JSON-RPC 2.0 IPC

### OS 수준 격리 (선택사항)

- **Linux**: 자동 생성 AppArmor 프로필
- **macOS**: sandbox-exec (실험적)
- **Windows**: Restricted Token + Job Object

> **팁**: Extension 개발에 대한 자세한 내용은 "Extension Development" 섹션을 참조하세요.

## 디렉토리 구조

```
extensions/builtin_<name>/
  extension.json            # 매니페스트 (이름, 버전, 권한 등)
  <name>_ext.py             # 엔트리 포인트 (get_blueprint() 노출)
  templates/<name>/          # Jinja2 템플릿
  core_impl/                 # 비즈니스 로직 (선택사항)
```

### extension.json 필수 필드

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

카테고리는 6가지 중 하나: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## Extension Module API v2 (ES Module 지원)

v4.29.0부터 Extension에서 `<script type="module">`과 Import Maps를 사용한 ES Module 임포트를 사용할 수 있습니다.

### 활성화 방법

`extension.json`에 `"script_type": "module"`을 추가합니다:

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### 사용 방법

템플릿의 `<script>`를 `<script type="module">`로 변경하고 `yu-api`에서 임포트합니다:

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast 알림
showToast('저장 완료');

// SSE 이벤트 구독
sseSubscribe('scan.progress', (data) => {
  console.log('진행:', data);
});

// i18n 번역
const label = tr('my_ext.title', 'My Extension');

// API 호출 (CSRF 헤더 자동 주입)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### 공개 API 목록

| 함수 | 설명 |
|---|---|
| `showToast(message, isError?)` | Toast 알림 표시 |
| `sseSubscribe(eventType, handler)` | SSE 이벤트 구독 |
| `sseUnsubscribe(eventType, handler)` | SSE 이벤트 구독 해제 |
| `tr(path, a?, b?)` | i18n 번역 키 해석 |
| `apiFetch(path, opts?)` | CSRF 포함 fetch 래퍼 |
| `apiUrl(path)` | API URL 빌더 |
| `escapeHtml(text)` | HTML 특수 문자 이스케이프 |

### TypeScript 타입 정의

`src/ts/extension-api/extension-api.d.ts`를 Extension 프로젝트에 복사하면 IDE 자동 완성과 타입 검사를 사용할 수 있습니다.

### 하위 호환성

`"script_type": "classic"` (기본값)인 Extension은 기존과 동일하게 `window.showToast()` 등의 전역 함수를 사용할 수 있습니다. 기존 Extension은 수정이 필요하지 않습니다.

## 개발 문서

Extension 개발에 대한 개발 인사이트, 내부 설계 결정, 알려진 주의사항, 디버깅 팁은 [MD Viewer](/ext/md-viewer/)에서 확인할 수 있습니다. `docs/development/development_docs/` 디렉토리가 등록되어 있으며 FTS5 전문 검색을 지원합니다.
