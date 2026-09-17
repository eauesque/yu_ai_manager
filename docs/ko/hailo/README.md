# Hailo-10H AI Hat+ 개발 문서

Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H)을 사용한 AI 추론 구현 기록입니다.

공식 문서가 부족한 영역에서의 실제 개발을 통해 얻은 실무 지식을 공유합니다.

## 문서 색인

| 파일 | 설명 |
|------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 마이그레이션 노트: API 차이, 디바이스 노드 이름 변경 (`/dev/h1x-0`), HEF 호환성, smoke-test 스크립트 |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | 여러 모델 (YOLO/CLIP/LLM/VLM/Whisper)이 단일 프로세스에 공존할 수 있게 하는 공유 VDevice 관리자 구현 패턴 |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Pi 5 CMA 할당 제한 (`numa=fake=8` 하에서의 동작). `cma=1G`이 무음으로 실패하는 이유, 확인된 상한이자 권장값인 `cma-512` (`config.txt`의 `dtoverlay=cma,cma-512`), Hailo GenAI 메모리 요구사항, `VDevice.release()`의 CMA 미반환 동작 |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP 시맨틱 검색 개발 로그. 단계별 구현 기록, 직면한 문제와 해결책 |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo 디바이스 제어 방법, VDevice 관리, 배타적 접근 제어, 모델 전환 |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX를 HEF로 변환하는 절차. Dataflow Compiler, 양자화, 문제 해결 |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | 변환 검증 보고서 (DFC v5.2.0). 3개 WD-Tagger 변형의 상세한 실패 분석 |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 후속 조치. 동일 3개 WD-Tagger 모델의 재테스트 (여전히 실패), 그리고 v5.3.0 개선사항 (새로운 `_create_layer_normalization_layer`, onnxsim 재시도 흐름, 종료 노드 권장사항) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX 멀티백엔드 개발 로그. Hailo 하드웨어가 없는 환경을 위한 폴백 |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **CMA leak의 구조적 제약과 실측**. `VDevice.release()`가 회수하지 않는다는 것, 추론 중의 지속적 leak (약 14 MB/분), 그리고 **자식 프로세스 kill로도 process exit로도 module unload로도 회수되지 않는다**는 것 (Phase 0 PoC에서 2회 독립 실측, SIGTERM + 30초 대기로 +8 MB뿐). 확실한 회수 수단은 Pi 본체의 reboot뿐 **(구 결론. HailoRT / driver 5.4.0에서의 재시험으로 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8에서 정정 완료)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **위 CMA leak 판정의 정정과 재검증**. HailoRT / driver 5.4.0에서 공식 vanilla와 `FOLL_LONGTERM` 수정판을 A/B 비교하여, 구 판정이 초회 HEF 로드 후의 `CmaFree` 절대 회복량만을 본 오판정이었다고 정정. v5.3.0 → v5.4.0의 소스 diff, 자체 빌드 절차의 함정, 실측 데이터 포함 |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | 위 내용을 받아 채택된 자동 reboot 방침의 운영 가이드. 관측 단계 (`would_fire`만 기록하고 재부팅하지 않음), 판정 임계값, 기본값 `mode = "off"`인 이유 |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | 동일 단계의 현재 환경용 런북. 관측 시작·확인·종료 절차 |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | cold_load (~71초) 중 Quart event loop가 GIL로 인해 멈추는 문제를, LLM chat 추론의 subprocess 격리로 해결한 구현 로그 |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Hailo-10H 생태계 평가 (2026-03-19, HailoRT/DFC v5.2.0 기준) |

## 중요한 알려진 문제

### 환경 / Raspberry Pi 5

- **Pi 5 (8 GB)에서 CMA 상한은 512 MB이며, 설정 위치는 `config.txt`입니다**: 기본 커널이 `numa=fake=8`을 적용하여 RAM을 8 × 1 GB NUMA 노드로 분할합니다. CMA는 단일 노드 경계 내에 들어와야 하며, `cma-1024`와 `cma-768`은 무음으로 실패합니다 (`CmaTotal=0`, 커널 패닉 없음). **`cma-512`가 확인된 상한이자 권장값입니다** (2026-05-16에 overlay 경유로 재검증, `CmaTotal: 524288 kB`). 2026-05 firmware 리그레션으로 인해, cmdline `cma=`가 아니라 `/boot/firmware/config.txt`의 `dtoverlay=cma,cma-512`를 사용해야 합니다. 자세한 내용은 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 참조
- **재부팅 후 항상 CMA 확인**: `grep CmaTotal /proc/meminfo` — 0이면 설정이 무음으로 무시되었다는 뜻
- **`VDevice.release()`는 CMA를 반환하지 않음**: CMA는 OS 세션 전체 수명 동안 유지됩니다. VDevice를 세션 범위의 싱글톤으로 취급하십시오. **프로세스 재시작으로도 회수되지 않음** —— 자식 프로세스 kill·process exit·module unload 어느 쪽으로도 회수되지 않는다는 것이 Phase 0 PoC에서 2회 독립적으로 실측되었습니다 (SIGTERM + 30초 대기로 +8 MB뿐, 기대값 ≥250 MB). 확실한 회수 수단은 Pi 본체의 `sudo reboot` (PCIe power-cycle)뿐입니다. 상세와 채택된 대처는 [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) 참조. **정정**: 본 항목은 구 측정에 기반합니다. HailoRT / driver 5.4.0에서의 A/B 재시험에서는 실용상의 CMA 누수가 재현되지 않았으며, [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8에서 정정 완료
- **`numa=fake=8`은 Node.js 설치에 영향을 미침**: 노드당 메모리 (1 GB)가 총 RAM으로 잘못 감지되어 npm/node 설치 관리자가 중단됩니다. 상류로 보고됨: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel은 소스 빌드 필요**: PyPI나 Hailo Developer Zone에 aarch64 wheel이 없음
- **hailo-ollama와의 상호 배제**: VDevice 사용 중에는 hailo-ollama를 중지해야 함
- **프로세스 종료 시 VDevice 누수**: `lsof /dev/hailo*`로 확인하고 `kill PID`로 해결

### VDevice / API

- **InferModel API 사용**: `VDevice.create_infer_model()`이 올바른 접근 방식입니다. 레거시 VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`)는 Hailo-10H에서 `HAILO_NOT_IMPLEMENTED`를 반환합니다
- **InferModel은 단순 모델만 지원**: 단일 입력 YOLO HEF는 작동하지만, 2입력 4출력 Whisper HEF의 경우 `configure()`가 `HAILO_INVALID_ARGUMENT`를 반환합니다. 복잡한 모델의 경우 GenAI SDK 사용
- **VDevice는 하나의 물리 디바이스로 매핑**: 두 개의 `VDevice()` 인스턴스를 동시에 생성하면 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 발생
- **모델 전환 시 VDevice 완전히 해제**: Python 참조를 단순히 `None`으로 설정하는 것은 불충분합니다. 새로운 VDevice를 생성하기 전에 `VDevice.release()`를 사용하여 물리 디바이스를 명시적으로 해제하세요
- **`set_format_type(FormatType.FLOAT32)`은 hailort 5.2.0에서 지원되지 않음**: `format_type` 속성이 없습니다. 수동으로 uint8 양자화/역양자화를 처리하거나 GenAI SDK 사용
- **출력은 uint8 양자화됨**: 출력 버퍼를 float32로 할당하면 `buffer size mismatch` 발생합니다. uint8로 할당하고 역양자화 매개변수 (scale, zero_point)를 사용하여 float32로 변환하세요

### GenAI (LLM / VLM / Speech2Text)

- **HailoRT 5.3.0에서 `temperature=0.0`은 거부됨**: `LLM.generate()`가 `temperature=0`에서 `HAILO_INVALID_ARGUMENT` 발생. 호출하기 전에 클램핑: `temperature = max(temperature, 0.01)`. OpenAI 호환 클라이언트가 기본값으로 `temperature=0`을 전송하는 경우에 영향
- **GenAI × 2 동시 로드 가능**: LLM + Whisper-tiny를 동일한 VDevice에서 동시에 로드할 수 있음 (HailoRT 5.3.0에서 확인). 둘 다 로드된 경우 CMA 여유: 256 MB 중 약 10 MB. Whisper-base 이상은 오버플로우 가능성 높음
- **LLM + Whisper-tiny CMA 예산**: 약 246 MB (측정됨). 전체 모델 CMA 수치는 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 참조

### Whisper (음성 인식)

- **GenAI SDK 사용**: `hailo_platform.genai.Speech2Text`가 전체 파이프라인을 제공합니다. NPU에서 인코더+디코더 전체 실행
- **HEF는 디코더 전용**: `Whisper-Base.hef`는 2개 입력 (encoder_features + token_embeddings)과 4개 출력 (어휘가 4개로 분할됨). InferModel API에서 작동하지 않음
- **GenAI SDK 입력**: 리틀 엔디언 float32 (`<f4`), [-1,1]로 정규화된 PCM 오디오 데이터
- **ONNX 폴백**: GenAI SDK를 사용할 수 없을 때 HuggingFace ONNX 모델을 사용하여 CPU에서 인코더+디코더 실행

### YOLO (객체 감지)

- **InferModel API에서 작동**: 단일 입력 HEF는 문제 없음
- **ONNX 폴백**: Hailo를 사용할 수 없을 때 `yolo11n.onnx`가 자동으로 다운로드됨. 출력 `(1,84,8400)`은 yolov8n과 호환
- **초기화 실패 쿨다운**: 엔진 초기화 실패 후 60초간 재시도 억제

### 분산 추론

- **상태 확인 필요**: 분산 처리를 시작하기 전에 `filter_available()`을 사용하여 원격 노드 상태 확인
- **원격 실패 시**: 남은 항목은 로컬 처리로 폴백됩니다. 복구된 노드는 다음 배치에서 자동으로 감지됨
- **워크로드 분산**: GPU와 NPU 간의 속도 차이가 크므로 균등 분배가 비효율적입니다. 처리량 측정을 기반으로 한 동적 할당은 향후 과제
