# Files API

파일 상세정보, 썸네일, 원본 미디어 조회를 위한 API입니다.

## GET /api/file/<id>

파일의 상세 메타데이터를 조회합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `id` | int | 파일 ID (경로 파라미터) |

### 응답

```json
{
  "id": 42,
  "path": "/images/output/00042.png",
  "filename": "00042.png",
  "size": 1234567,
  "mtime": 1709500000,
  "width": 1024,
  "height": 1536,
  "meta_type": "a1111_png",
  "model_name": "animagine-xl-3.1",
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

썸네일 이미지 (WebP)입니다. ETag 캐싱을 지원합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `id` | int | 파일 ID |
| `size` | int | 썸네일 크기 (기본값 300) |

### 응답

- Content-Type: `image/webp`
- ETag / If-None-Match 지원 (304 Not Modified)
- 캐시: 24시간

## GET /api/original/<id>

원본 파일을 스트리밍합니다. ZIP 아카이브 내부의 파일도 지원합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `id` | int | 파일 ID |

### 응답

- Content-Type: 파일의 MIME 타입
- Content-Disposition: `inline`
- Range 요청 지원 (동영상 탐색용)

## POST /api/convert

프롬프트 형식 변환 (A1111 <-> NAI)입니다.

### 요청

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### 응답

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

컨테이너(폴더/ZIP)의 썸네일 ID 목록으로, 이미 캐시된 항목은 제외됩니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `keys` | string | 컨테이너 키 (쉼표 구분) |
