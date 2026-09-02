# HailoRT 5.3.0의 CMA 메모리 누수 — 확정 진단 및 운용상의 제약

> **정정 안내**: 본서는 구 측정에 기반한 CMA leak 진단 기록이며, `release()` 후에도 CMA가 회수되지 않는다, 추론 중에 약 14 MB/분으로 지속적으로 누수된다, Pi 본체 재부팅만이 확실한 회복 수단이라는 구 결론은 철회되었다. HailoRT/driver 5.4.0의 재시험에 의한 최종 판정은 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8에서 정정 완료. 본서의 구 결론을 현행 실용 판정으로 참조하지 말 것.

**작성일**: 2026-05-17 (v4.214.11에서 발견 및 기록)
**영향 범위**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (`hailo_platform.genai` 경로 이용)
**증상**: LLM을 한 번 로드하면 `VDevice.release()` / `LLM.release()`를 호출해도 CMA가 거의 회수되지 않는다. 또한 추론 중에도 CMA가 지속적으로 누수된다. Pi 본체를 재부팅하는 것 외에는 복구 수단이 없다.
**상태**: 드라이버 측의 구조적 제약으로 확인됨. 회피책 검토 중.

---

## 1. 확정 진단의 근거

`v4.214.10`에서 도입한 CMA 이벤트 로거(`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)를 사용하여 2026-05-17에 다음 시퀀스를 실측했다.

### 1-1. 관측 로그 (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6분간 채팅 이용 (약 5〜10개 메시지 정도의 추론)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. 해석

| 페이즈 | CmaFree 차이 | 의미 |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | VDevice 생성 자체는 CMA를 거의 소비하지 않음 |
| `acquire_pre` → `acquire_post` (Qwen3-1.7B-Instruct 로드) | **−285 MB** | LLM 1개에 285 MB 소비 |
| `acquire_post` → `release_pre` (6분간 추론) | **−84 MB / 6 min ≒ −14 MB/min** | **추론 중에도 지속적으로 누수** |
| `release_pre` → `release_post` (LLM 언로드) | **+1 MB** | **`release()`로 사실상 CMA가 반환되지 않음** |

### 1-3. 기존 가설과의 비교

이것은 2026-05-16에 작성한 `SQLCIPHER_MMAP_CORRUPTION.md` §7 및 구 문서의 초기 가설 「VDevice 유지 전략 (우리의 `_maybe_reset_vdevice`가 비어있음)이 누수를 증폭시키고 있다」를 일부 반증하는 관측 결과다. VDevice 생성 0 MB / release 0 MB이므로, **유지 전략을 변경해도 (= `_maybe_reset_vdevice`를 매번 리셋하도록 변경해도) 효과가 없다**.

---

## 2. 구조적 제약

실측 결과로부터, HailoRT 5.3.0 (community build, `hailo_platform.genai` API)에는 다음 3가지 문제가 공존한다:

1. **`VDevice.release()` / GenAI 모델의 `release()`가 호스트 CMA를 회수하지 않음** (실측 확인)
   - 단일 프로세스 내에서는 PCIe 드라이버 (`hailo1x_pci`)가 DMA 영역을 계속 보유하며, `munmap`에 상당하는 동작이 발생하지 않음
2. **추론 중 지속적인 CMA 누수 (약 14 MB/분)** (실측 확인)
   - 오늘 관측에서는 Qwen3-1.7B-Instruct 이용 중 6분에 84 MB를 잃었음
   - 로드/언로드와는 독립된 별도 경로. 언로드하지 않아도 고갈됨
3. **Pi 본체 재부팅 외에 CMA를 확실히 회수하는 방법이 확인되지 않음** (실측 + 커뮤니티 보고)
   - `systemctl restart yu-ai-manager`에 상당하는 서버 프로세스 재시작으로도, `hailo1x_pci`가 PCIe 전원 사이클까지 DMA를 보유하므로 불완전함. 완전 복구에는 Pi 본체의 `sudo reboot`가 필요 (이 저장소에서의 실측)
   - Hailo 커뮤니티에서도 복수의 독립 보고가 있음: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> 및 <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (`VDevice.release()` / 프로세스 종료 / 드라이버 재로드로는 복구되지 않고 호스트 재부팅만 복구 가능하다고 명기)
   - 이것은 `acquire_genai`의 사전 거부 오류 메시지에도 사용자용으로 기재되어 있음 (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. 「자식 프로세스 kill로 CMA가 반환되는가」: **실측으로 반증** (2026-05-17 Phase 0 PoC)

구 버전 (rev1)에서는 「Linux 커널이 `mm_struct` teardown 시에 DMA 페이지를 회수하므로, 자식 프로세스 kill로 CMA가 완전히 회수된다」고 이론적으로 단정했지만, Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`)로 **실측한 결과, 자식 프로세스 kill로는 CMA가 거의 회수되지 않음을 2회 독립적으로 확인**했다.

**측정 결과 (2회째, 엄밀 버전)**:

| 측정점 | CmaFree | Δ |
|---|---:|---:|
| 베이스라인 (PoC 시작 전) | 503 MB | — |
| VDevice 생성 후 | 372 MB | **-131 MB** (콜드 스폰 자식 프로세스에서는 VDevice 구축 시 소비) |
| LLM 로드 후 | 372 MB | 0 MB (LLM은 VDevice DMA pool 내에서 완결, 신규 소비 없음) |
| SIGTERM 전송 + join 후 | 378 MB | +6 MB |
| **30초 대기 후** | **380 MB** | **누계 +8 MB만 회수** |

기댓값 ≥250 MB 회수에 대해 실측값은 고작 +8 MB (1회째 우발 측정에서는 +1 MB). 이것은 시스템 지터 수준으로, **유의미한 CMA 회수가 발생하지 않았다**.

**확정 진단**:

- `hailo1x_pci` 드라이버는 DMA pool을 사용자 프로세스의 `mm_struct`가 아닌 **드라이버 내부 글로벌 상태**로 관리하고 있음 (추정)
- `process exit`, `kill`, `module unload`로도 회수되지 않음 (커뮤니티 보고와 일치)
- **유일하게 확인된 회수 수단은 Pi 본체의 `sudo reboot` (= PCIe 전원 사이클)** ← §2 3번째 행에 기재된 실측 사실이 정확함

상세 보고서: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

이 결과로 인해 `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`는 **REJECTED**로 표시되고, 서브프로세스 격리에 의한 완화 노선은 폐지됨. 대안으로 §4 (D)의 자동 재부팅 노선이 채택됨.

---

## 3. 운용상의 함의

### 3-1. 「1 모델 / Pi 재부팅」이 사실상의 상한

- Pi 5 (CMA 512 MB 상한, Pi 사양상 늘릴 수 없음) + Qwen3 계열 LLM (285 MB) 조합에서는:
    - 재부팅 직후 CmaFree ≒ 480 MB
    - LLM 1개 로드 → CmaFree ≒ 190 MB
    - 수십 분의 추론 → CmaFree ≒ 50 MB 이하
    - **2번째 모델 로드는 영구적으로 불가능** (250+ MB 필요인데 잔량 부족, release해도 반환되지 않음)

### 3-2. LLM + VLM / LLM + S2T의 동시 사용 불가

- VLM (llava 계열, ~300 MB), S2T (whisper-small, ~175 MB)를 LLM과 교체하며 사용하는 유스케이스는, 위 제약으로 인해 **로드 → 재부팅 → 로드**의 절차를 밟지 않는 한 실현 불가능.
- 「대화 중에 이미지를 첨부하여 다른 모델로 전환」「대화의 음성을 텍스트로 변환」 등의 **멀티 모델 UX는 HailoRT 5.3.0에서는 설계상 성립하지 않는다**.

### 3-3. 장시간 연속 추론이 어려움

- 14 MB/분의 누수는 CmaFree가 200 MB 시점에서도 14분에 절반, 30분에 거의 고갈.
- 30분 이상의 채팅 세션은 Pi 재부팅을 끼워넣지 않으면 안정되지 않음.

---

## 4. 취할 수 있는 대책

우선순위・공수 포함하여 열거:

| 안 | 효과 | 공수 | 부작용・리스크 |
|---|---|---|---|
| ~~(A) Hailo 조작을 서브프로세스에 격리, 정기적으로 kill하여 커널에 CMA 반환~~ | ❌ **REJECTED** (Phase 0 PoC로 반증, 2회 재현). kill 후 회수량은 누계 +8 MB에 불과하여 가설 불성립 | — | 채용하지 않음 |
| **(B) `_CMA_ESTIMATES_MB`를 실측값 + 마진으로 업데이트** | 사전 거부의 정밀도 향상 (false-positive 로드 시도를 줄임) | ✅ 즉시 적용 가능, 1줄 | 250 MB 가정으로 겨우 동작하던 기존 사용자가 거부되지만, 그것은 원래 실패하고 있었던 것 |
| **(C) `CmaFree < 80 MB`에서 UI 배너 / `< 30 MB`에서 error.log에 WARN** | 이용자가 상황을 파악할 수 있음, Pi 재부팅 촉구 가능 | 중 | 경고 피로 / 과도한 알림 리스크 |
| **(D) `CmaFree < 30 MB` 감지 시 supervisor에 SIGTERM** | 자동 복구 (다만 Pi 전체 재부팅이 필요하므로 `systemctl reboot` 경유) | 중 | supervisor 권한 부여 필요 / 다른 작업 중 세션 종료 |
| **(E) HailoRT 수정 대기 + 제약의 문서화** | 비용 0 | 0 | Hailo의 릴리스 사이클에 의존 (수개월〜) |
| **(F) Hailo의 이슈 트래커 / 포럼에 수정 요청 제출** | 수정 타이밍이 앞당겨질 가능성 | 소 | 반응 속도는 지원 계약과 커뮤니티 상황에 의존 |

단기 방침 (v4.214.11에서 실시): **(B) 적용 + 본 문서 (E와 F의 출발점)**.
중기 방침 (별도 spec): **(C) UI 경고 → (A) 서브프로세스 격리** 순으로 검토.
장기: HailoRT 릴리스를 모니터링하여, 수정되면 본 문서를 업데이트하고 제약을 해제.

---

## 5. 관련 문서 / 코드

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — 사전 CmaFree 확인 + 사용자용 오류 메시지에 본 제약을 명시
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — 모델별 CMA 필요량 추정 (v4.214.11에서 qwen을 250 → 300으로 상향)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — v4.214.10에서 도입한 측정 계장. 본 문서의 실측 데이터도 여기서
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — 「VDevice를 프로세스 라이프타임 동안 보유」하는 설계 (빈 함수). 본 실측 결과로, 이것을 리셋하도록 변경해도 CMA 회수에 기여하지 않음이 확정
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Phase 0.5 관측 페이즈의 오퍼레이터 가이드. `mode=lazy` + `dry_run=true`로 `would_fire` 로그만 수집하는 절차
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Pi5 전체의 CMA 상한 및 각 드라이버 (camera / KMS / Hailo / HEVC)의 베이스라인 소비량
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — HailoRT 5.3.0으로 마이그레이션한 경위와 기지 차이점

---

## 6. 재현 절차 (Hailo 이슈 보고용)

외부에 버그 보고하는 경우의 최소 재현 절차:

```bash
# 1. Pi 재부팅 직후의 베이스라인 확인
grep CmaFree /proc/meminfo
# CmaFree: 480000 kB 전후

# 2. 서버 기동 + 1번째 LLM 로드 (예: /tools의 GenAI에서 1통 전송)
# /api/llm/generate 또는 /api/chat/send에 1 요청

# 3. CmaFree 확인
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. 모델 언로드
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. CmaFree 확인
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (반환되지 않음 ← bug)

# 6. 동일 모델 / 다른 모델의 재로드 시도 → 불충분한 CMA로 거부
```

기대되는 동작: 절차 5에서 CmaFree가 절차 1의 베이스라인에 가까운 값 (>400 MB)으로 돌아올 것.
실제 동작: +1 MB 정도밖에 반환되지 않아 재로드 불가.
