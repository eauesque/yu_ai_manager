# Video Analysis API

동영상 분석 설정 관리 및 상태 확인을 위한 API입니다. 동영상 파일에서 키프레임을 추출하는 설정을 제어합니다.

## GET /api/video-analysis/config

현재 동영상 분석 설정을 가져옵니다. 저장된 설정과 기본값을 병합한 결과를 반환합니다.

### Parameters

없음

### Response

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `enabled` | boolean | `true` | 동영상 분석 활성화 여부 |
| `keyframe_count` | int | `4` | 추출할 키프레임 수 (1-16) |
| `strategy` | string | `"uniform"` | 키프레임 추출 전략. `uniform` (균등 간격), `scene` (장면 전환 감지), `single` (단일 프레임만) |
| `scene_threshold` | float | `0.4` | 장면 전환 감지 임계값 (0.0-1.0). `strategy`가 `scene`일 때 사용 |
| `store_per_keyframe` | boolean | `false` | 각 키프레임을 개별 저장할지 여부 |

## POST /api/video-analysis/config

동영상 분석 설정을 저장합니다. 지정된 필드만 업데이트되며, 생략된 필드는 기존 값을 유지합니다.

### Rate Limit

WRITE

### Request

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

모든 필드는 선택 사항입니다. 지정된 필드만 업데이트됩니다.

| 매개변수 | 타입 | 필수 | 제약 조건 | 설명 |
|----------|------|------|-----------|------|
| `enabled` | boolean | 아니오 | - | 동영상 분석 활성화 여부 |
| `keyframe_count` | int | 아니오 | 1-16 | 추출할 키프레임 수 |
| `strategy` | string | 아니오 | `uniform`, `scene` 또는 `single` | 키프레임 추출 전략 |
| `scene_threshold` | float | 아니오 | 0.0-1.0 | 장면 전환 감지 임계값 |
| `store_per_keyframe` | boolean | 아니오 | - | 각 키프레임을 개별 저장할지 여부 |

### Response

저장 후 병합된 설정을 반환합니다 (GET과 동일한 형식).

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Errors

| 상태 코드 | Code | 조건 |
|-----------|------|------|
| 400 | `invalid_json` | 요청 본문이 JSON 객체가 아님 |
| 400 | `invalid_value` | 유효성 검사 오류 (잘못된 타입, 범위 초과 값, 유효하지 않은 전략 등) |

## GET /api/video-analysis/status

동영상 분석 상태 정보를 가져옵니다. ffmpeg 사용 가능 여부, 동영상 파일 수, 키프레임이 추출된 파일 수를 반환합니다.

### Parameters

없음

### Response

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ffmpeg` | boolean | 시스템에서 ffmpeg 사용 가능 여부 |
| `video_files` | int | 데이터베이스의 총 동영상 파일 수 (소프트 삭제 제외). 지원 확장자: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | 키프레임이 추출된 파일 수 |
