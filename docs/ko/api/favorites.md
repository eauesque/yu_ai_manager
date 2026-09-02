# Favorites API

즐겨찾기의 추가, 제거, 확인 및 목록 조회를 위한 API입니다.

## POST /api/favorites/toggle

파일의 즐겨찾기 상태를 전환합니다. 즐겨찾기에 포함되어 있지 않으면 추가하고, 이미 포함되어 있으면 제거합니다.

- **속도 제한**: WRITE

### 요청 본문

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 대상 파일 ID (양의 정수) |
| `collection_id` | int | 아니오 | 컬렉션 ID (기본값: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### 응답

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `file_id` | int | 대상 파일 ID |
| `collection_id` | int | 컬렉션 ID |
| `favorited` | bool | 전환 후 상태. `true` = 추가됨, `false` = 제거됨 |

## GET /api/favorites/check

지정한 파일 ID 중 즐겨찾기에 포함된 항목을 반환합니다.

### 매개변수

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `ids` | string | 예 | 쉼표로 구분된 파일 ID (예: `1,2,3`) |
| `collection_id` | int | 아니오 | 특정 컬렉션으로 필터링 |

### 응답

```json
{
  "favorites": [1, 3]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `favorites` | int[] | 즐겨찾기에 포함된 파일 ID 배열 |

## GET /api/favorites/check_collections

지정한 파일이 포함된 컬렉션 ID 목록을 반환합니다.

### 매개변수

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 대상 파일 ID |

### 응답

```json
{
  "collections": [1, 3]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `collections` | int[] | 이 파일을 포함하는 컬렉션 ID 배열 |

## GET /api/favorites/list

즐겨찾기 파일 ID 목록을 조회합니다. 결과는 추가 날짜 내림차순으로 정렬되며, 논리 삭제된 파일은 제외됩니다.

### 매개변수

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `collection_id` | int | 아니오 | 특정 컬렉션으로 필터링 |

### 응답

```json
{
  "ids": [42, 55, 67]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ids` | int[] | 즐겨찾기 파일 ID 배열 (`added_at` 내림차순) |
