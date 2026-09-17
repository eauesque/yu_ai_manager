# OCR API

이미지, 동영상 및 PDF에서 텍스트를 추출(OCR)하는 API이며, 번역, 오버레이 이미지 생성, 내보내기, 벤치마크 및 엔진 관리 기능도 제공합니다.

## POST /api/ocr/<file_id>

단일 파일에 대해 OCR을 실행하고 결과를 데이터베이스에 저장합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | OCR 작업 유형. `ocr` / `ocr_document` / `ocr_manga` 중 하나. 기본값: `ocr` |
| `language` | string | 아니오 | 언어 힌트. 기본값: `auto` |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID. 생략 시 자동 선택 |

### 응답 (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### 오류

- `400` -- 유효하지 않은 작업 값
- `404` -- 파일을 찾을 수 없음
- `500` -- OCR 엔진 해석 실패 / OCR 실행 오류

---

## GET /api/ocr/result/<file_id>

저장된 OCR 결과를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | 작업 유형으로 필터링 |
| `engine` | string | 아니오 | 엔진 이름으로 필터링 |
| `all` | string | 아니오 | 임의의 값을 설정하면 모든 결과를 반환 |

### 응답 (결과 있음)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### 응답 (`?all=1` 사용 시)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### 응답 (결과 없음)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

저장된 OCR 결과를 삭제합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "",
  "engine": ""
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | 작업 유형으로 필터링. 빈 문자열은 모든 작업 대상 |
| `engine` | string | 아니오 | 엔진 이름으로 필터링. 빈 문자열은 모든 엔진 대상 |

### 응답

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

여러 파일에 대해 배치 OCR을 실행합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| 파라미터 | 타입 | 필수 | 제한 | 설명 |
|----------|------|------|------|------|
| `file_ids` | int[] | 예 | 최대 500 | 대상 파일 ID 배열 |
| `task` | string | 아니오 | -- | OCR 작업 유형. `ocr` / `ocr_document` / `ocr_manga`. 기본값: `ocr` |
| `language` | string | 아니오 | -- | 언어 힌트. 기본값: `auto` |
| `server_id` | string | 아니오 | -- | 사용할 분석 서버 ID |

### 응답 (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### 오류

- `400` -- `file_ids`가 비어 있음 / 500 초과 / 유효하지 않은 작업 값
- `500` -- OCR 엔진 해석 실패

---

## POST /api/ocr/video/<file_id>

동영상 파일에서 키프레임을 추출하고 각 프레임에 대해 OCR을 실행합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | OCR 작업 유형. 기본값: `ocr` |
| `language` | string | 아니오 | 언어 힌트. 기본값: `auto` |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID |
| `keyframe_count` | int | 아니오 | 추출할 키프레임 수. 범위: 1-16. 기본값: `4` |
| `strategy` | string | 아니오 | 키프레임 추출 전략. 기본값: `uniform` |

### 응답 (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### 오류

- `400` -- 파일이 동영상이 아님
- `404` -- 파일을 찾을 수 없음
- `500` -- OCR 엔진 해석 실패 / 동영상 OCR 실행 오류

---

## POST /api/ocr/pdf/<file_id>

PDF 페이지를 이미지로 변환하고 OCR을 실행합니다. 텍스트 레이어가 없는 스캔 PDF에 유용합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | OCR 작업 유형. 기본값: `ocr_document` |
| `language` | string | 아니오 | 언어 힌트. 기본값: `auto` |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID |
| `page_range` | string | 아니오 | 페이지 범위 (예: `"1-5"`, `"1,3,5"`). 빈 문자열은 전체 페이지 |
| `dpi` | int | 아니오 | 렌더링 해상도. 범위: 72-400. 기본값: `200` |

### 응답 (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### 오류

- `400` -- 파일이 PDF가 아님
- `404` -- 파일을 찾을 수 없음
- `500` -- OCR 엔진 해석 실패 / PDF OCR 실행 오류

---

## POST /api/ocr/bbox/<file_id>

기존 OCR 결과의 텍스트 바운딩 박스를 감지합니다. 이전에 추출된 텍스트 영역에 위치 정보를 추가하는 2단계 처리로 사용됩니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "",
  "server_id": ""
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `task` | string | 아니오 | 대상 OCR 작업 유형 |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID |

### 응답 (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### 오류

- `400` -- 텍스트 영역을 찾을 수 없음 / VLM 엔진 필요
- `404` -- OCR 결과를 찾을 수 없음 (먼저 OCR을 실행하세요) / 파일을 찾을 수 없음
- `500` -- OCR 엔진 해석 실패 / 바운딩 박스 감지 오류

---

## GET /api/ocr/engines

사용 가능한 OCR 엔진 (분석 서버)과 작업별 점수를 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

NPU(Neural Processing Unit) 장치 상태 및 권장 최적화 설정을 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `task` | string | 아니오 | 최적화 권장 사항의 작업 유형. 기본값: `ocr` |

### 응답

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

기존 OCR 결과를 지정된 언어로 번역합니다. 번역 결과는 데이터베이스에 저장됩니다.

### Rate Limit

WRITE

### 요청

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `target_lang` | string | 예 | 대상 언어 코드 (예: `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID |
| `task` | string | 아니오 | 대상 OCR 작업 유형 |

### 응답 (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### 오류

- `400` -- `target_lang` 미지정
- `404` -- OCR 결과를 찾을 수 없음
- `500` -- 번역 실행 오류

---

## GET /api/ocr/translations/<file_id>

파일의 번역 결과 목록을 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `target_lang` | string | 아니오 | 언어 코드로 필터링 |

### 응답

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

OCR 결과(또는 번역)를 원본 이미지 위에 렌더링한 오버레이 이미지를 생성합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `mode` | string | 아니오 | 표시 모드. `translated` / `original` / `both`. 기본값: `translated` |
| `target_lang` | string | 아니오 | 번역 언어로 필터링 |
| `format` | string | 아니오 | 출력 이미지 형식. `png` / `jpeg`. 기본값: `png` |
| `task` | string | 아니오 | 대상 OCR 작업 유형 |

### 응답

- Content-Type: `image/png` 또는 `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### 오류

- `400` -- 유효하지 않은 모드 / 형식 값
- `404` -- OCR 결과를 찾을 수 없음 / 파일을 찾을 수 없음
- `500` -- 오버레이 이미지 생성 오류

---

## GET /api/ocr/export/<file_id>

지정된 형식으로 OCR 결과를 내보내어 다운로드합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `format` | string | 아니오 | 내보내기 형식. `txt` / `md` / `json` / `pdf`. 기본값: `md` |
| `task` | string | 아니오 | 대상 OCR 작업 유형 |
| `include_translation` | string | 아니오 | 임의의 값을 설정하면 번역 포함 |
| `target_lang` | string | 아니오 | 포함할 번역 언어 코드 |

### 응답

- Content-Type: 형식에 적합한 MIME 타입
- Content-Disposition: `attachment; filename=...`

### 오류

- `400` -- 유효하지 않은 형식 값
- `404` -- OCR 결과를 찾을 수 없음

---

## POST /api/ocr/export/batch

여러 파일의 OCR 결과를 일괄 내보냅니다. ZIP 다운로드 또는 서버 측 직접 저장을 지원합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_ids` | int[] | 예 | 대상 파일 ID 배열 |
| `format` | string | 아니오 | 내보내기 형식. `txt` / `md` / `json` / `pdf` / `overlay`. Extension 설정에서 기본값 가져옴 |
| `output_dir` | string | 아니오 | 서버 측 저장 절대 경로. 생략 시 ZIP 다운로드 반환 |
| `overlay_mode` | string | 아니오 | 오버레이 모드 (`format=overlay` 시). `translated` / `original` / `both`. 기본값: `translated` |
| `target_lang` | string | 아니오 | 번역 언어 코드 |
| `include_translation` | bool | 아니오 | 번역 포함 여부. 기본값: `false` |

### 응답 (ZIP 다운로드)

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip` (텍스트 형식) 또는 `ocr_overlay_batch.zip` (오버레이 형식)

### 응답 (서버 측 저장)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### 오류

- `400` -- `file_ids`가 비어 있음 / 유효하지 않은 형식 값 / `output_dir`이 절대 경로가 아님
- `403` -- `output_dir`이 금지된 디렉토리
- `404` -- OCR 결과를 찾을 수 없음

---

## POST /api/ocr/benchmark

OCR 벤치마크를 실행하여 정확도와 성능을 측정합니다. 벤치마크 케이스 (이미지 + 정답 텍스트 쌍)가 필요합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `task` | string | 아니오 | 벤치마크할 작업 유형. 기본값: `ocr` |
| `server_id` | string | 아니오 | 사용할 분석 서버 ID |
| `benchmark_dir` | string | 아니오 | 벤치마크 케이스 디렉토리 경로. 기본값: `extensions/builtin_ocr/benchmarks/` |

### 응답 (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### 오류

- `404` -- 벤치마크 케이스를 찾을 수 없음
- `500` -- OCR 엔진 해석 실패 / 벤치마크 실행 오류

---

## GET /api/ocr/benchmark/cases

사용 가능한 벤치마크 케이스를 나열합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `dir` | string | 아니오 | 벤치마크 케이스 디렉토리 경로 |

### 응답

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

작업별 점수 설정이 포함된 OCR 모델 Profile을 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

URL에서 커뮤니티 게시 모델 Profile을 가져와 병합합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `url` | string | 예 | Profile JSON의 URL |

### 응답 (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### 오류

- `400` -- `url` 미지정
- `500` -- 가져오기 또는 병합 실패

---

## PUT /api/ocr/profiles/<model_prefix>

모델 Profile의 점수를 수동으로 업데이트합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `model_prefix` | string | 예 | 모델 이름 접두사 (경로 파라미터) |
| `scores` | object | 예 | 작업 유형을 키로, 점수(정수)를 값으로 하는 객체 |

### 응답

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### 오류

- `400` -- `scores` 미지정
