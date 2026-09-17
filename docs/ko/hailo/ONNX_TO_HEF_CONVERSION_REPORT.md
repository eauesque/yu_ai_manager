# ONNX에서 HEF로의 변환 보고서

**실시일**: 2026-03-06
**목적**: WD-Tagger ONNX 모델을 Hailo HEF 형식으로 변환하여, Raspberry Pi 5 + AI HAT 2 (Hailo-10H)에서 추론 가능하게 만들기
**결과**: 실패 (모든 모델 변형에서 변환 불가)

---

## 환경

| 항목 | 상세 |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (uv로 설치) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## 시도한 모델

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **소스**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **입력**: `[batch, 448, 448, 3]` float32
- **출력**: `[batch, 10861]` float32
- **결과**: 실패
- **오류**: `IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **원인**: LayerNormalization의 축 변환이 DFC v5.2.0에서 미지원

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **소스**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **입력**: `[batch, 448, 448, 3]` float32
- **출력**: `[batch, 10861]` float32
- **결과**: 실패
- **오류**: 상동 (`IndexError` in `_convert_axes_to_nhwc`)
- **원인**: ViT도 LayerNormalization을 사용하고 있어 같은 지점에서 실패

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **소스**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **입력**: `[batch, 448, 448, 3]` float32
- **출력**: `[batch, 10861]` float32
- **결과**: 실패
- **오류**: `UnsupportedShuffleLayerError` (다수의 Transpose 노드) + `UnsupportedModelError` (Mul의 shape 불일치)
- **원인**: ConvNeXt의 channels-last 설계에 따른 Transpose 연산이 DFC 미지원

---

## 실패의 근본 원인

DFC v5.2.0의 ONNX 파서가 다음 연산을 올바르게 처리하지 못함:

1. **LayerNormalization**: 3차원 이상의 텐서에 대한 LayerNorm의 NHWC 축 변환에서 인덱스 오류 발생
2. **Transpose (Shuffle)**: ConvNeXt의 channels-last/first 변환에 사용되는 Transpose 패턴이 미지원

WD-Tagger의 모든 변형 (SwinV2, ViT, ConvNeXt)은 모두 LayerNormalization을 많이 사용하는 현대적 아키텍처이며, DFC v5.2.0에서는 변환이 불가능하다.

---

## 캘리브레이션 데이터

- ComfyUI / Stable Diffusion forge의 출력 이미지에서 랜덤으로 500장을 선정
- WD-Tagger와 동일한 전처리 (RGBA→RGB 흰색 배경 합성, 종횡비 유지 리사이즈, 흰색 패딩, BGR 변환)를 적용
- `calibration_data.npy`로 저장했으나, 변환 단계에 도달하지 못해 미사용

---

## 향후 가능성

- **DFC 향후 버전**: Hailo가 LayerNormalization / Transpose 지원을 개선한 경우, 재시도할 가치가 있음
- **모델 개조**: LayerNorm을 BatchNorm으로 치환한 개조 모델 생성 (공수가 크고, 정확도 열화 위험 있음)
- **현상 유지**: ONNX Runtime (CPU)에서의 추론을 계속 사용
