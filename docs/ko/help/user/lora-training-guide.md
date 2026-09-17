# LoRA 학습 가이드

YU AI Manager + MCP + kohya_ss를 활용한 자연어 LoRA 학습 완전 가이드

---

## 소개

이 가이드는 YU AI Manager의 MCP 서버와 kohya_ss를 연동하여 자연어 지시만으로 LoRA를 제작하는 흐름을 설명하는 실전 가이드입니다.

기존 LoRA 제작 시간의 대부분은 "데이터셋 수동 준비"에 소요되었습니다. 이미지 선별, 태그 검토 및 제외, caption 파일 정리, 폴더 구조 정비——이 모든 것을 사람이 직접 해야 했습니다.

YU AI Manager의 MCP 연동으로 이 흐름이 바뀝니다. "○○의 LoRA를 만들어 주세요. 태그는 △△를 제외해서"라는 지시 하나로, 소재 수집부터 태깅, 데이터셋 생성, kohya_ss 실행까지 일관되게 동작합니다.

---

## 전체 흐름

LoRA 제작 과정은 다음 5단계로 구성됩니다.

| 단계 | 작업 내용 | 담당 |
|------|---------|------|
| 1. 소재 준비 | 학습용 이미지 수집 및 배치 | 사람 / AI 에이전트 |
| 2. 태깅 | WD-Tagger를 통한 자동 태깅 | MCP（자동） |
| 3. 데이터셋 생성 | 프로젝트 생성, 제외 태그 설정, 내보내기 | MCP（자동） |
| 4. 학습 실행 | kohya_ss 호출로 학습 | MCP（자동） |
| 5. 검증 | SD에서 LoRA를 사용해 결과 확인 | 사람 |

사람이 개입하는 것은 "무엇을 학습시킬지"라는 의사결정과 최종 결과 확인뿐입니다.

---

## 사전 조건

### 필요한 소프트웨어

- YU AI Manager — MCP 서버 기능 포함
- Claude Desktop 또는 Claude Code — MCP 클라이언트
- kohya_ss — sd-scripts 포함 버전
- Stable Diffusion WebUI（A1111 / ComfyUI / Forge）— 결과 검증용

### GPU 요건

| GPU VRAM | 지원 모델 | 필요 설정 |
|---------|---------|---------|
| 8GB | SD 1.5만 실용적 | `--gradient_checkpointing` 필수 |
| 12GB | SDXL 동작（제한 있음） | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL 쾌적 | 기본 설정으로 동작 |
| 24GB+ | SDXL·FLUX 모두 지원 | 거의 제한 없음 |

> **참고**: RTX 3060 12GB에서 SDXL LoRA 학습이 가능하지만, gradient_checkpointing이 필수이므로 24,000 스텝에 약 10시간이 소요됩니다. RTX 5060 Ti 16GB라면 3〜5시간으로 단축될 것으로 예상됩니다.

### kohya_ss 디렉토리 구성

kohya_ss는 최상위 디렉토리와 실제 스크립트 디렉토리가 분리되어 있는 경우가 많습니다.

```
O:\webui\kohya_ss\              ← kohya_path에 설정하는 최상위 디렉토리
O:\webui\kohya_ss\venv\         ← Python 가상 환경（자동 감지됨）
O:\webui\kohya_ss\sd-scripts\   ← 학습 스크립트가 저장되는 디렉토리
```

> ⚠️ **주의**: `kohya_path`에 최상위 디렉토리를 지정하면 YU AI Manager가 `sd-scripts` 하위 폴더와 venv를 자동으로 감지합니다. sd-scripts 경로를 직접 지정하지 마세요.

---

## YU AI Manager 설정

### Extension 설정

LoRA Dataset Manager 설정 탭에서 다음을 입력합니다.

| 설정 항목 | 설명 | 예시 |
|---------|------|------|
| `kohya_path` | kohya_ss 최상위 디렉토리 | `O:\webui\kohya_ss` |
| `output_base_dir` | 데이터셋 출력 기본 디렉토리 | `C:\lora_datasets` |
| `checkpoint_dir` | 기본 모델 디렉토리 | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | 기본 모델 종류 | `sdxl` |

### WD-Tagger 설정

LoRA 데이터셋 용도에서는 VLM（llava 등）과의 조합을 권장하지 않습니다. VLM은 자유 기술 태그를 대량 생성하여 caption 품질을 저하시킵니다.

```
engine_type: "onnx"  ← ONNX 단독 사용
```

> ⚠️ **주의**: `engine_type`을 `"both"`로 설정하면 VLM 유래의 복합 태그（`wooden_bear_and_fish_sculpture` 등）가 생성됩니다. 이것들은 kohya_ss의 caption으로 기능하지 않아 학습을 방해합니다.

---

## MCP를 통한 LoRA 제작 절차

### Step 1: 소재 이미지 준비

학습용 이미지를 YU AI Manager의 scan root에 배치하고 스캔합니다.

- YU AI Manager의 Scan Root 설정에서 학습용 폴더 추가
- 스캔 완료 후 대상 이미지가 DB에 등록됨
- 최소 20〜30장, 권장 50〜200장

> **참고**: 이미지 품질이 학습 결과의 최대 결정 요인입니다. 해상도 512px 이상, 대상이 명확하게 찍힌 것을 선택하세요.

### Step 2: WD-Tagger로 태깅

MCP에서 일괄 태깅을 실행합니다.

```python
# 대상 파일 ID 목록을 가져와 일괄 태깅
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

기존 태그가 있는 경우 먼저 삭제 후 재실행합니다.

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3: 프로젝트 생성

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # kohya_ss 폴더명으로 사용
    base_model="sdxl",
    repeat=20
)
```

### Step 4: 파일과 태그 설정

프로젝트에 파일 ID를 설정하고 태그 집계를 확인합니다.

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

태그 집계를 보고 제외할 태그를 결정합니다.

#### 제외 태그 설계 철학

LoRA에 "무엇을 학습시킬지"의 핵심이 여기에 있습니다.

**남겨둘 태그**: 학습시키고 싶은 개념 고유의 특징（조형·스타일·고유 요소）

**제외할 태그**: 모델이 이미 알고 있는 범용 태그（`no_humans`, `realistic`, `animal`, `solo`, 배경 관련 등）

예시: 나무 조각 곰 LoRA의 경우

- 남김: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- 제외: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

> ⚠️ **주의**: 개념 분리에 실패하면 학습이 분산됩니다. `bear`나 `wood`를 남기고 싶은 경우 WD-Tagger ONNX가 이를 확실히 부여하지 않을 수 있습니다. caption 미리보기로 실제 출력을 확인하세요.

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5: Caption 미리보기 확인

```python
preview_lora_caption(project_id=N, file_id=<임의의 파일ID>)
```

출력 예시:

```
"fish, full_body, open_mouth, standing"
```

VLM 노이즈 없이 간결한 태그 목록인지 확인합니다. 빈 caption이 많은 경우 제외 태그를 재검토해야 합니다.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Step 6: 데이터셋 내보내기

```python
export_lora_dataset(project_id=N)
```

출력 폴더 구성:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7: 학습 실행

먼저 dry_run으로 명령어를 확인합니다.

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="전체경로\checkpoint.safetensors"
)
```

문제 없으면 학습을 시작합니다.

```python
start_lora_training(
    project_id=N,
    checkpoint="전체경로\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

진행 상황 확인:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## 기본 학습 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `network_dim` | 32 | LoRA의 랭크. 클수록 표현력이 높아지지만 파일 크기도 증가 |
| `network_alpha` | 16 | 보통 dim의 절반으로 설정 |
| `learning_rate` | 1e-4 | 학습률 |
| `max_train_epochs` | 10 | 에포크 수 |
| `save_every_n_epochs` | 2 | 중간 저장 간격 |
| `mixed_precision` | fp16 | 정밀도. 경우에 따라 bf16이 VRAM을 더 절약 |
| `resolution` | 1024,1024（SDXL） | 학습 해상도. SD1.5는 512,512 |

> **참고**: 이것들은 Settings 탭 또는 `set_extension_config`에서 변경 가능합니다. 추가 인수는 `start_lora_training`의 `extra_args`로 추가할 수 있습니다.

---

## GPU별 권장 설정

| GPU VRAM | 권장 extra_args |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | （기본 설정으로 동작） |
| 24GB+ | （기본 설정으로 동작; batch_size 증가 가능） |

> ⚠️ **주의**: 12GB GPU에서 gradient_checkpointing을 사용하면 SDXL 24,000 스텝에 약 10〜12시간이 걸립니다. 16GB 이상에서는 이 제약이 없어져 대폭 빠르게 처리됩니다.

---

## Repeat 수와 Epoch 수 기준

**총 학습 스텝 수 = 이미지 수 × repeat 수 × epoch 수**

| 개념 복잡도 | 권장 스텝 수 | 예시（이미지 50장 기준） |
|----------|----------|----------------|
| 단순한 객체·스타일 | 1,000〜3,000 | repeat=10, epoch=5 |
| 캐릭터·조형물 | 3,000〜8,000 | repeat=20, epoch=5 |
| 복잡한 스타일·인물 | 5,000〜15,000 | repeat=20, epoch=10 |

> **참고**: 120장 × 20 repeat × 10 epoch = 24,000 스텝으로 학습하면 충분한 품질을 얻을 수 있습니다. 그러나 5〜6 epoch에서도 동등한 결과를 얻을 수 있으므로, 먼저 짧은 epoch로 시험해 보는 것을 권장합니다.

---

## 트러블슈팅

### ModuleNotFoundError: No module named 'torch'

**원인**: YU AI Manager의 venv에서 kohya_ss 스크립트를 실행하려고 합니다.

**대처**: `kohya_path`를 최상위 디렉토리（sd-scripts의 부모）로 설정합니다. YU AI Manager는 자동으로 `kohya_path/venv/Scripts/python.exe`를 감지합니다.

---

### AssertionError: resolution is required

**원인**: `--resolution`이 지정되지 않았습니다.

**대처**: YU AI Manager 최신 버전에서는 자동으로 부여됩니다（SDXL: 1024,1024, SD1.5: 512,512）.

---

### AssertionError: network for Text Encoder cannot be trained with caching

**원인**: `--cache_text_encoder_outputs`와 `--network_train_unet_only`가 짝을 이루지 않고 있습니다.

**대처**: YU AI Manager 최신 버전에서는 SDXL 시 자동으로 `--network_train_unet_only`를 부여합니다.

---

### torch.OutOfMemoryError: CUDA out of memory

**원인**: VRAM이 부족합니다.

**대처**: `extra_args`에 다음을 추가합니다.

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM 노이즈 태그 혼입

**원인**: `engine_type`이 `"both"`로 설정되어 VLM（llava 등）이 자유 기술 태그를 생성하고 있습니다.

**대처**: WD-Tagger 설정에서 `engine_type="onnx"`로 변경하고, 태그를 모두 삭제한 뒤 재태깅합니다.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir（403 오류）

**원인**: checkpoint 경로가 `checkpoint_dir` 외부를 가리키고 있습니다.

**대처**: Extension 설정의 `checkpoint_dir`이 올바른 디렉토리를 가리키는지 확인합니다.

---

### output_base_dir not configured（400 오류）

**원인**: Extension 설정의 `output_base_dir`이 미설정이거나 저장되지 않았습니다.

**대처**: UI 설정 탭에서 다시 저장하거나 MCP에서 `set_extension_config`로 설정합니다.

---

## 생성 시 프롬프트

### 기본 프롬프트 구성

```
{concept_token}, {특징 태그}, <lora:{lora_name}:{strength}>
```

나무 조각 곰 LoRA 예시:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

네거티브 프롬프트:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### LoRA 강도 조정

| 강도 | 특성 |
|-----|------|
| 0.5〜0.6 | 기본 모델의 영향이 강함. 색상·스타일이 기본 모델 쪽으로 치우침 |
| 0.7〜0.8 | 권장 범위. LoRA 특징과 기본 모델의 균형이 좋음 |
| 0.9〜1.0 | LoRA의 영향이 강함. 조형은 잘 나오지만 색이 흰색/크림색으로 치우치기 쉬움 |

> **참고**: 색상이 하얗게 날아가는 경우 강도를 낮추거나 프롬프트에 `brown wood, warm tone`을 추가해 색상을 유도합니다.

---

## 향후 확장

### 소재 수집 자동화

현재 소재 이미지는 사람이 수동으로 준비해야 합니다. Claude in Chrome 등의 브라우저 에이전트를 활용하면 "○○의 이미지를 웹에서 모아 폴더에 넣어 주세요"라는 지시로 소재 수집도 자동화할 수 있습니다.

YU AI Manager의 생성 이미지를 소재로 활용하는 방향도 유효합니다. SD/ComfyUI/NAI로 생성한 이미지를 그대로 LoRA 소재로 재활용하는 사이클이 성립합니다.

### LoRA 대량 제작 흐름

MCP + Claude Desktop을 활용하면 다음과 같은 완전 자동화가 실현됩니다.

1. 웹에서 소재 수집（Claude in Chrome）
2. YU AI Manager에서 스캔·태깅（MCP）
3. 프로젝트 생성·제외 태그 설정·내보내기（MCP）
4. kohya_ss 학습 시작（MCP）
5. 자기 전에 지시 → 다음 날 아침 LoRA 완성

### 기본 모델 선택

waiSHUFFLENOOB 등 Illustrious 계열 기본 모델은 애니메이션 스타일 생성에 최적화되어 있습니다. 실사 소재（나무 조각 곰 등）를 학습시키면 흰색/크림색 계열의 색감이 되기 쉽습니다.

실사에 가까운 질감을 원하는 경우 realisticPhoto 계열 기본 모델을 선택합니다. LoRA는 학습할 때 사용한 기본 모델과 동일한 모델에서 사용해야 합니다.

---

## 요약

YU AI Manager + MCP + kohya_ss 흐름을 통해 LoRA 제작에 드는 공수를 대폭 줄일 수 있습니다.

- 소재 이미지부터 전체 epoch 학습까지 MCP 지시만으로 완주
- 자연어 지시로 전체 흐름이 동작
- 생성 이미지에서 학습 대상의 조형이 명확하게 표현됨

남은 과제는 소재 수집의 자동화뿐이며, 브라우저 에이전트와 결합함으로써 완전 자동화가 시야에 들어옵니다.
