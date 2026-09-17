# Events API (SSE)

Server-Sent Events를 통한 실시간 이벤트 전달입니다.

## GET /api/events/stream

메인 이벤트 스트림입니다. 모든 페이지가 단일 연결을 공유합니다.

### 연결

```javascript
// TypeScript 모듈에서
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// 템플릿 인라인 스크립트에서
window.sseSubscribe('scan.complete', (data) => { ... });
```

**중요**: `new EventSource()`를 직접 사용하지 마십시오. `window.EventSource`는 Proxy로 덮어쓰여져 있어 직접 사용 시 오류가 발생합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `types` | string | 구독할 이벤트 타입 (쉼표 구분; 생략 시 모든 이벤트) |

### 연결 제한

- IP당 최대 10개 동시 연결
- 가시성 인식: 탭이 숨겨지면 연결이 절전 상태로 전환됩니다
- 지수 백오프를 사용한 자동 재연결

## 이벤트 타입

### 스캔

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | 스캔 진행 상황 |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | 스캔 완료 |
| `config.scan_roots_changed` | `{}` | 스캔 루트 변경 알림 |

### 즐겨찾기 및 컬렉션

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | 즐겨찾기 추가 |
| `favorite.remove` | `{ file_id, collection_id }` | 즐겨찾기 삭제 |
| `collection.create` | `{ id, name }` | 컬렉션 생성 |
| `collection.delete` | `{ id }` | 컬렉션 삭제 |

### AI 분석 및 태깅

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | CLIP 인덱싱 시작 |
| `semantic_index.progress` | `{ done, total }` | CLIP 인덱싱 진행 상황 |
| `semantic_index.complete` | `{ indexed }` | CLIP 인덱싱 완료 |
| `vlm_caption.start` | `{ total }` | VLM 캡셔닝 시작 |
| `vlm_caption.progress` | `{ done, total }` | VLM 캡셔닝 진행 상황 |
| `vlm_caption.complete` | `{ processed }` | VLM 캡셔닝 완료 |
| `yolo_detect.start` | `{ total }` | YOLO 감지 시작 |
| `yolo_detect.progress` | `{ done, total }` | YOLO 감지 진행 상황 |
| `yolo_detect.complete` | `{ detected }` | YOLO 감지 완료 |

### Freeze & Pull-back

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | 작업 시작 |
| `fpb.progress` | `{ job_id, frame, total }` | 프레임 진행 상황 |
| `fpb.complete` | `{ job_id, output_path }` | 작업 완료 |
| `fpb.error` | `{ job_id, error }` | 작업 오류 |

### 채팅 로그

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | AI 재처리 시작 |
| `chatlog_reprocess.progress` | `{ done, total }` | AI 재처리 진행 상황 |
| `chatlog_reprocess.complete` | `{ processed }` | AI 재처리 완료 |
| `chatlog_reprocess.error` | `{ error }` | AI 재처리 오류 |

### 스케줄러

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | 예약 작업 완료 |
| `scheduler.job_error` | `{ job_id, error }` | 예약 작업 오류 |

## GET /api/logs/stream

서버 로그 전용 SSE 스트림입니다. 메인 스트림과 독립적으로 동작합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `level` | string | 최소 로그 레벨 (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### 이벤트

| 이벤트 | 데이터 | 설명 |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | 로그 항목 |

### 연결 제한

- IP당 최대 3개 동시 연결 (메인 스트림과 별도)
- 15초 하트비트 간격 (`: heartbeat\n\n`)
