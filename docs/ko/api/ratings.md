# Ratings API

파일 평점(1–5 별점)의 설정, 조회, 통계에 관한 API입니다.

## POST /api/ratings/set

파일에 평점을 설정합니다. `rating=0`을 지정하면 평점을 초기화합니다.

**속도 제한**: WRITE

### 요청

```json
{
  "file_id": 42,
  "rating": 5
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (양의 정수) |
| `rating` | int | 예 | 평점 값 (0–5). 0은 평점 초기화 |

### 응답

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

여러 파일의 평점을 일괄 설정합니다.

**속도 제한**: WRITE

### 요청

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `items` | array | 예 | 평점 설정 목록 (최대 500건) |
| `items[].file_id` | int | 예 | 파일 ID (양의 정수) |
| `items[].rating` | int | 예 | 평점 값 (0–5) |

### 응답

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

파일의 평점을 조회합니다. 평점이 없는 파일은 `rating: 0`을 반환합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (쿼리 파라미터) |

### 응답

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **참고**: 평점이 없는 파일은 `rating: 0`을 반환합니다.

## POST /api/ratings/batch

여러 파일의 평점을 일괄 조회합니다.

### 요청

```json
{
  "file_ids": [1, 2, 3]
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_ids` | array | 예 | 파일 ID 목록 |

### 응답

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **참고**: 평점이 설정된 파일만 맵에 포함됩니다. 평점이 없는 파일은 응답에서 제외됩니다.

## GET /api/ratings/stats

전체 파일의 평점 통계를 조회합니다.

### 파라미터

없음.

### 응답

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `total_rated` | int | 평점이 설정된 파일의 총 수 |
| `distribution` | object | 각 평점 값(1–5)별 파일 수 |
