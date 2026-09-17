# 드래그 & 드롭 파일 등록

메인 라이브러리 페이지(`/`)에 이미지/동영상 파일을 드래그 & 드롭하면 설정된
**Drop Inbox** 디렉터리에 저장하고 라이브러리에 자동 등록합니다. 일반 스캔
경로(`scan_one`)를 사용하므로 메타데이터 추출, 썸네일 생성, 태그 처리가
정상적으로 수행됩니다.

## 동작

1. 메인 페이지를 연 상태에서 파일 탐색기나 다른 브라우저에서 파일을 드래그
2. 창 위에 오버레이가 표시되고 대상(Drop Inbox) 경로가 표시됩니다
3. 드롭하면 각 파일이 Drop Inbox에 복사되고 라이브러리에 등록됩니다
4. 토스트에 성공/실패 개수가 표시됩니다

## Drop Inbox 결정 로직

Drop Inbox는 다음 우선순위로 결정됩니다:

1. `config.json`의 `drop_inbox_dir`(명시적 설정)
2. 설정되지 않은 경우: 활성화된 첫 번째 스캔 루트를 그대로 사용

**제약**: `drop_inbox_dir`는 반드시 `scan_roots` 항목 중 하나의 하위에
있어야 합니다. 외부 디렉터리는 HTTP 400으로 거부됩니다. 이는 "스캔 루트 =
라이브러리 파일의 단일 진실 공급원"이라는 불변 조건을 유지하기 위함입니다.

## 설정 예시

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

`drop_inbox_dir`이 존재하지 않으면 자동으로 생성됩니다(상위 디렉터리는
여전히 `scan_roots` 하위에 있어야 함).

## 파일명 충돌 처리

같은 이름의 파일이 이미 존재하는 경우, 자동으로 `_1`, `_2` 등의 접미사를
붙여 저장합니다. 기존 파일을 덮어쓰지 않습니다.

## 허용된 확장자

| 카테고리 | 확장자 |
|---|---|
| 이미지 | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| 동영상 | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

압축파일(`.zip` / `.7z` / `.rar`)은 **드래그 & 드롭 대상이 아닙니다**. 압축
파일은 스캔 루트에 직접 배치하고 일반 스캔을 실행해 주세요.

## 제한 사항

- 단일 요청의 총 크기 상한은 `MAX_CONTENT_LENGTH`(기본 **100 MB**)
- 경로 탐색(`..`) 포함 파일명은 거부됩니다
- 현재 디렉터리 전체 드롭은 지원하지 않습니다(개별 파일만)

## HTTP API

### `POST /api/dnd-upload`

multipart로 여러 파일을 받아 Drop Inbox에 저장하고 라이브러리에 등록합니다.

### `GET /api/dnd-inbox`

UI 오버레이 표시용으로 현재 해결된 Drop Inbox 정보를 반환합니다.

### `POST /api/files/register-path`

이미 디스크에 있는 파일을 경로 지정으로 등록합니다(업로드 불필요). 경로는
`scan_roots` 하위여야 합니다. MCP 도구 `register_file`도 이 API를 사용합니다.

## MCP 도구

| 도구 | 설명 |
|---|---|
| `register_file(path)` | 절대 경로로 파일을 라이브러리에 등록 |
| `drop_inbox_info()` | 현재 해결된 Drop Inbox 디렉터리 조회 |
