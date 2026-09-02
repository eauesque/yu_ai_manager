# Collections API

컬렉션(즐겨찾기 그룹) 관리를 위한 API.

## GET /api/collections

모든 컬렉션 목록을 조회. `sort_order` 오름차순, `id` 오름차순으로 정렬.

### 파라미터

없음

### 응답

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

새로운 컬렉션을 생성.

### 속도 제한

WRITE

### 요청

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `name` | string | 예 | 컬렉션 이름 |
| `query_json` | object/null | 아니오 | 스마트 컬렉션용 쿼리. 생략 시 일반 컬렉션 |

### 응답 (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

컬렉션 이름을 변경.

### 속도 제한

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | int | 컬렉션 ID (경로 파라미터) |

### 요청

```json
{
  "name": "Renamed Collection"
}
```

### 응답

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

컬렉션을 삭제. 컬렉션 내의 모든 즐겨찾기 항목도 함께 삭제됨.

기본 컬렉션(`id=1`)은 삭제할 수 없음.

### 속도 제한

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | int | 컬렉션 ID (경로 파라미터) |

### 응답

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

컬렉션의 표시 순서를 변경.

### 속도 제한

WRITE

### 요청

```json
{
  "ids": [3, 1, 2]
}
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `ids` | int[] | 컬렉션 ID 배열. 지정된 순서가 새로운 정렬 순서가 됨 |

### 응답

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

컬렉션에 파일을 일괄 추가. 멱등성 보장: 이미 존재하는 항목은 건너뛰며 성공으로 카운트됨.

### 속도 제한

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | int | 컬렉션 ID (경로 파라미터) |

### 요청

```json
{
  "file_ids": [1, 2, 3]
}
```

| 파라미터 | 타입 | 제한 | 설명 |
|----------|------|------|------|
| `file_ids` | int[] | 최대 500건 | 추가할 파일 ID 배열 |

### 응답

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

컬렉션에서 파일을 일괄 제거.

### 속도 제한

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | int | 컬렉션 ID (경로 파라미터) |

### 요청

```json
{
  "file_ids": [1, 2]
}
```

| 파라미터 | 타입 | 제한 | 설명 |
|----------|------|------|------|
| `file_ids` | int[] | 최대 500건 | 제거할 파일 ID 배열 |

### 응답

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

컬렉션 내의 파일을 CSV 형식으로 내보내기.

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | int | 컬렉션 ID (경로 파라미터) |

### 응답

- Content-Type: `text/csv; charset=utf-8`
- CSV 컬럼: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- 컬렉션이 존재하지 않으면 404 반환
