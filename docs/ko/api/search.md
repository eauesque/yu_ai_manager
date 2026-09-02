# Search API

파일 검색, 제안, 그룹 표시를 위한 API입니다.

## GET /api/search

메인 파일 검색 엔드포인트입니다.

### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `q` | string | `""` | 검색 쿼리 (프롬프트 내 텍스트, 태그명) |
| `sort` | string | `"date"` | 정렬 순서: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | 페이지네이션 시작 위치 |
| `limit` | int | `50` | 결과 수 (최대 200) |
| `cursor` | string | - | 커서 기반 페이지네이션용 토큰 |
| `meta` | string | `"all"` | 메타데이터 유형: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | 태그 필터 (쉼표 구분) |
| `rating_min` | int | - | 최소 평점 (0-5) |
| `rating_max` | int | - | 최대 평점 (0-5) |
| `path` | string | - | 경로 접두사 필터 |
| `ext` | string | - | 확장자 필터 (쉼표 구분, 예: `png,webp`) |
| `has_prompt` | bool | - | 프롬프트 유무 필터 |
| `collection_id` | int | - | 컬렉션 내 검색 |
| `favorites_only` | bool | `false` | 즐겨찾기만 |
| `group_by` | string | - | 그룹화: `folder`, `conversation` |

### 응답

```json
{
  "results": [
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
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

폴더/ZIP별로 그룹화된 검색 결과입니다.

### 파라미터

`/api/search`와 동일한 쿼리 파라미터에 추가:

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `group_limit` | int | 그룹당 최대 표시 항목 수 |

## GET /api/groups-index

폴더 및 ZIP 컨테이너 그룹의 인덱스입니다. 검색 결과 그룹화에 사용됩니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `sort` | string | 정렬 순서: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | 페이지네이션 시작 위치 |
| `limit` | int | 결과 수 |

## GET /api/group-members

지정된 컨테이너 내의 파일 ID 목록입니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | string | 컨테이너 키 (폴더 경로 또는 ZIP 경로) |

## GET /api/suggest

태그 및 프롬프트 자동완성입니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `q` | string | 입력 텍스트 |
| `limit` | int | 제안 수 (기본값 10) |

### 응답

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA 모델명 제안입니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `q` | string | 입력 텍스트 |
| `limit` | int | 제안 수 |

## GET /api/server-info

기본 서버 정보입니다.

### 응답

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
