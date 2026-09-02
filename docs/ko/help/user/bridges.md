# Bridge 연동

Bridge 기능을 사용하면 YU AI Manager에서 각종 AI 이미지 생성 도구로 프롬프트를 직접 전송할 수 있습니다.

## 지원하는 Bridge

### SD WebUI Bridge
Stable Diffusion WebUI (Automatic1111 / Forge)와 연동합니다.
- 프롬프트 송수신
- 생성 파라미터 전송

### NAI Bridge
NovelAI와 연동합니다.
- 프롬프트 구문 자동 변환 (SD ↔ NAI)
- 품질 태그 자동 삽입

#### Vibe Transfer (NAI 포션)와 encode-vibe 캐시

NAI V4+ 모델은 참조 이미지를 생성 요청에 첨부하기 전에 `/ai/encode-vibe` API로
인코딩해야 합니다 (**1회당 2 Anlas** 소비).

동일 이미지로 반복 생성 시 Anlas 낭비를 방지하기 위해 인코딩 결과를 로컬에 캐시합니다:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **키**: 원본 이미지 SHA256 + 모델 이름 + 정보 추출도 (0.01 단위)
- **최대 크기**: 기본 500 MB. Settings > NAI Bridge > "Vibe encode cache (MB)"에서 변경 가능 (0 = 비활성화)
- **LRU 제거**: 한도 초과 시 백그라운드 스레드에서 오래된 순으로 삭제

### ComfyUI Bridge
ComfyUI와 연동합니다.
- 워크플로에 프롬프트 삽입
- 출력 포맷 커스터마이즈

## 배치 생성

세 가지 Bridge 모두 메인 생성 경로에서 배치 생성 (A1111 호환 시맨틱스)을 지원합니다.

### Batch count / Batch size

- **Batch count** — 연속 생성 횟수 (시간 방향). 클라이언트가 1회씩 API를 계속 호출합니다
- **Batch size** — 1회 API 호출에서 병렬 생성하는 장수 (VRAM 방향). NAI Bridge에서는 표시되지 않습니다
- 총 장수 = Batch count × Batch size

고정 Seed인 경우, loop 내에서 seed를 `base + i`로 순번 증가시킵니다 (A1111과 동일한 동작). `-1` (랜덤)인 경우 각 회마다 새로운 랜덤 seed가 사용됩니다.

### 중단 버튼

| Bridge | 단발 (count=1) | loop (count>1) |
|---|---|---|
| NAI | 중단 버튼 없음 | 「현재 생성 완료 후 중단」만 |
| SD WebUI | 「중단」(서버 cancel API) | 「현재 생성 완료 후 중단」+「중단」 |
| ComfyUI | 「중단」(서버 cancel API) | 「현재 생성 완료 후 중단」+「중단」 |

- **중단 (즉시)** — 진행 중인 API 호출을 끊고 loop도 중지합니다. SD WebUI / ComfyUI에서는 서버 cancel API도 호출합니다
- **현재 생성 완료 후 중단** — 현재 생성 중인 이미지를 완성시킨 후, 다음 iteration을 보내지 않습니다

NAI Bridge의 단발 생성에 중단 버튼이 없는 이유는, NAI API가 fetch를 수락한 시점에 Anlas (크레딧)을 소비하기 때문입니다. HTTP 연결을 끊어도 서버 측 생성이나 과금이 멈추지 않으므로, 중단 버튼은 UX 오해를 불러일으킬 뿐이어서 의도적으로 표시하지 않습니다.

### VRAM 주의

Batch size를 높이면 서버 측 GPU의 VRAM 소비가 장수만큼 증가합니다. SDXL × Batch size 4 이상에서 OOM이 발생할 수 있으므로, 처음에는 1부터 시작하세요.

## 품질 프리셋

각 Bridge의 툴바에 있는 「QP」 버튼으로 품질 향상 태그를 원클릭으로 삽입할 수 있습니다.

내장 프리셋:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

커스텀 프리셋도 생성 가능합니다.

## 해상도 프리셋

SD WebUI Bridge와 ComfyUI Bridge의 Width/Height 입력 위에 "Resolution Preset" 드롭다운과 ⇄ 교체 버튼이 있습니다. 대표 해상도를 원클릭으로 입력할 수 있습니다.

- **SD 1.5** — SD1.5 계열 모델용 5종 (512 기준)
- **SDXL Trained** — SDXL 공식 학습 버킷 9종 (품질 최우선)
- **SDXL Cheat Sheet** — 영화·사진 비율을 8의 배수로 근사한 12종 (구도 우선, 출처 [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

`Custom` 선택 시 기존 W/H 값을 유지합니다. 프리셋 적용 후 W/H를 수동 편집하면 자동으로 `Custom`으로 돌아갑니다. ⇄ 버튼으로 Width와 Height를 교체할 수 있습니다.

Cheat Sheet 해상도는 공식 버킷에서 벗어나므로 일부 모델에서 구도가 약간 흐트러질 수 있습니다.

> ComfyUI Bridge에서는 Simple 모드에만 적용됩니다. Raw JSON Workflow 모드의 노드 값에는 영향이 없습니다.

## Bridge 간 전송

Bridge 간에 프롬프트를 직접 전송할 수 있습니다. SD ↔ NAI 간에는 구문이 자동 변환됩니다.

## Bridge로 보내기

이미지 상세 모달 툴바에서 현재 표시 중인 이미지의 프롬프트 또는 이미지 자체를 생성 Bridge에 직접 보낼 수 있습니다.

- **프롬프트 보내기 ▾** — 표시 이미지의 프롬프트를 NAI Bridge / SD WebUI / ComfyUI 중 하나에 전송합니다. NAI 구문으로 작성된 프롬프트는 대상이 SD/ComfyUI인 경우 SD 구문으로 자동 변환되며, 반대도 마찬가지입니다. NAI v4의 캐릭터 프롬프트(positive/negative)는 대상이 NAI Bridge인 경우 구조화된 상태로, 그 외 대상은 메인 프롬프트에 병합되어 전송됩니다.
- **이미지 보내기 (img2img) ▾** — 표시 이미지의 풀 해상도를 NAI Bridge / SD WebUI / ComfyUI의 img2img 슬롯에 직접 설정합니다. ComfyUI는 v4.121.0부터 지원됩니다.
- **리믹스 ▾**(v4.121.3〜) — 프롬프트와 이미지를 **함께** 전송합니다. 같은 이미지에 대해 프롬프트를 살짝 수정하여 재생성하고 싶을 때 한 번의 클릭으로 완결됩니다. 대상: NAI / SD WebUI / ComfyUI.

버튼 표시 조건:
- 프롬프트 전송: 이미지에 프롬프트 메타데이터(positive/negative 또는 캐릭터 정보)가 포함된 경우
- 이미지 전송: 현재 표시 중인 미디어가 이미지(정지 이미지 / 애니메이션 이미지 / 동영상)인 경우. 동영상은 현재 재생 위치의 프레임을 캡처하여 전송합니다(v4.121.20〜)
- 리믹스: 위 두 조건이 모두 충족될 때만

주의 사항:
- PDF·오디오에서는 「이미지 보내기」가 표시되지 않습니다
- 동영상 프레임 전송 시 원본 동영상이 아닌, 현재 재생 위치의 1 프레임 PNG가 전송됩니다
- 프롬프트 변환이 실패한 경우 원본 구문으로 전송되며, 대상 Bridge 화면에 경고 토스트가 표시됩니다
- 전송되는 것은 프롬프트/이미지만입니다. 샘플러·스텝 수·CFG·Seed 등의 파라미터는 대상에서 복원되지 않습니다 (Bridge 측의 기본값 또는 이전 값이 사용됩니다)
