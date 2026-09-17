# Danbooru 자동 태깅 — 구현 사양

**상태**: 구현 완료 (Phase 1-5: v2.77.0)
**대상**: YU AI Manager
**목적**: WD-Tagger ONNX (CPU) + VLM (OpenAI 호환 API)의 2단계 접근으로 AI 이미지에 Danbooru 태그를 자동 부여
**구현**: `extensions/builtin_wd_tagger/core_impl/` (12개 파일), `routes/wd_tagger.py` (11개 API)

---

## 구현 현황

| 단계 | 상태 | 위치 |
|---|---|---|
| Phase 1: WD-Tagger ONNX | **완료** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2: VLM 엔진 (OpenAI 호환) | **완료** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3: 태그 후처리 | **완료** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4: 배치 API | **완료** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5: UI | **완료** | Tools 페이지 + 상세 모달 WD 태그 뱃지 + XMP 뷰어 |

### Phase 2/3 구현 개요 (v2.77.0-v2.77.1)

- **VLM 엔진** (`engine_vlm.py`): OpenAI 호환 API와 Ollama 네이티브 API 간 자동 폴백
- **복합 엔진** (`engine_composite.py`): 2단계 ONNX + VLM 파이프라인 (Mode B)
- **태그 후처리** (`tag_postprocess.py`): 정규화 (소문자, 언더스코어, 유효하지 않은 문자 제거, 중복 제거) + NSFW 필터 (~30개 태그)
- **엔진 팩토리**: `engine_type`에 따른 라우팅 ("onnx" / "vlm" / "both")
- **UI**: 엔진 타입 선택, VLM URL/모델/타임아웃 설정, 연결 테스트, NSFW 필터
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: `wd_tagger_vlm_test`, `wd_tagger_vlm_models` 도구
- **테스트 완료**: Ollama qwen2.5vl:7b로 실제 이미지 태깅 확인, 23개 단위 테스트 통과

---

## 선행 기술

### DeepDanbooru (KichangKim)
- **접근법**: 이미지 분류 모델 (TensorFlow)을 사용한 직접 태그 예측
- **장점**: 빠름, 태그 특화, ONNX 변환 가능
- **단점**: 고정 태그 세트, 새 태그에 적응 불가
- **참고**: A1111에 이미 통합됨

### WD-Tagger (SmilingWolf) — Phase 1에서 채택
- **접근법**: DeepDanbooru의 후속. SwinV2/ViT/ConvNeXt/EVA02의 4가지 아키텍처
- **장점**: DeepDanbooru보다 높은 정확도, 카테고리 분류 포함 (general/character/copyright/rating)
- **ONNX**: 공식 ONNX 모델 + `selected_tags.csv`가 HuggingFace에서 배포
- **입력**: 448x448 RGB (종횡비 유지 + 흰색 패딩)

### DanTagGen / DTG (KohakuBlueleaf)
- **접근법**: LLaMA 기반 LLM (400M)을 사용한 태그 생성 및 완성
- **장점**: 문맥 인식 태그 완성
- **단점**: LLM 추론으로 인해 느림
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### 설계 근거
이 시스템은 WD-Tagger ONNX (빠르고 안정적)와 hailo-ollama 경유 Qwen2-VL (유연하고 문맥 인식) **모두**를 지원하여, 사용자가 상황에 맞는 도구를 선택할 수 있습니다.

---

## 아키텍처

```
[이미지 입력]
    |
[엔진 선택]  (engine_factory.py)
    |-- WD-Tagger ONNX (빠름, 고정 태그 세트 ~10,000개)  [Phase 1: 구현 완료]
    |       | 신뢰도 점수 + 분류된 태그 목록
    |-- Qwen2-VL via hailo-ollama (느림, 유연, 문맥 인식)   [Phase 2]
    |       | JSON 배열 -> 태그 파싱
    |-- 2단계: ONNX -> Qwen2-VL 보완                    [Phase 2 옵션]
    |       | ONNX 태그를 프롬프트에 포함, LLM이 추가 태그 생성
    |
[후처리: 태그 정규화, NSFW 필터링]  [Phase 3]
    |
[DB: file_wd_tags 테이블에 저장]  (store.py)
[XMP: 파일에 임베드 (선택 사항)]  (xmp_write.py)
```

---

## Phase 1: WD-Tagger ONNX 엔진 — 구현 완료

**모델**: SmilingWolf/wd-swinv2-tagger-v3 (권장), ViT v3, ConvNeXt v3, EVA02-Large v3

**구현 파일** (`extensions/builtin_wd_tagger/core_impl/`):
| 파일 | 행 수 | 역할 |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | selected_tags.csv 파싱, 카테고리 매핑 |
| `model_download.py` | ~120 | HuggingFace HTTP 다운로드 |
| `engine_onnx.py` | ~150 | ONNX 추론 (448x448, BGR, 임계값 필터링) |
| `engine_factory.py` | ~50 | 엔진 캐시 + 생성 |
| `store.py` | ~130 | DB CRUD (file_wd_tags 테이블) |
| `xmp_xml.py` | ~60 | XMP 패킷 구성 |
| `xmp_read.py` | ~90 | XMP 읽기 |
| `xmp_write.py` | ~160 | PNG/JPEG/WebP에 XMP 쓰기 |
| `config_ops.py` | ~70 | config.json 읽기/쓰기 |
| `single_ops.py` | ~80 | 단일 이미지 태깅 파이프라인 |
| `batch_ops.py` | ~120 | 배치 처리 (JobManager 연동) |

**DB**: `file_wd_tags` 테이블 (스키마 v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11개 엔드포인트

---

## Phase 2: VLM 엔진 (OpenAI 호환 API) — 구현 완료 (v2.77.0)

**목적**: WD-Tagger ONNX가 포착할 수 없는 상세한 설명과 문맥적 태그를 보완
**구현**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (범용 OpenAI 호환 VLM 엔진)
**참고**: 원래 사양에서는 Hailo 전용 `engine_hailo.py`를 계획했으나, 실제 구현에서는 Ollama, hailo-ollama 및 기타 OpenAI 호환 서버를 통합적으로 처리하는 범용 엔진 `engine_vlm.py`를 사용합니다. OpenAI 호환 API (`/v1/chat/completions`)와 Ollama 네이티브 API (`/api/chat`) 간 자동 폴백을 지원합니다.

### 하드웨어 구성

| 항목 | 사양 |
|---|---|
| **디바이스** | Raspberry Pi 5 + Hailo-10H AI 가속기 |
| **메모리** | 8GB RAM |
| **VLM 모델** | **Qwen2-VL-2B-Instruct** (Hailo Model Zoo의 유일한 VLM) |
| **추론 프레임워크** | hailo-ollama (OpenAI 호환 API) |
| **엔드포인트** | `http://<pi-ip>:8000/v1/chat/completions` |

### 모델 특성

- **Qwen2-VL-2B-Instruct**: Qwen 계열의 Vision-Language 모델 (2B 파라미터)
- llava 계열이 아닌 Qwen 계열에 속합니다. 이미지 이해 정확도가 일반적으로 llava 기반 모델보다 높습니다
- 2B 파라미터로 Hailo-10H 8GB RAM에 여유 있게 들어갑니다
- 텍스트 전용 Qwen2 (1.5B)가 hailo-ollama에서 동작 확인됨
- **참고**: 2026-02 기준으로 Hailo-10H에서 사용 가능한 유일한 VLM입니다

### 프롬프트 설계

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### 구현 설계 (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100행)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME type inference
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Response format: list or {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs do not return confidence scores
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Check connectivity to the hailo-ollama server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### 동작 모드

**Mode A: Qwen2-VL 단독**
```
이미지 -> Qwen2-VL -> JSON 태그 배열 -> 정규화 -> DB 저장
```
- LLM이 이미지를 직접 분석하여 태그 생성
- 신뢰도 점수 없음 (일률적으로 0.5 설정)
- 고정 태그 세트 없이 유연한 태깅
- 속도: 이미지당 ~3-10초 (Hailo-10H 추정)

**Mode B: WD-Tagger ONNX -> Qwen2-VL 보완 (2단계)**
```
이미지 -> WD-Tagger ONNX -> 높은 신뢰도 태그 (>=0.7)
                              |
                              v
    Qwen2-VL: "이 태그들이 이미지를 설명합니다. 추가 태그를 제안하세요."
                              |
                              v
    ONNX 태그 + LLM 보완 태그 -> 병합 -> 정규화 -> DB 저장
```
- 신뢰성 있는 ONNX 태그와 LLM의 문맥 이해를 결합
- 프롬프트에 ONNX 태그를 포함하면 LLM 정확도가 향상될 것으로 예상
- 속도: ONNX (~0.5초) + LLM (~3-10초) = 이미지당 ~4-11초

**Mode B 프롬프트**:
```python
COMPLEMENT_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### engine_factory.py에 추가

```python
# engine_factory.py의 get_engine()에 추가

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # 2단계: ONNX -> Hailo 보완 (Phase 2 옵션)
    ...
```

### config.json 항목

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### 구현 전 검증 (Pi 하드웨어 테스트)

1. **hailo-ollama에서 Qwen2-VL-2B-Instruct가 실행되는지 확인**
   ```bash
   # Pi에서
   hailo-ollama run qwen2-vl:2b
   ```

2. **OpenAI 호환 API를 통한 비전 요청이 동작하는지 확인**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Danbooru 형식 JSON 출력이 안정적인지 확인**
   - hailo-ollama가 `response_format: json_object`를 지원하는지 확인
   - 미지원 시 텍스트 출력에서 정규식 기반 JSON 추출 폴백 필요

4. **실제 추론 속도 측정** — 이미지당 초 (배치 크기 계산에 필요)

---

## Phase 3: 태그 후처리 — 구현 완료 (v2.77.0)

**구현**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**통합**: `single_ops.py` / `batch_ops.py`에서 추론 후 자동 적용

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remove invalid characters
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicate and sort
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW tag list (managed in a separate file)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Phase 1과의 통합**:
- WD-Tagger ONNX는 이미 카테고리 9 (rating)를 사용하여 등급 태그를 분리
- NSFW 필터는 등급 태그 (`explicit`, `questionable`) + 추가 NSFW 목록 사용
- `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`로 구현 완료 (~80행)

---

## Phase 4: 배치 처리 API — 구현 완료

**API** (`routes/wd_tagger.py`):

| 메서드 | 경로 | 용도 |
|---|---|---|
| POST | `/api/wd-tagger/batch` | 배치 시작 (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | 단일 이미지 태깅 |
| GET | `/api/wd-tagger/tags/<file_id>` | 태그 조회 |
| DELETE | `/api/wd-tagger/tags/<file_id>` | 태그 삭제 |
| GET | `/api/wd-tagger/stats` | 통계 |
| GET | `/api/wd-tagger/untagged` | 미태깅 파일 목록 |
| GET/POST | `/api/wd-tagger/config` | 설정 CRUD |
| POST | `/api/wd-tagger/model/download` | 모델 다운로드 |
| GET | `/api/wd-tagger/model/status` | 모델 상태 |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP 읽기 |

**처리 흐름** (`batch_ops.py`):
1. `file_ids`의 파일을 순차적으로 처리 (미지정 시 `meta_source=unknown`인 미태깅 파일이 기본값)
2. 엔진을 통해 추론 실행
3. `file_wd_tags` 테이블에 UPSERT (model 컬럼으로 엔진 식별)
4. 파일에 XMP 임베드 (선택 사항)
5. JobManager를 통한 진행 상황 추적 및 취소 지원

---

## Phase 5: UI — 구현 완료

**Tools 페이지** (`templates/tools/content/primary/_wd_tagger.html`):
- 모델 선택 (4개 모델), 임계값 슬라이더 (general/character)
- XMP 쓰기 토글, 모델 다운로드 버튼
- 배치 실행 버튼 + 진행률 바
- 통계 표시 (태그 수, 카테고리별 분석, 미태깅 수)

**상세 모달**:
- WD 태그 뱃지 (general=파랑, character=초록, copyright=주황, rating=빨강)
- XMP 뷰어 버튼 (dc:subject + wdtag 네임스페이스 + 원시 XML)
- 태그 클릭으로 검색 실행

---

## 파일 구조 (현재)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # 모듈 초기화
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv 파싱
├── model_download.py        # HuggingFace 모델 다운로드
├── engine_onnx.py           # WD-Tagger ONNX 추론 [Phase 1]
├── engine_vlm.py            # VLM 엔진 (OpenAI 호환) [Phase 2: 완료]
├── engine_composite.py      # ONNX + VLM 2단계 [Phase 2: 완료]
├── engine_factory.py        # 엔진 생성 + 캐시
├── store.py                 # DB CRUD (file_wd_tags)
├── xmp_xml.py               # XMP 패킷 구성
├── xmp_read.py              # XMP 읽기
├── xmp_write.py             # XMP 쓰기 (PNG/JPEG/WebP)
├── config_ops.py            # config.json 읽기/쓰기
├── single_ops.py            # 단일 이미지 태깅 파이프라인
├── batch_ops.py             # 배치 처리 (JobManager)
├── batch_processors.py      # 배치 처리 내부 로직
└── tag_postprocess.py       # 태그 정규화, NSFW 필터 [Phase 3: 완료]

routes/wd_tagger.py          # API 엔드포인트 (11개)

src/ts/tools-page/wd-tagger/
├── core.ts                  # 설정 CRUD, 배치, 모델 다운로드
└── render.ts                # DOM 렌더링

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # 상세 모달 WD 태그 + XMP 뷰어
```

---

## 구현 우선순위 (업데이트)

```
Phase 1 (WD-Tagger ONNX)        -> 완료
Phase 4 (배치 API)              -> 완료
Phase 5 (UI)                     -> 완료
Phase 3 (후처리/NSFW)           -> 다음 (~80 추가 행)
Phase 2 (Qwen2-VL hailo-ollama) -> Pi 하드웨어 테스트 후 (~100 추가 행 + 팩토리 변경)
```

---

## 참고 자료

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API 사양: 수정된 포크 소스 참조

---

*작성: 2026-02-27 / 업데이트: 2026-02-27 (Phase 1 구현 완료, Phase 2를 Qwen2-VL 기반으로 개정)*
