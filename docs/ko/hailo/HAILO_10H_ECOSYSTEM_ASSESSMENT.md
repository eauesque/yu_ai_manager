# Hailo-10H 에코시스템 평가

**작성일**: 2026-03-19
**대상**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)
**HailoRT**: v5.2.0
**DFC**: v5.2.0
**목적**: 본 프로젝트에서의 Hailo-10H 개발 경험을 기록하고, 현실적인 제약과 향후 전망을 정리한다

---

## 종합 평가

**하드웨어는 우수하다. 소프트웨어 에코시스템이 결정적으로 부족하다.**

Hailo-10H는 40 TOPS의 추론 성능을 갖춘 NPU이며, 하드웨어로서의 잠재력은 충분하다. 그러나 소프트웨어 툴체인이 폐쇄적이고 미성숙하여, 개발자가 자유롭게 모델을 가져와 실행하는 것이 **사실상 불가능하다**.

본 프로젝트에서는 CLIP 시맨틱 검색, YOLO 물체 감지, LLM/VLM 채팅, Whisper 음성 인식, 분산 태거 서버 등 Hailo-10H를 다방면으로 활용하는 개발을 진행해왔으나, 안정적으로 동작하는 것은 **모두 Hailo 공식 Model Zoo에서 다운로드한 사전 컴파일된 HEF를 사용**한 것이며, 직접 ONNX에서 HEF로 변환에 성공한 사례는 **단 한 건도 없다**.

---

## 본 프로젝트에서의 구현 현황

### 동작 중인 기능 (모두 공식 HEF 다운로드)

| 기능 | 사용 API | HEF 입수처 |
|------|---------|-----------|
| CLIP 이미지 인코더 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO 물체 감지 | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM 채팅 | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM 이미지+텍스트 추론 | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper 음성 인식 | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### 동작하지 못한 기능 (HEF 변환 실패)

| 기능 | 시도한 내용 | 결과 |
|------|-----------|------|
| WD-Tagger (SwinV2) | ONNX → HEF 변환 | DFC가 LayerNormalization을 처리하지 못해 실패 |
| WD-Tagger (ViT) | ONNX → HEF 변환 | 동일 |
| WD-Tagger (ConvNeXt) | ONNX → HEF 변환 | DFC가 Transpose 연산을 처리하지 못해 실패 |

### 구현의 주목할 점

본 프로젝트에서는 `hailo_platform` wheel의 Python API를 **직접 호출하여** 모든 기능을 구현하였다. hailo-ollama나 hailo-apps는 사용하지 않았다.

특히 다음은 Hailo사가 공식적으로 제공하기 전에 자체 구축한 것이다:

- **VDevice 배타 제어 디바이스 매니저** — CLIP/YOLO/LLM/VLM/S2T를 단일 VDevice로 자동 전환. hailo-apps에는 디바이스 공유 메커니즘이 없음
- **멀티 백엔드 폴백** — Hailo → CoreML → ONNX Runtime을 투명하게 자동 전환
- **uint8 역양자화 파이프라인** — `quant_info`의 scale/zero_point로부터 float32를 복원
- **LAN 분산 추론 아키텍처** — 복수 머신의 워크 스틸링 병렬 태깅

이러한 개발은 **API 문서가 거의 존재하지 않는 상태에서** 수행되었다. InferModel API의 입출력 사양, 버퍼 크기 요건, 양자화 파라미터 취득 방법은 전부 에러 메시지와 소스 코드 추측을 통해 해명하였다.

---

## Hailo Dataflow Compiler (DFC)의 문제

### DFC란

ONNX / TensorFlow 모델을 Hailo-10H용 HEF (Hailo Executable Format)로 변환하기 위한 컴파일러. x86_64 Linux에서 동작하며, 다음 파이프라인으로 모델을 변환한다:

```
model.onnx → HAR (float32) → 최적화 → 양자화 (INT8) → 컴파일 → model.hef
```

### 현실

**DFC는 Hailo가 자사 Model Zoo용으로 사전 검증한 아키텍처만 제대로 변환할 수 있다.**

본 프로젝트에서의 변환 시도 (2026-03-06, DFC v5.2.0):

| 모델 | 크기 | 에러 | 도달 단계 |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | 최적화 전 |
| wd-vit-tagger-v3 | 362 MB | 동일 | 최적화 전 |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | 최적화 전 |

3개 모델 전부 **최적화 단계에 도달하기 전에** 파서 수준에서 실패. 500장의 캘리브레이션용 이미지를 준비했으나 사용되지도 않았다.

### 근본 원인

DFC의 ONNX 파서가 다음 연산자를 처리할 수 없다:

- `LayerNormalization` (다차원 텐서에서의 축 변환)
- `Transpose` (channels-last/first 변환 패턴)

이것들은 Transformer 계열 아키텍처 (SwinV2, ViT, ConvNeXt 등)의 기본 구성 요소이며, 2022년 이후 주류 모델의 대다수가 사용하고 있다.

### DFC의 실질적 대응 범위

| 아키텍처 | DFC 대응 | 근거 |
|---------------|---------|------|
| ResNet, MobileNet 등 CNN 계열 | ✓ 대응 | Model Zoo에 다수 존재 |
| YOLO v5/v8/v11 | ✓ 대응 | Model Zoo에 HEF 있음 |
| CLIP ViT (Hailo 버전) | ✓ 대응 | Model Zoo에 HEF 있음 (Hailo사가 변환) |
| SwinTransformer V2 | ✗ 미대응 | LayerNorm 변환 실패 |
| Vision Transformer (범용) | ✗ 미대응 | LayerNorm 변환 실패 |
| ConvNeXt | ✗ 미대응 | Transpose 변환 실패 |

> **참고**: CLIP ViT가 Model Zoo에 있는 것은 Hailo사 내부에서 특별한 대응 (수동 그래프 변환이나 커스텀 파서)을 했을 가능성이 높다. 같은 ViT라도 일반 사용자가 DFC로 변환하면 실패한다.

---

## HEF 포맷의 문제

- **바이너리 사양이 비공개** — Hailo는 포맷 문서를 공개하지 않고 있다
- **DFC 외에 생성 수단이 없다** — 서드파티 도구로 HEF를 만드는 것이 불가능하다
- **리버스 엔지니어링도 비현실적** — NPU의 명령어 세트와 데이터플로우 아키텍처에 대한 지식이 필요하다

즉, DFC가 변환할 수 없는 모델은 **어떤 방법으로도 Hailo-10H에서 실행할 수 없다**. 대안은 존재하지 않는다.

---

## 개발 툴체인 평가

### hailo_platform (Python SDK)

| 항목 | 평가 |
|------|------|
| InferModel API | 동작하지만 문서가 극히 부족 |
| GenAI API (LLM/VLM/S2T) | 비교적 사용하기 쉬움. 단 undocumented 동작 다수 |
| Python wheel 배포 | PyPI에 없음. aarch64 wheel은 소스에서 빌드 필요 |
| 에러 메시지 | 최소한의 수준. 버퍼 크기 불일치 원인 특정이 어려움 |
| VDevice 관리 | 배타적 접근만 가능. 멀티 모델 동시 이용 불가 |

### 개발 중 해명한 undocumented 동작

1. **InferModel API가 정답** — 구 VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`)는 Hailo-10H에서 `HAILO_NOT_IMPLEMENTED`를 반환
2. **출력은 uint8 양자화** — float32로 버퍼를 확보하면 `buffer size mismatch`. uint8로 확보한 후 역양자화가 필요
3. **`input()`/`output()`은 프로퍼티** — 메서드가 아님 (다른 Hailo API와 일관성이 없음)
4. **`quant_info` 취득** — `infer_model.output().quant_info`로 scale/zero_point를 얻을 수 있으나, 이를 설명하는 문서는 존재하지 않음
5. **hailo-ollama와의 배타** — VDevice 사용 중에는 hailo-ollama를 중지해야 함. 에러 메시지에서는 원인을 파악하기 어려움

---

## 경쟁 제품과의 비교

### Ryzen AI (XDNA) NPU

| 항목 | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| 성능 | 40 TOPS | 16~50 TOPS (세대에 따라 상이) |
| 모델 반입 | DFC로 변환 필수, 대부분 실패 | **ONNX Runtime이 직접 대응** |
| 개발자 경험 | 독자적 툴체인, 문서 부족 | `pip install onnxruntime-directml`로 완료 |
| 에코시스템 | 폐쇄적, Model Zoo 의존 | ONNX / DirectML / Microsoft 공동 |
| 보급 대수 | Pi + AI HAT, USB 동글 (예정) | **수백만 대의 노트북 PC에 내장 완료** |

Ryzen AI에서의 통합은 다음만으로 완결된다:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Hailo-10H에서는 같은 일이 불가능하다. ONNX Runtime Execution Provider가 존재하지 않는다.

### NVIDIA CUDA

| 항목 | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| 모델 반입 | DFC 경유, Model Zoo 외에는 대부분 실패 | ONNX / PyTorch / TensorFlow → 그대로 실행 가능 |
| 툴체인 | 미성숙 / 반폐쇄 | 성숙 / 공개 / 대량의 문서 |
| 개발자 커뮤니티 | 극소 | 세계 최대 |
| 가격대 | 저렴 ($70 정도) | 고가 ($200~$2000+) |

Hailo의 유일한 우위는 **가격과 소비 전력**이다.

---

## hailo-apps (2025-10)와의 관계

### hailo-apps 개요

Hailo사가 2025년 10월에 출시한 공식 애플리케이션 모음. 20개 이상의 샘플 앱을 포함:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: 물체 감지, 포즈 추정, 얼굴 인식, CLIP 분류, OCR
- Standalone: Python/C++ HailoRT 학습용 데모

### 본 프로젝트와의 비교

| 항목 | hailo-apps | 본 프로젝트 |
|------|-----------|-------------|
| VLM 대응 | vlm_chat 앱 | `hailo_platform.genai.VLM` 직접 구현 |
| CLIP | clip 앱 | 시맨틱 검색 시스템으로 통합 |
| LLM | simple_llm_chat | GenAI Extension으로 통합 |
| Whisper | simple_whisper_chat | Speech-to-Text Extension으로 통합 |
| 디바이스 관리 | 없음 (단일 앱 전제) | **배타 제어 디바이스 매니저 (CLIP/YOLO/LLM/VLM/S2T 자동 전환)** |
| 백엔드 폴백 | 없음 | **Hailo → CoreML → ONNX 자동 전환** |
| 분산 추론 | 없음 | **LAN 분산 워크 스틸링** |
| 통합도 | 개별 데모 앱 | 단일 통합 WebUI 애플리케이션 |

본 프로젝트는 hailo-apps가 공개되기 전에 동등 이상의 기능을 `hailo_platform` wheel의 저수준 API로 자체 구현하였다.

---

## 향후 전망

### 단기 (현실적)

- **ONNX Runtime + LAN 분산이 유일한 실용적 해법** — 분산 태거 서버의 ONNX 백엔드로 운용
- Hailo-10H는 공식 HEF가 있는 용도 (YOLO, CLIP, LLM, Whisper)에 한정하여 사용
- 커스텀 모델의 NPU 실행은 포기

### 중기 (희망적)

- ASUS 등에서 Hailo-10H 탑재 USB 동글 발매 → 사용자 증가
- 사용자 증가에 따라 Hailo사에 도구 개선 압력이 가해질 가능성
- DFC의 향후 버전에서 Transformer 계열 지원이 추가될 가능성

### 장기 (구조적 과제)

- Hailo가 ONNX Runtime EP를 제공하지 않는 한, Ryzen AI (XDNA)에 개발자 에코시스템에서 뒤처진다
- USB 동글로 하드웨어가 보급되더라도, 소프트웨어의 자유도가 없으면 "빠른 YOLO가 돌아가는 키" 수준에 머문다
- 40 TOPS의 잠재력이 Model Zoo의 수십 개 모델에서만 사용 가능한 상태가 지속된다

---

## 정리

Hailo-10H는 40 TOPS라는 뛰어난 하드웨어 성능을 갖추고 있으나, 소프트웨어 에코시스템의 폐쇄성과 미성숙함으로 인해 개발자가 자유롭게 모델을 가져와 활용하는 것이 **사실상 불가능한** 상태이다.

본 프로젝트에서는 undocumented API를 수작업으로 해명하면서 Hailo사의 공식 애플리케이션 모음 (hailo-apps) 이상의 통합 소프트웨어를 구축하였다. 그러나 그럼에도 커스텀 모델 (WD-Tagger)의 NPU 실행은 DFC의 제약으로 인해 실현할 수 없었다.

**"도구가 너무 부족하여 개발이 사실상 불가능하다"** — 이것이 수개월에 걸친 Hailo-10H 개발을 거친 솔직한 결론이다.

---

## 관련 문서

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — CLIP 시맨틱 검색 개발 로그 (Phase 1~12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — DFC 변환 가이드 (참고 자료)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — WD-Tagger 변환 실패 보고서
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — CLIP ONNX 폴백 개발 로그
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — VDevice 디바이스 관리 설계
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — 분산 태거 서버 문서
