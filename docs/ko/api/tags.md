# Tags API

태그 일괄 조작 및 태그 제안/자동완성 관련 API.

## POST /api/tags/batch-set

여러 파일에 대해 태그를 일괄 추가 또는 삭제합니다.

### 속도 제한

WRITE (약 120 req/min, 버스트 30)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `items` | array | 예 | 작업 목록 (최대 500건) |
| `items[].file_id` | int | 예 | 파일 ID (양의 정수) |
| `items[].add` | string[] | 아니오 | 추가할 태그 이름 |
| `items[].remove` | string[] | 아니오 | 삭제할 태그 이름 |

- 각 항목에는 `add` 또는 `remove` 중 최소 하나가 필요합니다
- 존재하지 않는 태그는 자동으로 생성됩니다 (namespace=null)
- API를 통해 추가된 태그의 source는 `"user"`로 설정됩니다
- 고아 태그 (연결된 파일이 없는 태그)는 자동으로 삭제됩니다

### 요청 예시

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### 응답

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `total` | int | 처리된 총 건수 |
| `succeeded` | int | 성공한 건수 |
| `failed` | int | 실패한 건수 |
| `errors` | array | 오류 상세 목록 |

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 잘못된 요청 본문 (items가 비어 있음, file_id가 유효하지 않음, add와 remove 모두 누락 등) |
| 429 | 속도 제한 초과 |

---

## GET /api/tags/suggest

검색 문자열에 부분 일치하는 태그 후보를 반환합니다. 자동완성용입니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `q` | string | 예 | 검색 문자열 |
| `limit` | int | 아니오 | 반환 결과의 상한 (기본값: 20, 최대: 100) |

- 검색은 대소문자를 구분하지 않습니다 (LIKE %q%)
- 결과는 `file_count` 내림차순으로 정렬됩니다
- `q`가 비어 있으면 빈 배열을 반환합니다

### 응답

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `data[].id` | int | 태그 ID |
| `data[].tag` | string | 태그 이름 |
| `data[].namespace` | string\|null | 네임스페이스 (보통 null) |
| `data[].file_count` | int | 이 태그가 연결된 파일 수 |
