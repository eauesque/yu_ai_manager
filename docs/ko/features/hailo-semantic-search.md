# Hailo 시맨틱 검색 Extension — 구현 사양

**상태**: 구현 완료 — Hailo 전용 버전은 CLIP ONNX (v2.95.0)로 대체됨
**대상**: YU AI Manager Extension
**목적**: Hailo-10H (AI HAT 2)에서 CLIP/SigLIP을 활용한 시맨틱 이미지 검색
**구현**: `extensions/builtin_clip_search/core_impl/` (공유 레이어) + `extensions/builtin_clip_onnx/core_impl/` (ONNX 구현)
**참고**: 이 사양은 초기 Hailo 전용 설계를 설명합니다. 현재 구현은 통합 ONNX 멀티 백엔드 아키텍처를 사용합니다

---

## 개요

이 Extension은 자연어 텍스트를 사용하여 이미지를 검색하는 기능을 추가합니다.
예: "파란 하늘과 바다", "웃는 소녀", "야경 도시 풍경" — 모두 시각적으로 유사한 이미지를 반환합니다.

기존 FTS5 태그 검색 및 pHash 유사 검색과 **병행**하여 작동해야 합니다.
이 Extension은 Hailo 디바이스가 없는 환경에서는 자동으로 비활성화됩니다.

---

## 아키텍처

```
[이미지 스캔 중]
이미지 파일 -> CLIP Image Encoder (Hailo HEF) -> 512차원 벡터 -> DB 저장

[검색 시]
텍스트 입력 -> CLIP Text Encoder (CPU / Hailo HEF) -> 512차원 벡터
           -> 코사인 유사도 검색 -> file_id 목록 -> 기존 검색 결과와 병합
```

**CLIP과 SigLIP 모두 지원**하며, 설정을 통해 전환 가능합니다.
SigLIP이 더 높은 정확도를 제공하지만, CLIP은 더 많은 실적과 커뮤니티 자원을 보유합니다.
CLIP으로 시작하고 나중에 SigLIP을 추가하는 것을 권장합니다.

---

## 단계별 분류

### Phase 1: 실현 가능성 검증 (가장 먼저 수행)

Pi5 환경으로 이동한 후, Claude Code가 다음 단계를 **위에서 아래로 순서대로** 실행합니다.
실패한 단계가 있으면 중지하고 문제를 해결한 후 계속 진행합니다.

#### Step 1-1: HailoRT 런타임 확인

```bash
# 디바이스 인식 확인
hailortcli fw-control identify

# Python 바인딩 확인
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **디바이스가 보이지 않음**: `dmesg | grep hailo`로 드라이버 상태 확인. AI HAT 2 PCIe 연결 확인
- **import 실패**: `pip install hailort` 또는 Hailo APT 저장소 (`python3-hailort`)에서 설치

#### Step 1-2: CLIP HEF 파일 다운로드

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Image encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / 접근 거부**: Hailo Developer Zone (https://hailo.ai/developer-zone/) 등록이 필요합니다.
  등록 후 Model Zoo CLI (`hailo_model_zoo`)를 통해 다운로드 시도
- **크기 확인**: 각 파일은 수십~약 100MB여야 합니다. 비정상적으로 작은 파일은 다운로드 실패를 나타냄

#### Step 1-3: Python 의존성 설치

```bash
# 이미지 전처리에 필요 (Phase 1에서 사용)
pip install opencv-python-headless numpy

# 확인
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Step 1-4: 최소 추론 테스트

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# HEF 입출력 레이어 정보 확인 (레이어 이름은 모델에 따라 다름)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Expected: (224, 224, 3) etc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # 더미 이미지로 추론 테스트
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # 512차원 벡터가 출력되면 성공
```

- **VDevice 오류 (`not enough free devices`)**: hailo-ollama가 실행 중일 수 있음. `systemctl stop hailo-ollama`로 중지 후 재시도
- **추론은 성공하지만 출력이 512차원이 아님**: HEF 버전과 모델 변형 확인

#### Step 1-5: 판단 기준

| 결과 | 다음 조치 |
|------|----------------|
| 512차원 벡터 출력 | Phase 2 이후로 진행 |
| HEF 로드 성공이나 출력 차원이 다름 | 다른 모델 변형 시도 (clip_resnet_50 등) |
| HEF 다운로드 불가 | Developer Zone 등록 -> Model Zoo CLI로 다운로드 |
| hailo_platform import 불가 | HailoRT 재설치. 해결 안 되면 CPU CLIP으로 폴백 |
| 디바이스 미인식 | 하드웨어 연결 / 드라이버 문제. Extension 개발 일시 중지 |

Phase 1이 성공하면 전체 구현을 진행합니다. 실패하면 CPU CLIP을 대안으로 검토합니다.

---

### Phase 2: DB 스키마 확장

기존 DB 마이그레이션에 추가:

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

저장: `numpy.ndarray.tobytes()` -> BLOB
로드: `numpy.frombuffer(blob, dtype=numpy.float32)`

**참고**: SQLite에는 ANN (Approximate Nearest Neighbor) 인덱스가 없으므로, 200,000개 레코드 전체에 대해 코사인 유사도 계산이 필요합니다. numpy 배치 계산으로 Pi5에서 허용 가능한 범위 내에 유지될 것으로 예상됩니다 (측정 필요). 레코드 수가 크게 증가하면 `sqlite-vec` 확장을 고려하세요.

---

### Phase 3: Hailo 추론 코어

**파일 구조**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Extension 진입점
├── core/
│   ├── hailo_clip.py     # Hailo CLIP 추론 래퍼
│   ├── cpu_clip.py       # 비Hailo 환경용 CPU 폴백 (선택 사항)
│   └── vector_store.py   # DB 벡터 CRUD
├── routes/
│   └── semantic_search.py  # API 엔드포인트
└── templates/
    └── _semantic_search_ui.html
```

**`hailo_clip.py`의 역할**:
- HEF 로드 및 VDevice 초기화 (싱글톤, 시작 시 1회)
- 이미지 -> 전처리 (224x224 리사이즈, 정규화) -> HEF 추론 -> 512차원 벡터
- 텍스트 -> 토큰화 -> HEF 추론 -> 512차원 벡터
  * Hailo-10H용 텍스트 인코더 HEF가 사용 가능하면 사용; 그렇지 않으면 CPU (transformers 라이브러리) 사용

**전처리**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4: 인덱스 구축 API

**엔드포인트**:
```
POST /api/extensions/hailo-semantic/index
```
- 백그라운드 스레드에서 인덱스되지 않은 이미지를 순차적으로 처리
- `semantic_index.progress` 이벤트로 SSE를 통해 진행 상황 전송
- 선택적으로 기존 `scan.complete` 이벤트에 연결하여 자동 실행

**배치 크기**: 32개 이미지 (메모리와 속도 균형)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5: 시맨틱 검색 API

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**처리 흐름**:
1. 텍스트 `q`를 벡터로 변환
2. `file_vectors`에서 모든 벡터 로드 (numpy)
3. 배치로 코사인 유사도 계산
4. `threshold` 이상의 결과를 유사도 내림차순으로 정렬
5. 기존 `/api/search` 형식으로 `file_id` 목록 반환

**코사인 유사도 계산**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**성능 목표**: 200,000개 레코드에서 1초 이내 (Pi5에서도 numpy 배치 계산으로 달성 가능)

---

### Phase 6: UI 통합

기존 검색 UI에 "시맨틱 검색" 탭을 추가합니다.
기존 condition-builder와 독립적인 단독 UI로 할 수 있습니다 (통합은 향후 과제).

```html
<!-- 검색바 옆에 토글 버튼 추가 -->
<button id="semantic-search-toggle" class="btn-secondary">
  의미 검색 (Hailo)
</button>
```

- Hailo 디바이스가 감지되지 않으면 버튼을 숨기거나 비활성화
- 검색 결과에 기존 그리드를 재사용
- 인덱스가 없을 때 인덱스 구축 안내 표시

---

## 설정 (config.json 추가)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## 확인된 사항 (2026-02-27 기준)

아래 정보는 사전 조사를 통해 확인되었습니다. Phase 1 실행 시 참고 자료로 활용하세요.

### CLIP HEF 가용성

Hailo Model Zoo v5.2.0에는 CLIP/SigLIP 변형에 대해 Hailo-10H용 **이미지 인코더와 텍스트 인코더** HEF가 모두 포함되어 있습니다:

| 모델 | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | 사용 가능 | 사용 가능 |
| clip_vit_b_32 | 사용 가능 | 사용 가능 |
| clip_vit_l_14 | 사용 가능 | 사용 가능 |
| clip_resnet_50 | 사용 가능 | 사용 가능 |
| siglip_b_16 | 사용 가능 | 사용 가능 |
| siglip_l_16_256 | 사용 가능 | 사용 가능 |
| siglip2_b_32_256 | 사용 가능 | 사용 가능 |
| TinyCLIP 변형 | 사용 가능 | 사용 가능 |

S3 URL 패턴: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### 텍스트 인코더 현황

- 공식 `hailo-CLIP` 앱은 **텍스트 인코더를 CPU (PyTorch)에서 실행**합니다
- Hailo-10H용 텍스트 인코더 HEF가 Model Zoo에 존재하지만, **이를 사용하는 공개된 애플리케이션은 없습니다**
- 권장 접근법: **CPU에서 텍스트 인코더를 구현 (`sentence-transformers`)**. 검색 쿼리당 1회만 실행되므로 속도가 문제되지 않음
- 이미지 인코더가 Hailo 가속의 실질적 가치를 제공하는 부분 (200K 이미지 배치 인덱싱)

### hailo-ollama와의 공존

- `SHARED_VDEVICE_GROUP_ID`를 통한 디바이스 공유가 공식적으로 지원됨
- 그러나 **hailo-ollama 바이너리는 이 공유에 참여하지 않음** (디바이스를 독점적으로 점유)
- 커뮤니티 사례: 커스텀 디바이스 매니저를 구축하여 6개 서비스를 동시에 실행
- **실용적 접근법**: 인덱스 구축 중 hailo-ollama를 중지하고 디바이스를 시분할
  - `systemctl stop hailo-ollama` -> 인덱스 구축 -> `systemctl start hailo-ollama`

### 200,000개 레코드의 벡터 검색 추정

- 200K x 512 float32 = 약 400MB — Pi5 (8GB) RAM에 적합
- numpy 배치 코사인 유사도 계산이 Pi5 Cortex-A76에서 1초 이내에 완료될 것으로 예상

### 대규모 벡터 검색용 FAISS 가속 (v3.26.0)

v3.26.0에서 FAISS (Facebook AI Similarity Search) 지원이 추가되었습니다. 시스템이 `faiss-cpu` 설치를 자동 감지하고 NumPy 브루트 포스 대신 근사 최근접 이웃 검색을 사용합니다.

| 규모 | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (정확한 내적 검색)이 자동 선택됨
- **>= 50K**: IndexIVFFlat (IVF 클러스터링)이 자동 선택됨, nprobe = nlist/10
- FAISS가 설치되지 않으면 NumPy로 폴백 (영향 없음)

**설치**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # x86_64에서 직접 pip install 가능
# aarch64 (RPi): conda install -c conda-forge faiss-cpu 또는 소스에서 빌드
```

활성화 시 시작 로그에 `FAISS x.x.x detected — using accelerated vector search`가 표시됩니다.

### hailo-CLIP 앱에 대한 참고 사항

- `hailo-ai/hailo-CLIP`은 **Hailo-8/8L**을 대상으로 합니다. Hailo-10H는 지원되지 않음
- 이미지 검색 파이프라인이 아닌 실시간 제로샷 분류용으로 설계됨
- 참고 자료로 활용할 수 있으나 직접 사용은 불가. HailoRT API를 사용하여 커스텀 파이프라인을 구축해야 함

---

## 대안 (Hailo를 사용할 수 없는 경우)

`sentence-transformers`의 `clip-ViT-B-32`가 CPU 전용 CLIP 지원을 제공합니다.
느리지만 Hailo가 없는 환경에서도 동일한 Extension을 실행할 수 있습니다.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Extension 설정에서 `"device": "cpu"`를 설정하면 CPU 모드가 활성화됩니다. 이 듀얼 아키텍처 접근법은 이식성을 극대화합니다.

---

## 구현 우선순위

```
Phase 1 (검증)       -> 필수, 가장 먼저 수행
Phase 2 (DB)         -> Phase 1 성공 후
Phase 3 (추론 코어)  -> Phase 2 이후
Phase 4 (인덱싱)     -> Phase 3 이후
Phase 5 (검색 API)   -> Phase 4 이후
Phase 6 (UI)         -> Phase 5 이후, 마지막
```

Phase 1이 실패하면 전체 접근법을 CPU CLIP으로 전환합니다.

---

## 참고 저장소

- `hailo-ai/hailo-apps`: CLIP 제로샷 분류 샘플
- `hailo-ai/hailort`: pyHailoRT API 참고
- `hailo-ai/Hailo-Application-Code-Examples`: Python 추론 샘플
- `hailo-ai/hailo_model_zoo`: CLIP/SigLIP HEF 다운로드 소스

---

*작성: 2026-02-27*
*조사 보충: 2026-02-27 — Phase 1 절차 상세, HEF 가용성 확인, hailo-ollama 공존 분석*
