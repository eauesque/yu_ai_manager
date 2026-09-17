# SVG 래스터화 API

SVG 벡터 이미지를 PNG/WebP 비트맵으로 변환하는 API입니다.
img2img 파이프라인 통합을 위해 설계되었으며, 반환되는 base64 이미지 데이터를 NovelAI Bridge 또는 SD WebUI Bridge에 직접 전달할 수 있습니다.

## GET /api/svg/info

SVG 래스터화 기능의 사용 가능 여부를 확인합니다.

- **속도 제한**: 없음 (GET)

### 응답

```json
{
  "available": true,
  "backend": "resvg"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `available` | bool | 래스터화 가능 여부 |
| `backend` | string \| null | 사용 중인 백엔드 (`"resvg"` 또는 `null`) |

---

## POST /api/svg/rasterize

SVG를 래스터화하여 PNG/WebP 비트맵을 반환합니다.

- **속도 제한**: HEAVY

### 요청 본문

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | ※1 | 데이터베이스의 SVG 파일 ID |
| `svg_path` | string | ※1 | SVG 파일의 절대 경로 |
| `svg_data` | string | ※1 | 인라인 SVG XML 문자열 |
| `width` | int | 아니오 | 출력 너비 (기본값: 1024) |
| `height` | int | 아니오 | 출력 높이 (기본값: 1024) |
| `format` | string | 아니오 | `"png"` 또는 `"webp"` (기본값: `"png"`) |
| `background` | string | 아니오 | 배경색 (예: `"#ffffff"`). 미지정 시 투명 |

> ※1: `file_id`, `svg_path`, `svg_data` 중 하나를 제공해 주세요.

### 요청 예시

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### 응답

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | bool | 성공 플래그 |
| `base64` | string | Base64 인코딩된 PNG/WebP 데이터 |
| `width` | int | 실제 출력 너비 |
| `height` | int | 실제 출력 높이 |
| `format` | string | 출력 형식 |
| `size_bytes` | int | 바이너리 크기 (bytes) |

### 에러 응답

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## MCP 통합

Claude Desktop에서 SVG → img2img 파이프라인을 구축할 수 있습니다:

```
# 단계 1: SVG 래스터화
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# 단계 2: 반환된 base64를 img2img에 전달
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP 도구

| 도구 | 설명 |
|------|------|
| `svg_info` | 래스터화 기능 사용 가능 여부 확인 |
| `svg_rasterize` | SVG → PNG/WebP 래스터화 |

---

## 의존 패키지

| 패키지 | 라이선스 | 용도 |
|--------|----------|------|
| `resvg` | MIT | Rust 기반 SVG 렌더러 (크로스 플랫폼) |

`resvg`가 미설치된 경우 썸네일은 플레이스홀더로 표시되며, API는 HTTP 501을 반환합니다.

```bash
pip install resvg
```
