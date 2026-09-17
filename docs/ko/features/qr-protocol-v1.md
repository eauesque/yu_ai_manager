# YU QR Protocol v1 — 통합 페이로드 사양

**버전:** 1.0
**날짜:** 2026-02-23
**대상 애플리케이션:** YU AI Manager (TagDB)

---

## 개요

YU AI Manager는 QR 코드를 통한 프롬프트 공유 및 오류 진단을 지원합니다.
이 문서는 QR 페이로드 형식의 통합 사양을 제공합니다.

### 사용 라이브러리

| 용도 | 라이브러리 | 버전 |
|------|-----------|-----------|
| QR 생성 | QRCode.js | 1.0.0 |
| QR 읽기 | jsQR | 1.4.0 |

### QR 용량 제한

- 최대 문자 수: **2,953** (오류 정정 레벨 M)
- 2,500자 초과: 메타 JSON을 축소하여 재시도
- 2,953자 초과: 오류 (`qr.info.too_long`)

---

## 페이로드 타입 1 — 프롬프트 공유

### 출처

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON 스키마

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### 필드 정의

| 키 | 타입 | 필수 | 설명 | 제한 |
|------|-----|------|------|------|
| `v` | string | 필수 | 프로토콜 버전. 현재 `"1.0"` | — |
| `t` | string | 필수 | 페이로드 타입. 현재 항상 `"prompt"` | — |
| `p` | string | 필수 | 포지티브 프롬프트 | 2,000자 |
| `n` | string | 필수 | 네거티브 프롬프트 | 1,000자 |
| `src` | string | 필수 | 발급자 식별자. 현재 항상 `"TagDB"` | — |
| `m` | string | — | 모델 이름 | — |
| `s` | string | — | 시드 값 | — |
| `st` | string | — | 스텝 수 | — |
| `cfg` | string | — | CFG 스케일 | — |
| `sa` | string | — | 샘플러 이름 | — |
| `sz` | string | — | 이미지 크기 (`"WxH"` 형식) | — |

---

## QR 모드 — 4가지 유형

### `positive` 모드

```
qrText = shareData.p
```

- 내용: 포지티브 프롬프트 텍스트만
- 용도: 프롬프트의 직접 텍스트 공유

### `negative` 모드

```
qrText = shareData.n
```

- 내용: 네거티브 프롬프트 텍스트만

### `meta` 모드

```
qrText = JSON.stringify(shareData, null, 0)
```

- 내용: 전체 Prompt Share JSON 페이로드 (압축)
- 2,500자 초과 시 정렬된 `JSON.stringify`로 폴백

### `url` 모드

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- 내용: YU AI Manager 공유 페이지 URL
- localhost (`localhost` / `127.0.0.1`)에서는 비활성화

---

## 페이로드 타입 2 — 오류 진단

### 출처

- HTTP 오류 시 생성 -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON 스키마

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### 필드 정의

| 키 | 타입 | 설명 | 제한 |
|------|-----|------|------|
| `s` | string | HTTP 상태 코드 (`"404"`, `"500"` 등) | — |
| `p` | string | 요청 경로 | 80자 |
| `v` | string | 애플리케이션 버전 (`APP_VERSION` 파일에서) | — |

---

## URL 공유 디코딩 절차

공유 페이지 (`/share?data=...`)에서의 디코딩:

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## QR 생성 파라미터

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 오류 페이지에서는 180
  height:       200,   // 오류 페이지에서는 180
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% 오류 정정
});
```

---

## 향후 확장 (v1.x)

| 기능 | 상태 | 비고 |
|------|------|------|
| 컬렉션 QR 내보내기 (여러 이미지) | 미구현 | 페이로드 타입 3으로 예정 |
| `t: "collection"` 타입 | 미정의 | 파일 ID 목록 + 컬렉션 이름 |
| 압축 (gzip + Base64) | 미구현 | 2,953자 초과 프롬프트의 대안 |

---

## 구현 파일

| 파일 | 역할 |
|----------|------|
| `routes/share.py` | 공유 API Blueprint |
| `routes/share_ops/payload_build.py` | 페이로드 생성 |
| `routes/share_ops/prompt_extract.py` | 프롬프트 데이터 추출 |
| `core/web/app_factory_handlers.py` | 오류 QR 데이터 생성 |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | QR 빌드 및 렌더링 |
| `static/js/runtime/tools/runtime-tools-qr.js` | QR UI 핸들러 |
| `static/js/share/share-qr.js` | QR 이미지 디코딩 |
| `static/js/share/share-page.js` | 공유 페이지 표시 |
| `static/vendor/qrcode.min.js` | QRCode.js 라이브러리 |
| `static/vendor/jsQR.min.js` | jsQR 라이브러리 |
