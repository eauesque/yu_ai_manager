# Hailo-10H 설정

Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU)를 YU AI Manager에서 사용하기 위한 호스트 측 설정 단계입니다. 하드웨어 및 OS 관련 부분은 PyPI에서 완료할 수 없으므로 일부 수동 준비가 필요합니다.

> **대상**: Hailo-10H 하드웨어가 장착된 Raspberry Pi 5 (8 GB 권장)에서 Hailo 관련 확장 기능 (GenAI 채팅 / Semantic Search / YOLO Detect / Tagger / Whisper)을 활성화하려는 경우만 해당합니다. Hailo HW가 없는 환경에서는 이 페이지의 작업이 전혀 필요하지 않습니다.

---

## 1. 필수 조건

- Raspberry Pi 5 (8 GB를 강력히 권장. CMA 제한으로 인해 4 GB에서는 여러 모델을 동시에 로드하기 어렵습니다)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (`pyproject.toml`의 `requires-python`에서 `<3.14`로 고정됨. `uv`가 자동으로 3.13을 선택합니다)

---

## 2. PCIe 드라이버 설치

Hailo-10H는 전용 커널 모듈 `hailo1x_pci`를 사용합니다 (HailoRT 5.3.0에서 이전 `hailo_pci`에서 이름 변경됨).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

재부팅 후 확인:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

예상 결과:

- `hailo1x_pci`가 로드됨
- `/dev/h1x-0` 장치 노드가 존재 (이전 `/dev/hailo0` 아님)
- `dmesg`에 `Firmware loaded in NNNN ms` `Device created at /dev/h1x-0` 행이 있음

> **`/dev/hailo0`이 없어 보여도 문제없습니다**. HailoRT 5.3.0 이후 `/dev/h1x-0`이 기본값이며, 본 애플리케이션은 둘 다 인식합니다 (`core/llm_router/hailo_detect.py`).

---

## 3. HailoRT (시스템 측) 설치

`hailortcli` 바이너리 및 `libhailort.so` 공유 라이브러리. `hailo-all` 패키지에 포함되어 있지만 최신 버전이 필요한 경우 Hailo Developer Zone에서 `.deb`를 가져와 덮어씁니다.

확인:

```bash
hailortcli fw-control identify
```

예상 출력 (주요 내용):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Python wheel (`hailort-*.whl`) 준비

이는 PyPI에서 배포하지 않는 부분입니다. **aarch64용 Hailo Python wheel은 Hailo Developer Zone에도 없으므로 직접 구축해야 합니다.**

### 4.1 소스에서 빌드

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# 완료되면 빌드 트리 내에 hailort-5.3.0-cp313-cp313-linux_aarch64.whl이 생성됩니다
```

(빌드 단계의 세부 정보 및 종속성은 Hailo 공식 README를 참조하세요.)

### 4.2 wheel을 홈 디렉토리에 배치

빌드된 wheel을 다음 **어느 곳이든** 복사하면 본 애플리케이션이 시작할 때 자동으로 감지합니다:

| 탐색 위치 (우선순위) | 용도 |
|---|---|
| `$HAILORT_WHEEL` 환경 변수 | 임의의 전체 경로 지정 (최우선) |
| `$HOME/share/` | **권장 위치** |
| `$HOME/hailort/` | 소스 위치에 빌드 트리를 유지하는 경우 |
| `$HOME/Downloads/` | 다운로드 후 임시 위치 |
| `$HOME/` (직접) | 최후의 보험 |

권장 위치:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 자동 설치 메커니즘

`./start.sh` 실행 시 `scripts/install_hailo.py`가 실행되어

1. venv 내에서 `import hailo_platform`이 성공하는지 확인
2. 실패할 경우에만 위의 탐색 위치에서 **현재 Python 버전 (cp313) + 아키텍처 (aarch64)와 일치하는** wheel을 검색
3. 찾은 최신 wheel을 `uv pip install`로 설치
4. wheel이 없거나 이미 설치된 경우 아무것도 하지 않음 (조용한 무동작)

즉, 수동 `uv pip install`은 필요하지 않습니다. wheel을 홈 디렉토리에 놓고 `./start.sh`를 다시 시작하기만 하면 복구됩니다.

---

## 4.4 HEF 모델 파일 배치

각 확장 기능에서 사용하는 HEF 파일 (NPU용으로 컴파일된 모델)을 `~/hailo_models/`에 배치합니다.

| 파일 | 용도 | 크기 목안 |
|---|---|---:|
| `yolov8n.hef` | YOLO 객체 탐지 | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **의미론적 검색 (CLIP 이미지)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | 의미론적 검색 (CLIP 텍스트, 선택) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | 음성 인식 | 75-405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM 채팅 | 2.9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (이미지+텍스트) | 3.2 GB |

Hailo Model Zoo의 S3 bucket에서 인증 없이 직접 다운로드할 수 있습니다 (URL 형식):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

예 (CLIP 이미지 인코더):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **HEF 파일이 부족하면 확장 기능이 `사용 불가` 표시됩니다**. 예를 들어, 의미론적 검색 상태가 `hailo-10h (CLIP HEF 미배치)`로 표시되면 `clip_vit_b_16_image_encoder.hef`가 `~/hailo_models/`에 없다는 뜻입니다. 하드웨어나 Python 런타임 문제와 구분하기 쉽도록 `runtime_ok` / `hardware_ok` / `hef_ok`의 3단계 원인이 응답에 포함됩니다 (상태 텍스트 위에 마우스를 올려 세부 정보 보기).

`HAILO_HEF_DIR` 환경 변수로 다른 디렉토리를 지정할 수도 있습니다.

---

## 5. 커널 매개변수 (CMA)

Hailo의 GenAI 모델 (LLM/VLM/Whisper)은 DMA용 CMA (연속 메모리 할당기)가 필요합니다.

`/boot/firmware/cmdline.txt`의 끝에 추가:

```
cma=256M
```

> **Pi 5 (8 GB)에서 `cma=1G` 또는 `cma=512M`은 조용히 실패합니다**. 기본 커널이 `numa=fake=8`을 적용하므로 CMA는 단일 NUMA 노드 경계 (1 GB) 내에 있어야 하며, `256M`을 초과하면 `CmaTotal=0`이 됩니다 (패닉 없음). 자세한 정보: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

재부팅 후 확인:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB이면 성공
```

`0 kB`인 경우 값을 확인하고 필요하면 낮추세요.

---

## 6. hailo-ollama와의 공존 (선택)

동일 장치에서 `hailo-ollama` (Ollama의 Hailo NPU 버전)를 실행하는 경우:

- **HailoRT 5.3.0 이후**: `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama`로 시작하면 yu_ai_manager 측 (group_id `YU_SHARED`)과 물리 장치를 공유하고 HailoRT 스케줄러가 ROUND_ROBIN으로 시간 분할합니다
- **5.2.0 이전**: group_id를 받지 않으므로 yu_ai_manager 시작 전에 `systemctl stop hailo-ollama`로 중지해야 합니다

---

## 7. 동작 확인

`./start.sh` 시작 후 WebUI의 **설정 → 확장 기능**에서 다음이 활성화되면 성공입니다:

- `builtin_hailo_genai` (Hailo 채팅 / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP 의미론적 검색)
- `builtin_hailo_yolo_detect` (YOLO 객체 탐지)

또는 CLI에서 직접:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. 문제 해결

### Hailo 관련 확장 기능이 모두 「로드되지 않음」으로 표시됨

→ Python wheel이 설치되지 않았을 가능성이 높습니다. 다음을 확인하세요:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

`ModuleNotFoundError`이면 wheel을 홈 디렉토리에 놓은 후 `./start.sh`를 다시 시작하세요 (§4.2).

### `hailortcli fw-control identify`가 `HAILO_OPEN_FILE_FAILURE`로 실패

→ 드라이버 또는 장치 노드 문제입니다. `lsmod | grep hailo1x`에서 `hailo1x_pci`가 로드되었는지, `ls /dev/h1x-0`이 존재하는지 확인하세요. 둘 다 없으면 §2를 다시 수행한 후 재부팅하세요.

### LLM/VLM 로드 시 `HAILO_OUT_OF_HOST_MEMORY` / Pi 정지

→ CMA 부족입니다. `grep CmaTotal /proc/meminfo`에서 256 MB가 있는지 확인하세요 (§5). `VDevice.release()`는 CMA를 반환하지 않으므로 여러 모델을 반복해서 전환한 후 프로세스 재시작이 필요할 수 있습니다.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ 다른 프로세스가 VDevice를 점유 중입니다. `lsof /dev/h1x-0`으로 범인을 특정하세요 (일반적으로 `hailo-ollama` 또는 Ctrl+C로 제대로 종료하지 못한 이전 프로세스), 그 후 `kill`하고 재시작하세요.

### Python이 3.14로 업그레이드되어 wheel과 호환되지 않음

→ 본 저장소는 `pyproject.toml`에서 `requires-python = ">=3.13,<3.14"`로 고정되었습니다. clone 후 첫 번째 `uv sync`에서 3.13.x가 선택됩니다. 수동으로 `.python-version = 3.14`를 작성했다면 되돌려 놓으세요.

---

## 9. 관련 문서

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Hailo-10H 개발 문서 목차
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 마이그레이션 설명
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Pi 5의 CMA 제한 세부 정보
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — wheel 자동 감지 스크립트 본체
