# DFC 변환 추적 보고서: DFC v5.3.0의 WD-Tagger 모델

**작성일**: 2026-04-06
**DFC 버전**: 5.3.0
**관련 문서**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**환경**: WSL2 (Ubuntu 24.04), x86_64

---

## 배경

2026년 3월에 저는 세 가지 WD-Tagger 변형
(SwinV2, ViT, ConvNeXt)이 모두 Hailo Dataflow Compiler v5.2.0에서 파서 단계에서 실패했으며,
양자화 단계에 도달하지 못했음을 보고했습니다. 원본 보고서는
[`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md)에 보존되어 있습니다.

저는 이제 DFC v5.3.0에서 세 모델을 모두 다시 테스트했습니다.
이 문서는 그 추적 보고서입니다.

---

## 결과 요약

| 모델 | 크기 | DFC 5.2.0 오류 | DFC 5.3.0 오류 | 변화 |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `_convert_axes_to_nhwc`의 `IndexError` | 동일 | **없음** |
| `wd-vit-tagger-v3` | 362 MB | 동일 | 동일 (onnxsim 재시도 후) | 재시도 흐름 추가됨 |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | 동일 + 추가 `UnsupportedModelError` | **오류 증가** |

**세 모델 모두 여전히 파서 단계에서 실패합니다.** 
양자화 단계(500개의 보정 이미지가 준비됨)는 v5.2.0 실행과 마찬가지로 도달 불가능한 상태로 남아 있습니다.

---

## DFC v5.3.0에서 변경된 사항

실패는 계속되지만, DFC v5.3.0에서 v5.2.0과 비교하여 다음과 같은 개선 사항이 보입니다:

### 1. `_create_layer_normalization_layer` 메서드 추가

이 메서드는 v5.2.0에 전혀 존재하지 않았습니다. DFC v5.3.0은 이제 `LayerNormalization` 연산자를 명시적으로 처리하려는 시도를 합니다.
이는 개발 노력이 지속되고 있다는 명확한 신호입니다.

그러나 **내부 구현이 불완전합니다**: 메서드가 호출되지만, 그 내부의 `_convert_axes_to_nhwc` 호출은 여전히 v5.2.0에서 실패했던 동일한 텐서 모양에서 `IndexError: list index out of range`를 발생시킵니다.

### 2. onnxsim 단순화 + 재시도 흐름 추가

ViT와 ConvNeXt의 경우, DFC v5.3.0은 이제 `onnxsim`을 사용하여 입력 ONNX 모델을 자동으로 단순화하고 파싱을 다시 시도합니다.
단순화된 모델은 입력 옆에 `model.sim.onnx`로 저장됩니다. 이는 중복되거나 복잡한 ONNX 그래프를 가진 모델에 대한 유용한 새로운 안전망입니다.

이러한 특정 모델의 경우, 재시도는 **정확히 같은 지점에서 실패합니다** 원본 파싱처럼, 근본 원인이 ONNX 그래프 구조가 아니라 `_convert_axes_to_nhwc`에 있기 때문입니다.

### 3. 엔드 노드 권장사항

ConvNeXt의 경우, DFC v5.3.0은 이제 파서가 실패할 때 엔드 노드에 대한 구체적인 권장사항을 제시하고, 사용자에게 이러한 노드를 고정하여 재시도하도록 유도합니다. 이는 생각 깊은 UX 개선입니다.

권장 엔드 노드를 사용한 재시도도 실패합니다. 역시 근본 원인이 LayerNormalization / Transpose 처리에 있으며, 엔드 노드 선택에 있지 않기 때문입니다.

---

## 근본 원인 (3월 이후 변경 없음)

DFC ONNX 파서는 입력 텐서가 예상되는 NCHW 형식을 따르지 않을 때 `LayerNormalization` 연산자의 축을 올바르게 변환할 수 없습니다. 관련된 호출 체인은 이제 다음과 같습니다:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

ConvNeXt의 경우 특히, 여러 `Transpose` 노드(`token_5`부터 `token_34`까지)의 추가 `UnsupportedShuffleLayerError`는 Transpose 연산자 처리도 이 아키텍처가 사용하는 채널-마지막 패턴에 대해 불완전한 상태로 남아 있음을 나타냅니다.

간단히 말해: **새로운 코드 경로는 존재하지만, 원래 실패했던 경우를 아직 처리하지 못합니다.**

---

## 요청사항 (3월 이후 변경 없음)

3월 게시물의 두 가지 요청사항은 여전히 유효합니다:

### 1. 다차원 `LayerNormalization`에 대해 `_convert_axes_to_nhwc` 수정

메서드는 이제 도달 가능합니다(좋습니다). 하지만 축 매핑 로직 자체는 NCHW가 아닌 입력 텐서에 대해 실패합니다. 현대 Transformer 아키텍처(SwinV2, ViT, ConvNeXt)는 모두 이것이 작동해야 합니다.

### 2. Hailo-10H를 위한 ONNX Runtime 실행 공급자

이는 전체 DFC 변환을 선택적으로 만들고 이 클래스의 문제를 구조적으로 해결합니다. 많은 커뮤니티 사용자들이 완전히 양자화된 HEF보다 낮은 처리량일지라도 Hailo-10H에서 직접 수정되지 않은 ONNX 모델을 실행할 수 있으면 이점을 받을 것입니다.

---

## "ONNX Runtime Hailo Pipeline" 컴포넌트에 대한 참고사항

DFC v5.3.0 릴리스 노트는 "ONNX Runtime Hailo Pipeline" 컴포넌트를 언급합니다. 이를 사용하여 WD-Tagger 추론을 Hailo-10H에서 **전체 DFC 변환 없이** 실행할 수 있다면
(즉, 지원되는 부분 그래프를 NPU로 위임하는 ONNX Runtime 실행 공급자로서), 올바른 접근 방식에 대한 공식 지침을 매우 감사하겠습니다.

구체적으로:

- 이 컴포넌트가 DFC가 현재 파싱할 수 없는 모델들을 위한 경로로 의도되었습니까?
- 부분 HEF(즉, 파싱 가능한 부분 그래프를 HEF로 컴파일하고 나머지는 ORT를 통해 CPU에서 실행)를 필요로 합니까?
- Transformer 스타일의 ONNX 모델과 함께 사용하는 방법을 보여주는 샘플 코드나 튜토리얼이 있습니까?

---

## 재현 방법

이러한 결과를 재현하기 위한 정확한 단계:

```bash
# 1. 깨끗한 Python venv에서 DFC v5.3.0 설정
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. 세 개의 WD-Tagger ONNX 모델 다운로드
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. 각 모델의 파싱 시도
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

각 실행의 전체 오류 로그는 요청 시 제공됩니다.

---

## 테스트 환경

| 항목 | 세부사항 |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| 모델 | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| 보정 데이터 | 500개 ComfyUI / SD 출력 (사용되지 않음 — 양자화 단계에 도달하지 못함) |

---

## 마무리

DFC v5.3.0에서 보이는 개발 노력
(`_create_layer_normalization_layer`, onnxsim 재시도 흐름, 엔드 노드 권장사항)은 진정으로 고무적입니다 — 이는 정확히 커뮤니티가 보기를 원했던 진전의 종류입니다. 남은 격차는 이제 도달 가능하지만 아직 이러한 모델에 대해 올바르지 않은 `_convert_axes_to_nhwc` 내부의 실제 구현입니다.

저는 각 DFC 릴리스마다 계속 재테스트하고 상황이 변함에 따라 추적 보고서를 게시할 예정입니다. Hailo의 누군가가 이를 읽고 전체 오류 로그, ONNX 모델 SHA-256 해시, 또는 최소 재현자를 원한다면 기꺼이 제공하겠습니다.
