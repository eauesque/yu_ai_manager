# Hailo-10H Semantic Search — 개발 로그

**프로젝트**: YU AI Manager — Hailo-10H CLIP 시맨틱 이미지 검색
**목표**: Raspberry Pi 5 + AI HAT 2 (Hailo-10H)에서 CLIP 기반의 자연어 이미지 검색을 실현하기
**시작일**: 2026-03-01
**상태**: Phase 1-8 완료, Phase 9-12 (VLM 캡션 연동, 동영상 S2T, LLM 멀티턴, OpenAI 호환 API) 완료

---

## 이 프로젝트가 중요한 이유

Hailo-10H (AI HAT 2)는 2025년 말에 출시된 비교적 새로운 엣지 AI 가속기로,
Raspberry Pi 5의 M.2 슬롯에 장착하여 사용한다. 40 TOPS의 추론 성능을 갖추고 있지만,
**실용적인 애플리케이션에서의 사용 사례는 아직 거의 공개되지 않았다**.

이 프로젝트는 Hailo-10H를 사용하여 20만 장 규모의 이미지 라이브러리에 대한
시맨틱 검색(자연어를 통한 이미지 검색)을 실현하는, 아마 최초의 실용 소프트웨어가 될 것이다.

---

## Phase 1: 실현 가능성 확인 (2026-03-01)

### 환경 정보

| 항목 | 값 |
|------|-----|
| 하드웨어 | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT 드라이버 | 5.2.0 (hailort-pcie-driver) |
| HailoRT 라이브러리 | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**소스 빌드**) |

### Step 1-1: 디바이스 인식 — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

디바이스는 문제없이 인식되었다. PCIe 연결, 드라이버 로드 모두 정상.

### Step 1-2: HEF 다운로드 — OK

Hailo Model Zoo v5.2.0의 S3 버킷에서 직접 다운로드 가능했다 (인증 불필요).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL 패턴:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3: Python 바인딩 — 소스 빌드 필요

#### 문제: 패키지 버전 불일치

Raspberry Pi OS의 리포지터리에는 다음 2계통의 패키지가 존재한다:

| 패키지 계통 | 버전 | 비고 |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Hailo 공식 deb. Python 바인딩 없음 |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Raspberry Pi 팀 제공. Python 있음 |

**문제**: 2계통은 `Conflicts` 설정으로 공존 불가. `h10-hailort` (5.1.1)를 설치하면
드라이버도 5.1.1이 되지만, hailo-ollama는 5.2.0이 필요.

#### 해결: hailort 5.2.0의 Python wheel을 소스 빌드

**PyPI에 wheel이 없다**. Hailo Developer Zone의 다운로드 페이지에도
**aarch64용 wheel은 존재하지 않는다** (x86_64만).

GitHub 리포지터리에서 소스 빌드로 해결:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# 빌드 의존성
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# 빌드 (약 2분)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# 설치
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**주의사항**:
- `--plat-name linux_aarch64`는 필수. 생략하면 `LIBHAILORT_PATH`의 디렉터리명 파싱에서
  `ValueError: not enough values to unpack`이 발생 (setup.py 163행의 버그)
- `hailort` deb (C 라이브러리)를 먼저 설치해야 한다
- `h10-hailort`와 `hailort`는 `Conflicts` 설정으로 공존 불가이므로,
  `h10-hailort`를 먼저 삭제한 후 `hailort` 5.2.0을 설치

### Step 1-4: 추론 테스트 — 성공 (API 변경 있음)

#### 중요한 발견: Hailo-10H는 구 VStreams API 미지원

사양서에 기재한 `InferVStreams` + `ConfigureParams.create_from_hef()` 코드는
**Hailo-10H에서는 동작하지 않는다**. `VDevice.configure()`가 `HAILO_NOT_IMPLEMENTED (error 7)`를 반환한다.

이것은 **Hailo-8/8L과 Hailo-10H의 근본적인 API 차이**이며,
공식 문서에도 명확하게 기재되어 있지 않은 중요한 사실이다.

#### 올바른 API: InferModel

Hailo-10H에서는 `VDevice.create_infer_model()`을 사용한다:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs는 프로퍼티 (callable이 아님)
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 입력: uint8 이미지
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # 출력: uint8 버퍼를 명시적으로 확보
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### 막혔던 포인트와 해결

| 문제 | 오류 | 해결 |
|------|--------|------|
| `infer_model.inputs()`가 TypeError | `'list' object is not callable` | 프로퍼티이므로 `inputs[0]` (괄호 없음) |
| 출력 버퍼 미설정 | `not configured as view` | `bindings.output().set_buffer(buf)`로 명시적 확보 |
| 출력 버퍼를 float32로 확보 | `buffer size 2048 != expected 512` | **uint8**로 확보 (512 bytes). float32는 2048 bytes가 됨 |
| VDevice 종료 시 오류 | `Lost communication with server` | VDevice 클린업 순서 문제. **추론 결과에는 영향 없음** |

### 추론 성능

| 항목 | 값 |
|------|-----|
| 모델 | CLIP ViT-B/16 Image Encoder |
| 입력 | (224, 224, 3) uint8 |
| 출력 | (1, 1, 512) uint8 (양자화 완료) |
| 추론 시간 | **~20 ms** |
| 이론 처리량 | **~50 images/sec** |

20만 장의 인덱스 구축: 추론만으로 약 67분. 전처리 포함해도 수 시간 이내에 완료 전망.

### Phase 1 판정

| 기준 | 결과 |
|------|------|
| 512차원 벡터 출력 | **OK** (uint8 양자화, 역양자화 필요) |
| 추론 속도 | **우수** (20ms/image) |
| API 호환성 | InferModel API 사용 (사양서의 VStreams API는 불가) |
| 판정 | **Phase 2로 진행** |

### 다음 Phase로의 인계 사항

1. **역양자화**: uint8 출력을 float32로 변환할 필요가 있다.
   HEF에 양자화 매개변수 (scale/zero_point)가 포함되어 있을 것이다.
   `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer`를 사용할 수 있을 가능성 있음.
2. **텍스트 인코더**: HEF는 존재하지만 미테스트. 같은 InferModel API로 동작하는지 확인 필요.
   사양서 방침대로 CPU (sentence-transformers)로 구현하는 것이 안전할 수 있다.
3. **hailo-ollama와의 공존**: VDevice는 디바이스를 배타적으로 사용한다.
   인덱스 구축 시 hailo-ollama를 중지할 필요가 있다.
4. **VDevice 클린업**: 종료 시 오류 메시지는 무해하지만,
   장시간 가동하는 서버 프로세스에서는 리소스 누수에 주의.

---

## Phase 2: DB 스키마 확장 (2026-03-01)

### 구현 내용

Migration 25로 `file_vectors` 테이블을 추가.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**설계 판단**:
- `vector`는 역양자화 후의 float32 BLOB을 저장. uint8로 저장하면 정확도가 열화됨
- `file_id`가 PRIMARY KEY (1파일 1벡터). 향후 복수 모델 대응 시 UNIQUE(file_id, model)로의 변경이 필요
- `ON DELETE CASCADE`로 files 삭제 시 자동 삭제

**테스트**: 인메모리 DB에서 migration 적용 → 테이블/인덱스 존재 확인 → OK

### 파일

- `core/schema_core/schema_migrate_steps_25.py` (신규)
- `core/schema_core/schema_migrate.py` (import + `if current_version < 25` 추가)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (신규 - DB 벡터 CRUD)  *(현재 `extensions/builtin_hailo_semantic_search/core_impl/`로 이동됨)*

---

## Phase 3: Hailo 추론 코어 (2026-03-01)

### 구현 내용

`core/hailo_clip_core/` 패키지를 신규 작성 *(현재 `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| 파일 | 책임 |
|---------|------|
| `hailo_inference.py` | HailoClipEncoder 싱글톤. InferModel API 래퍼 |
| `image_preprocess.py` | cv2로 224x224 리사이즈 + BGR→RGB 변환 |
| `dequantize.py` | uint8→float32 역양자화 + L2 정규화 + quant_params 추출 |
| `text_encoder.py` | CPU CLIP 텍스트 인코더 (`openai/clip-vit-base-patch16`) |

**설계 판단**:
- 이미지 전처리는 uint8 그대로 Hailo에 전달 (HEF 내부에서 정규화됨)
- 텍스트 인코더는 `transformers`의 CLIPModel을 사용 (`sentence-transformers`가 아님).
  이유: `openai/clip-vit-base-patch16`은 Hailo HEF의 CLIP ViT-B/16과 동일 모델로
  벡터 공간이 일치함
- 역양자화 매개변수는 `infer_model.outputs[0].quant_infos[0]`에서 취득을 시도하고,
  실패 시 scale=1.0, zero_point=0.0으로 폴백

**의존 패키지**: `opencv-python-headless`, `numpy` (필수), `transformers`, `torch` (텍스트 검색용)

---

## Phase 4: 인덱서 + Extension (2026-03-01)

### 구현 내용

| 파일 | 책임 |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(현재 `extensions/builtin_clip_search/core_impl/`)* | 백그라운드 스레드에서 배치 인덱스 구축 |
| `core/hailo_clip_core/event_handler.py` *(현재 `extensions/builtin_clip_search/core_impl/`)* | scan.complete 이벤트로 자동 인덱스 |
| `extensions/builtin_hailo_semantic_search/extension.json` | Extension 매니페스트 |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 API |

**API 엔드포인트**:
- `GET /ext/hailo-semantic/api/status` — 디바이스/인덱스 상태
- `POST /ext/hailo-semantic/api/index/start` — 인덱스 구축 시작
- `GET /ext/hailo-semantic/api/index/status` — 진행 상황
- `POST /ext/hailo-semantic/api/index/stop` — 중단
- `GET /ext/hailo-semantic/api/search` — 시맨틱 검색
- `POST /ext/hailo-semantic/api/index/clear` — 인덱스 클리어

**이벤트**: `semantic_index.start/progress/complete`를 event_bus에 추가

---

## Phase 5: 시맨틱 검색 엔진 (2026-03-01)

### 구현 내용

`core/hailo_clip_core/search.py` *(현재 `extensions/builtin_clip_search/core_impl/search.py`)* — 메모리 캐시 기반 코사인 유사도 검색

**알고리즘**:
1. 전체 벡터를 DB에서 일괄 로드 → 메모리 캐시
2. 벡터를 사전 L2 정규화
3. 쿼리 텍스트 → CLIP 텍스트 인코더 → 512차원 벡터
4. 행렬곱 (dot product)으로 코사인 유사도 배치 계산
5. threshold 이상을 정렬 → 결과 반환

**메모리 견적**: 200K x 512 x 4 bytes = ~400 MB (Pi5 8GB RAM에서 허용 범위)

**응답 형식**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6: UI 통합 (2026-03-01)

### 검색 페이지

- 검색 바 옆에 시맨틱 검색 토글 (뇌 아이콘 `regex-pill` 스타일)을 추가
- Hailo 이용 가능 & 인덱스 구축 완료인 경우에만 표시
- 토글 ON 시: 검색 폼 제출을 가로채서 → 시맨틱 검색 API → 기존 그리드에 결과 표시
- 플레이스홀더를 영어 텍스트 예시로 교체

### Tools 페이지

- Search & Analysis 탭에 시맨틱 검색 섹션을 추가
- 디바이스 상태/인덱스 현황 표시
- 배치 사이즈 슬라이더 + 자동 인덱스 체크박스
- Build Index / Stop / Clear 버튼 + 프로그레스 바 (2초 폴링)

---

## 기술 노트

### Hailo-10H vs Hailo-8/8L의 주요 차이 (개발자 관점)

| 항목 | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | 지원 | **미지원** (NOT_IMPLEMENTED) |
| InferModel API | 지원 | 지원 |
| ConfigureParams | create_from_hef(hef, interface) | 불필요 (create_infer_model이 대체) |
| 출력 형식 | float32 or uint8 선택 가능 | uint8 고정 (역양자화 필요) |
| Python 패키지 | PyPI wheel 있음 | **없음** (소스 빌드 필요) |
| APT 패키지 | `hailort` 통합 | `h10-hailort` 별도 계통 (5.1.1만) |

### 빌드된 wheel의 보관

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

다른 Pi5 환경으로의 배포 시 이 wheel을 복사하여 설치 가능
(단, libhailort.so.5.2.0과 hailort-pcie-driver 5.2.0이 필요).

---

## Phase 2-6 구현 후 버그 수정 로그 (2026-03-01)

### 1. 텍스트 인코더의 `get_text_features` 호환성 문제

**문제**: `CLIPModel.get_text_features(**inputs)`가 transformers의 새 버전에서는
`torch.Tensor`가 아닌 `BaseModelOutputWithPooling` 객체를 반환하게 되었다.
그로 인해 `.squeeze()` 호출에서 `AttributeError`가 발생하여, 시맨틱 검색이 `Search failed` 오류를 표시.

**증상**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**원인**: `_model.get_text_features()`의 반환값이 transformers 버전에 의존.
새 버전에서는 모델 출력 객체 전체가 반환되어 `.pooler_output` 등을 직접 추출해야 함.

**수정**: `text_encoder.py`에서 명시적으로 `text_model()` → `text_projection()`의 2단계로 처리하도록 변경:

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**성능**:
- 첫 번째 쿼리 (모델 로드 포함): ~6초
- 두 번째 이후: ~100-170ms (CPU 추론만)
- 벡터 검색: <1ms (51건, 메모리 캐시)

### 2. 인덱스 구축 시 무한 리트라이 루프

**문제**: 디코드 실패한 파일 (비이미지 파일, 손상된 파일 등)을 `failed_ids`로 추적하지 않아,
`get_unindexed_file_ids()`가 매번 같은 실패 파일을 반환하여 에러 카운트가 300만을 초과.

**수정**: `indexer.py`에 `failed_ids: set`을 추가. 실패한 file_id를 기록하고 다음 배치에서 제외.

### 3. 아카이브 파일의 이미지 읽기 실패

**문제**: `cv2.imread('test.7z!image.png')`는 아카이브 멤버 경로를 이해하지 못함.

**수정**: `image_preprocess.py`에서 `is_archive_member()`를 사용하여 아카이브 경로를 감지하고,
`read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()` 패턴으로 전환.

### 4. SSE 실시간 진행 상황 업데이트

**문제**: 2초 폴링에서는 진행이 끊김 현상이 심해 사용 경험이 좋지 않음.

**수정**: `EventSource` SSE 연결로 전환. `semantic_index.progress` 이벤트로 실시간 업데이트.
`visibilitychange`로 탭 비표시 시 SSE 연결을 끊고, 복귀 시 재연결.

---

## Phase 7: YOLO 객체 검출 (2026-03-02)

### 개요

CLIP 시맨틱 검색에 이어, 같은 Hailo-10H에서 YOLO 객체 검출을 구현.
이미지/동영상의 80 클래스 COCO 객체 검출을 수행하고, 결과를 `file_annotations` 테이블에 저장.

### 아키텍처 설계

#### VDevice 공유 문제

Hailo-10H는 단일 프로세스에서 1개의 VDevice만 사용할 수 있으며, InferModel도 배타적이다.
CLIP과 YOLO를 동시에 실행할 수 없다.

**해결책**: `core/hailo_device_core/device_manager.py`를 신설.
- `acquire_device(owner, hef_path)` — 다른 owner가 보유 중이면 자동 해제 후 전환
- 동일 owner + 동일 HEF이면 재사용 (재초기화 회피)
- `threading.Lock`으로 스레드 안전
- CLIP의 `hailo_inference.py`를 리팩터링하여 device_manager에 위임

#### YOLO 출력 텐서 처리

CLIP은 출력 텐서가 1개이지만, YOLO는 복수 출력 텐서 (각 stride의 헤드에 대응)를 가진다.
`device_manager`는 모든 출력의 quantization parameters를 수집하여 반환한다.

#### 후처리 파이프라인

YOLO 후처리는 다음 단계로 진행:
1. uint8 → float32 역양자화 (output별 scale/zero_point 사용)
2. grid cell → pixel 좌표로 디코딩 (sigmoid + grid offset + stride)
3. confidence 필터
4. 클래스별 NMS (pure numpy)
5. letterbox 좌표 → 원본 이미지의 정규화 좌표 (0-1)로 변환

#### 동영상 대응

ffmpeg로 프레임 추출 → 각 프레임을 독립적으로 검출 → 클래스별로 집계.
각 클래스의 최대 confidence + 출현 프레임 수를 유지.

### 신규 모듈 구성

| 모듈 | 역할 |
|---|---|
| `core/hailo_device_core/device_manager.py` | 공유 VDevice 라이프사이클 관리 |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector 싱글톤 |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, box decode, dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80 클래스 라벨 |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 레터박스 리사이즈 |
| `core/hailo_yolo_core/yolo_video.py` | 동영상 프레임 추출 + 집계 |
| `core/hailo_yolo_core/yolo_indexer.py` | 백그라운드 배치 검출 |
| `core/hailo_yolo_core/model_download.py` | HEF 다운로드 |
| `core/hailo_yolo_core/event_handler.py` | scan.complete 핸들러 |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### 기술 노트

- **멀티 출력 텐서**: YOLO HEF는 복수 출력 텐서 (각 stride의 헤드에 대응)를 가진다.
  `infer_model.outputs`를 순회하여 shape/quant_params를 모두 수집해야 한다
- **출력 버퍼**: 각 출력 텐서에 개별 uint8 버퍼를 확보하고,
  `bindings.output(out.name).set_buffer(buf)`로 이름 지정하여 바인딩
- **텐서 레이아웃**: 형상은 `(1, H, W, C)`가 일반적. C에는 bbox (4) + class scores (80)가 저장
- **HEF 다운로드**: Hailo Model Zoo v5.2.0에서 직접 다운로드. User-Agent를 설정하지 않으면
  Cloudflare에 차단되므로 `_USER_AGENT`를 설정
- **검출 결과 저장**: `file_annotations` 테이블의 `source='hailo:<model>'`, `key='detections'`에
  JSON 배열로 저장. 기존 어노테이션 CRUD API를 그대로 활용

---

## Phase 8: GenAI (LLM / VLM / Speech2Text) 통합 (2026-03-02)

### 목표

Hailo-10H의 `hailo_platform.genai` 모듈 (LLM, VLM, Speech2Text)을
device_manager에 통합하여, 텍스트 생성/이미지 이해/음성 문자 변환을 WebUI에서 이용 가능하게 한다.

### device_manager 확장

- **문제**: 기존 device_manager는 InferModel API (CLIP/YOLO)만 대응.
  GenAI 클래스는 InferModel이 아닌 VDevice를 직접 전달받는 별도 모드
- **해결책**: `_mode` 변수 (`"infer"` | `"genai"`)로 모드를 구분.
  `acquire_genai(owner, model_path, genai_factory)`를 추가하여,
  factory 패턴으로 LLM/VLM/S2T 인스턴스를 생성
- **릴리스 처리의 차이**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (명시적 release 메서드)

### GenAI API 발견 사항

- **메시지 형식**: OpenAI 호환의 role/content 구조. content는 배열로 `{"type": "text", "text": "..."}` 형식
- **VLM 이미지 입력**: 336x336 RGB uint8 numpy 배열. `frames=[image]`로 리스트 전달.
  프롬프트 내에 `{"type": "image"}` 플레이스홀더를 배치
- **S2T 입력**: little-endian float32 (`<f4`), 모노, 16kHz. int16→float32 정규화가 필수
- **S2T 세그먼트**: `generate_all_segments()`가 `SegmentInfo` 객체의 리스트를 반환.
  `.text`, `.start`, `.end` 속성 있음
- **컨텍스트 관리**: LLM/VLM은 `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()`로 컨텍스트 윈도우를 관리
- **스트리밍**: `generate()`가 이터레이터를 반환하며, 토큰별로 yield

### 모델 HEF 다운로드 URL

- 패턴: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- 모델명은 CamelCase (예: `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- `hailo-apps-infra`의 `download_resources.py`의 `gen-ai-mz` 소스 타입으로 확인

### 신규 파일

| 파일 | 설명 |
|----------|------|
| `core/hailo_genai_core/__init__.py` | 패키지 init |
| `core/hailo_genai_core/genai_types.py` | GenAIModelType enum + GenAIModelInfo dataclass |
| `core/hailo_genai_core/model_download.py` | 7개 모델 HEF 다운로드 관리 |
| `core/hailo_genai_core/llm_inference.py` | HailoLLM 래퍼 (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | HailoVLM 래퍼 (singleton, 이미지 전처리) |
| `core/hailo_genai_core/s2t_inference.py` | HailoS2T 래퍼 (singleton, 세그먼트 대응) |
| `extensions/builtin_hailo_genai/extension.json` | Extension 매니페스트 |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Tools 페이지 UI (4 패널) |

### 기술 노트

- **VDevice.create_params()**: GenAI 모드에서는 `VDevice.create_params()`로 매개변수를 생성하고
  `VDevice(params)`로 인스턴스화한다. InferModel 모드의 `VDevice()` (인수 없음)과는 다름
- **SSE 스트리밍**: Flask의 `Response(generator(), mimetype='text/event-stream')`로
  토큰별로 `data: {"token": "..."}\n\n`을 전송. 완료 시 `data: {"done": true}\n\n`
- **VLM의 FormData 전송**: 이미지 파일 + 텍스트 프롬프트를 동시에 보내기 위해,
  VLM API는 JSON이 아닌 `multipart/form-data`를 사용
- **S2T의 WAV 읽기**: 서버 측에서 `wave` 모듈 + `io.BytesIO`로
  업로드된 WAV 바이트열에서 직접 읽기

---

## Phase 9: 시맨틱 검색 + VLM 캡션 연동 (2026-03-03)

### 목표

CLIP 검색 결과의 이미지를 VLM (Qwen2-VL)으로 일괄 캡션 생성하여
`file_annotations`에 저장한다.

### 구현

- **`core/hailo_clip_core/caption_runner.py`** *(현재 `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150행): 백그라운드 스레드에서 VLM 캡션 생성을 배치 실행. `indexer.py`의 `_state_lock` + `_stop_requested` + `_progress` 패턴을 답습. SSE 이벤트 `vlm_caption.start/progress/complete`
- **Blueprint 확장**: `hailo_semantic_search.py`에 `/api/caption/start`, `/api/caption/status`, `/api/caption/stop`의 3개 엔드포인트 추가
- **UI**: Tools 페이지의 Semantic Search 섹션에 "VLM Caption Generation" 패널 추가. 프롬프트 입력, SSE 프로그레스 바, 검색 결과 file_ids 자동 연동

### VDevice 배타적 제어

- `acquire_genai("vlm", ...)`로 VLM을 취득. CLIP 인덱서가 동작 중이면 device_manager의 기존 동작으로 자동 해제됨
- 캡션 완료 후에는 VLM이 디바이스를 계속 보유하므로, CLIP 인덱스 재개에는 모델 언로드가 필요

### 어노테이션 저장 규약

- `source="hailo:vlm"`, `key="caption"`, `value=<캡션 텍스트>`

---

## Phase 10: 동영상 음성 문자 변환 — S2T 파이프라인 (2026-03-03)

### 목표

동영상 파일에서 ffmpeg로 음성 추출 → Whisper (S2T)로 문자 변환 → `file_annotations`에 저장.

### 구현

- **`core/files_core/video_audio.py`** (~80행): `extract_audio_wav()`로 ffmpeg 음성 추출 (mono PCM s16le 16kHz). 동영상의 duration으로부터 동적 타임아웃 산출 (최대 120초). `check_ffmpeg()`는 `media_video.py`에서 재사용
- **Blueprint 확장**: `hailo_genai_ext.py`에 3개 엔드포인트 추가:
  - `POST /api/s2t/transcribe-video`: 단일 동영상 문자 변환 (file_id, language)
  - `POST /api/s2t/batch-transcribe`: 복수 동영상 배치 문자 변환 (file_ids, language), 백그라운드 스레드 + SSE 진행 상황 (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: 저장된 문자 변환 결과 취득
- **UI**: S2T 패널 내에 "Video Transcription" 서브섹션 추가. file_id 입력, 언어 선택 (ja/en), 저장된 결과 취득 버튼

### 어노테이션 저장 규약

- `source="hailo:s2t"`, `key="transcript"`, `value=<전문 텍스트>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### 주의사항

- 임시 WAV는 `tempfile.NamedTemporaryFile`로 생성, finally에서 반드시 삭제
- S2T와 LLM/VLM은 디바이스 배타적 사용 (동시 사용 불가)

---

## Phase 11: LLM 멀티턴 대화 UI 개선 (2026-03-03)

### 목표

단발 프롬프트를 대화 이력 대응으로 확장. 컨텍스트 계속/리셋/버블형 UI.

### 구현

- **API 수정**: `api_llm_generate()`가 `messages` 배열을 수신 가능하게. 하위 호환: `prompt`만인 경우 기존대로 system + user 메시지로 변환. `generate_stream()`은 이미 멀티턴 대응 완료 (`_normalise_prompt()` 경유)
- **버블형 채팅 UI**: `hg-chat-container` + `hg-bubble` (user=오른쪽 정렬 보라색, AI=왼쪽 정렬 회색). CSS 클래스: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **대화 이력 관리**: JS 측에 `_chatHistory = []` 배열로 `{role, content}`를 축적. API 전송 시 `messages: [systemMsg, ..._chatHistory]`를 전달. `hgLlmClear()`로 배열 리셋 + HailoRT 컨텍스트 클리어
- **스트리밍**: AI 버블을 먼저 DOM에 삽입하고, SSE 토큰을 순차적으로 추가

### 버그 수정: 멀티턴 대화의 system role 오류 (2026-03-03)

MCP 디버그 쿼리 + hailort 로그로 발견. 2턴째 이후의 `generate()` 호출에서 다음 오류가 발생:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**원인**: UI 템플릿이 매번 `[systemMsg].concat(_chatHistory)`로 system role을 선두에 붙여서 전송하고 있었음. HailoRT의 LLM API는 컨텍스트가 존재하는 상태 (2턴째 이후)에서는 system role을 받아들이지 않음.

**수정**:
1. `llm_inference.py`에 `_prepare_prompt()` 메서드 추가: `get_context_usage_size() > 0`인 경우, system role 메시지를 자동 제외
2. UI 템플릿 (`_genai_ui.html`): `_chatHistory.length <= 1` (첫 번째 사용자 메시지만)인 경우에만 system을 첨부

**기술 노트**: HailoRT의 제약으로서, `LLM.generate()`는 최초 호출에서만 system role을 처리한다. 이는 OpenAI API와는 다른 동작이며, 멀티턴 대화를 구현할 때 주의가 필요

---

## WD-Tagger VLM x Hailo-10H 실기 테스트 (2026-03-03)

### 테스트 환경
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (빌드 버전)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### 중요한 발견: hailo-ollama는 VLM 미지원

hailo-ollama의 공식 문서 (USAGE.rst)에 명기:
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

MODELS 테이블에서도 `Qwen2-VL-2B-Instruct`의 Inference API 란은 "C++, Python"만으로, "Hailo-Ollama"를 포함하지 않음.

`/hailo/v1/list`로 반환되는 모델 목록:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl`은 포함되지 않음.

### hailo-ollama 테스트 결과

**config 주의사항**: 빌드 버전 바이너리는 `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` 매크로를 사용하여, config JSON에 `limits` 키가 필수. 공식 config 템플릿에는 포함되어 있지 않으므로, 다음을 추가해야 함:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **LLM 텍스트 생성 (qwen2.5:1.5b)**: OpenAI + Ollama native 양쪽 OK, 6.5 TPS
- **OpenAI API vision 요청**: 500 오류 (`Node is NOT a STRING`)
- **Ollama native API + images**: 수리되지만 LLM은 이미지 처리 불가
- **VlmWdTaggerEngine 폴백**: OpenAI 500 → Ollama native 자동 전환 OK
- **response_format: json_object**: 수리되지만 JSON 출력은 강제되지 않음

### Hailo Python SDK VLM 직접 테스트 결과

VLM은 메시지 형식에서 `{"type": "image"}`를 포함해야 한다:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **모델 로드**: 33초 (최초 콜드 스타트. 공칭 6.2초와의 차이는 디스크 I/O가 지배적)
- **추론 속도**: ~5.1 TPS (128 토큰 / 20초). 공칭 6.73 TPS와의 차이는 TTFT를 포함하기 때문
- **이미지 인식 정확도**: 이미지 내용을 정확하게 이해 ("눈 풍경 속에서 손을 잡고 있는 두 여성"을 정확하게 묘사)
- **JSON 출력 품질**: 낮음. 2B 모델에서는 구조화된 JSON 생성 정확도가 불안정 (쉼표 누락, 마크다운 코드 펜스 혼입)

### 발견된 버그

1. **`engines_hailo_vlm.py` 프롬프트 형식**: VLM에 대해 텍스트만 메시지를 전달하고 있었음 → `{"type": "image"}`를 포함하는 리스트 형식으로 수정
2. **`vlm_inference.py` frames 인수**: VLM의 `generate_all()`은 `frames` 필수이지만 Optional로 선언되어 있었음 → 필수로 수정

### 기술 노트

- **VDevice 배타적 제약**: hailo-ollama 기동 중에는 `hailo_platform.VDevice()`를 취득할 수 없음. VLM 직접 추론 시에는 hailo-ollama를 중지해야 함
- **VLM.generate_all()은 frames 필수**: 텍스트만 추론은 `HAILO_INVALID_OPERATION` 오류가 발생. LLM과 VLM에서 API의 전제 조건이 다름
- **Qwen2-VL의 prompt template**: Jinja2 템플릿으로 `<|vision_start|><|image_pad|><|vision_end|>`를 삽입. 메시지 형식에서 `{"type": "image"}`를 포함하면 SDK가 자동 처리

---

## Phase 12: OpenAI 호환 API + 디바이스 전환 버그 수정 (2026-03-14)

### 목표

1. OpenAI SDK / LiteLLM / Continue.dev / Open WebUI 등 외부 도구에서 Hailo GenAI를 직접 이용할 수 있는 OpenAI 호환 API를 제공
2. Quart async 대응의 불비를 수정
3. MCP 도구의 SSE 엔드포인트 대응

### 구현: OpenAI 호환 API (`hailo_openai_routes.py`)

신규 파일 `extensions/builtin_hailo_genai/hailo_openai_routes.py`를 생성. 다음 4개 엔드포인트를 구현:

| 엔드포인트 | 기능 | 대응 모델 |
|---|---|---|
| `GET /v1/models` | 이용 가능 모델 목록 | 전 모델 + CLIP |
| `POST /v1/chat/completions` | 텍스트/이미지 채팅 (stream 대응) | LLM + VLM |
| `POST /v1/audio/transcriptions` | 음성 문자 변환 | Whisper |
| `POST /v1/embeddings` | 텍스트→CLIP 벡터 | CLIP ViT-B/16 |

#### 설계상의 판단

- **Vision 대응**: OpenAI Vision API 형식 (`image_url` with `data:` base64)을 그대로 수신. 추가로 `file_id:123` 형식으로 YU 라이브러리의 이미지를 직접 참조 가능
- **HTTP URL 미지원**: SSRF 방지를 위해, `image_url`에 `http://` / `https://`는 수신하지 않음
- **모델 별칭**: `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16` 등의 OpenAI 호환 별칭을 정의
- **비 WAV 음성**: ffmpeg로 자동 변환 (16kHz mono PCM16)
- **Usage 필드**: Hailo SDK는 토큰 수를 반환하지 않으므로 `0` 고정. 향후 개선 여지 있음

#### MCP 도구

- `hailo_genai_openai_info`: 엔드포인트 목록과 이용 방법을 반환하는 헬퍼 도구 (API 호출 없이 로컬에서 생성)

### 수정: Quart async SSE 제너레이터

모든 라우트 파일의 SSE 제너레이터에 async 대응 불비가 있었음:

| 파일 | 문제 | 수정 |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()`가 동기 함수 | `async def`로 변경, `get_llm()`과 `next(it)`를 `asyncio.to_thread`로 실행 |
| `hailo_vlm_routes.py` | 상동 + DB 참조가 동기 | 상동 + `run_db_sync`로 래핑 |
| `hailo_s2t_routes.py` | transcribe가 동기 실행 + DB가 동기 | `asyncio.to_thread` + `run_db_sync`로 래핑 |
| `hailo_chat_routes.py` | 상동 (LLM/VLM 모두) | 모든 블로킹 호출을 async화 |

Quart (ASGI)에서는 제너레이터가 `async def`가 아니면 이벤트 루프를 블로킹하여, SSE 배포 중 다른 요청이 처리되지 않는다.

### 발견된 버그: 디바이스 전환 시 싱글톤 불일치

#### 증상

VLM 사용 후 LLM을 호출하면 `'NoneType' object has no attribute 'get_context_usage_size'` 오류. 역방향 (LLM→VLM→LLM)에서도 반드시 발생.

#### 원인 분석

Hailo-10H는 VDevice를 1개만 보유할 수 있으므로, `device_manager.py`가 배타적으로 관리하고 있다. 모델 전환 시 흐름:

1. VLM의 `get_vlm()` → `acquire_genai("vlm", ...)` → 내부에서 `_release_internal()`이 LLM의 VDevice를 해제
2. VLM 사용 완료
3. LLM의 `get_llm()` → `_instance`가 남아 있음 + `model_name`도 일치 → **기존 인스턴스를 재사용**
4. `_instance._llm` 내부의 VDevice는 이미 해제되어 있음 → `get_context_usage_size()`가 `None` 위에서 호출되어 크래시

문제의 근본: 싱글톤의 `_instance`가 남아 있더라도, 그 내부의 Hailo SDK 객체 (`self._llm`)가 가리키는 VDevice가 `device_manager`의 `_release_internal()`에 의해 `.release()` 완료 상태. Python의 참조 카운트에서는 `_instance._llm`이 아직 살아있지만, Hailo SDK 측의 네이티브 리소스가 해제되어 있다.

#### 수정

`get_llm()` / `get_vlm()` / `get_s2t()`의 싱글톤 재사용 체크에 `device_manager.get_current_owner()` 확인을 추가:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # 디바이스를 보유 중 → 재사용 OK
            # 디바이스가 다른 모델에 빼앗김 → 재생성
            _instance = None
        ...
```

LLM / VLM / S2T의 3개 싱글톤 모두에 같은 수정을 적용.

#### 검증

LLM → VLM → LLM → VLM의 4회 연속 전환에서 모두 정상 동작을 확인.

### 기타 수정

- **MCP `post_sse` 메서드**: `mcp_server/client.py`에 SSE 스트림을 소비하여 최종 텍스트를 JSON으로 반환하는 `post_sse()` 메서드를 추가. `hailo_llm_generate`와 `hailo_vlm_generate` 도구가 이를 사용
- **MCP `yolo_search` 매개변수**: `labels` → `class_name`으로 이름 변경 (API 측 매개변수명과 일치)
- **Circuit Breaker**: `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`)를 추가. half_open 상태에서 `hailo_genai_status` 등 상태 관련 도구가 허용되도록
- **Semantic Search async**: `get_encoder_info()`와 `semantic_search()`를 `run_db_sync`로 래핑 (Quart 이벤트 루프 블로킹 방지)

### 기술 노트

- **VDevice의 배타적 제약은 SDK 레벨**: Python 측에서 객체의 참조를 가지고 있어도, Hailo SDK의 네이티브 측에서 리소스가 해제되면 사용할 수 없게 된다. 싱글톤 패턴을 사용하는 경우, 네이티브 리소스의 유효성을 별도로 체크해야 함
- **Quart + 동기 제너레이터**: Quart의 SSE 응답에 동기 제너레이터를 전달하면 동작은 하지만, `yield` 사이의 처리가 이벤트 루프를 블로킹한다. Hailo 추론 같은 무거운 처리는 반드시 `asyncio.to_thread`로 별도 스레드로 보내야 함
- **OpenAI Vision API와 VLM의 연동**: OpenAI Vision API는 `image_url` 필드로 이미지를 수신하지만, Hailo VLM은 `frames` (numpy array)를 수신한다. 변환 레이어에서 base64 디코딩 → OpenCV 디코딩 → 336x336 RGB 리사이즈를 수행
