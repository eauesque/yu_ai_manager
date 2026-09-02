# Pi 5의 `numa=fake=8` 환경에서의 CMA 제약

Hailo-10H 워크로드 실행 시 Raspberry Pi 5(8 GB)에서의 CMA 할당에 관한 실용적인 지식을 정리합니다.
`cma=`의 상한값, 512M를 초과하는 값이 조용히 실패하는 이유, 그리고 디스플레이 드라이버가 소비한 CMA를 회수하는 방법을 기술합니다.

**대상 독자**: Raspberry Pi 5에서 Hailo GenAI 모델(LLM, Speech2Text)을 실행하는 개발자
(AI HAT / AI HAT+ 사용).

---

## ⚠️ 2026-05 firmware 회귀 주의

**2026-05-13 릴리스 `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11` 이후**, `/boot/firmware/cmdline.txt`에 `cma=`를 기입하면 크기와 무관하게 VC firmware mailbox가 완전히 침묵합니다(`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, cpufreq sysfs 누락).

**2026-05-16 이후의 확정 권장 방법**: cmdline `cma=`가 아니라 `/boot/firmware/config.txt`에 `dtoverlay=cma,cma-512`를 기입하는 것입니다. DT의 `linux,cma` reserved memory node를 경유해 확보되므로 새 firmware와 충돌하지 않습니다. 자세한 내용은 §6과 [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md)를 참조하십시오.

아래의 옛 기술(cmdline `cma=512M` 권장)은 2026-04-15 시점의 검증 결과입니다. NUMA 노드 경계에 따른 상한값(512M)에 관한 지식은 여전히 유효하지만, **설정 위치는 cmdline이 아니라 config.txt의 overlay 인자로 이전되었습니다**.

---

## TL;DR

- **설정 위치는 `config.txt`의 `dtoverlay=cma,cma-512`**(2026-05-16 확정. cmdline `cma=`는 새 firmware에서 mailbox를 망가뜨립니다)
- `cma-1024` 및 `cma-768`은 Pi 5(8 GB)에서 **조용히 실패**합니다 — `CmaTotal`이 0이 되며, 커널 패닉이나 경고도 없습니다(NUMA 노드 경계에 의한 상한. overlay 경유에서도 동일한 제약이 남아 있을 것으로 추정)
- **`cma-512`가 확인된 상한값이며 권장값**입니다(overlay 경유로 2026-05-16에 Pi 5 8 GB에서 재검증, `CmaTotal: 524288 kB` 확보 확인)
- 근본 원인: 기본 Pi 5 커널이 `numa=fake=8`을 적용하여, 연속 할당을 1개의 NUMA 노드(1 GB)로 제한
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2`는 부팅 시 ~157 MB의 CMA를 소비**합니다 — DRM 드라이버 초기화가 실패한 경우에도 마찬가지입니다(2026-04-15에 검증)
- **`camera_auto_detect=1`**은 `pisp_be`와 `videobuf2_dma_contig`를 로드하며, 추가로 CMA를 소비합니다. 헤드리스 시스템에서는 비활성화를 권장
- **헤드리스 최적화 베이스라인**(두 오버레이 모두 비활성화): 부팅 시 ~98 MB의 CMA 사용, Hailo 모델용으로 ~414 MB 여유
- **YOLO InferModel은 0 MB의 CMA를 사용**합니다(2026-04-15에 확인) — GenAI 모델(LLM, Speech2Text)만 CMA에서 할당
- LLM(qwen2.5-1.5b) + Whisper-base 동시 로드: 합계 ~328 MB — 헤드리스 최적화 베이스라인 안에 수용
- CMA는 서버 재시작으로는 회수되지 않습니다 — 풀 시스템 재부팅(PCIe 전원 재투입)으로만 해제됩니다(`hailo1x_pci` 드라이버 버그, Hailo에 보고 완료)
- VDevice를 **프로세스 라이프타임 싱글턴**으로 취급하십시오. 축출/리로드 금지

---

## 1. 증상

`/boot/firmware/cmdline.txt`에서 `cma=1G`(또는 `cma=768M`)을 설정하고 재부팅하면 다음과 같이 됩니다:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

시스템은 정상적으로 부팅됩니다. 커널 패닉도 오류 메시지도 없습니다. `cmdline.txt`의 CMA 설정은 **조용히 무시**되며, CMA에 의존하는 것들(Hailo-10H NPU, V4L2 카메라 등)의 초기화가 실패합니다.

**`cmdline.txt`를 변경한 후에는 항상 CMA 할당을 검증하십시오:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. 근본 원인: `numa=fake=8` 노드 경계

Pi 5용 기본 Raspberry Pi OS 커널은 `numa=fake=8`을 적용하여, 물리 메모리 8 GB를 **각 1 GB씩의 가상 NUMA 노드 8개**로 분할합니다:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux CMA(`cma_init_reserved_mem`)는 부팅 시 **NUMA 노드 경계를 넘지 않는 연속 물리 메모리**로 할당되어야 합니다.
이로 인해 노드 1개 = 1 GB라는 엄격한 상한이 부과됩니다. 커널 자체가 같은 노드의 메모리를 점유하기 때문에, 정확히 1 GB를 예약하는 것은 불가능합니다:

> **아래 표는 2026-04-15 시점의 cmdline 방식에서의 측정 기록입니다.**
> NUMA 노드 경계에서 비롯된 상한값(512M)에 관한 지식은 지금도 유효하지만, **cmdline `cma=`는 현재 사용해서는 안 됩니다**(서두의 firmware 회귀 참조).
> 현재의 설정 방법은 `config.txt`의 `dtoverlay=cma,cma-512`(§6)입니다.

| `cmdline.txt` 설정(2026-04-15 당시 기록) | 결과 |
|---|---|
| `cma=1G` | 노드 전체를 소비하려 함. 커널을 위한 여유가 없음 → **조용한 실패**, CmaTotal=0 |
| `cma=768M` | 신뢰할 수 있는 연속 범위를 초과 → **조용한 실패**, CmaTotal=0(2026-04-15에 검증) |
| `cma=512M` | 1개 노드의 절반 → **확인된 안정 상태** ✓(2026-04-15에 검증) ← 당시의 권장. **현재는 `dtoverlay=cma,cma-512`를 사용할 것** |
| `cma=384M` | 미검증(512M가 확인되었으므로 384M는 불필요) |
| `cma=256M` | 안정적이지만, LLM + Whisper 동시 사용 시 빠듯함 |
| `cma=128M` | 안정적이지만, Hailo GenAI에는 부족(LLM만으로도 ~234 MB 필요) |

### 실패가 조용한 이유

`cma_init_reserved_mem`은 할당 실패 시 패닉을 일으키지 않습니다. 커널은 `CmaTotal=0`인 상태로 부팅되며, 마치 CMA가 요청되지 않은 것처럼 동작합니다.
`cmdline.txt`에 기입된 값은 사실상 무시됩니다.

---

## 3. Hailo-10H CMA 요구사항

Raspberry Pi 5, AI HAT+, HailoRT 5.3.0에서 측정:

| 모델 / 조합 | CMA 사용량 | 주석 |
|---|---|---|
| LLM — qwen2.5-1.5b-chat(단독) | **~234 MB** | 2026-04-15에 측정 |
| YOLO InferModel(yolov8n, configure + bindings) | **0 MB** | 2026-04-15에 확인 |
| Whisper-tiny(단독) | ~70 MB | 추정 |
| Whisper-base(단독) | ~100 MB | 추정 |
| Whisper-small(단독) | ~150 MB | 추정 |
| **LLM + Whisper-tiny(동시)** | **~246 MB** | CMA 256 MB로 측정 |
| **LLM + Whisper-base(동시)** | **~334 MB** | 추정. 헤드리스 베이스라인 안에 수용될 것으로 예상 |

**YOLO는 0 MB의 CMA를 사용**합니다: HailoRT 5.3.0에서 YOLO InferModel, `configure()`, `create_bindings()`는 CMA를 전혀 할당하지 않습니다.
입출력 DMA 버퍼는 CMA가 아니라 `set_buffer()`를 통해 사전 할당된 numpy 배열로부터 매핑됩니다.
따라서 YOLO는 CMA 예산 계산에서 요인이 되지 않습니다.

CMA 512 MB와 헤드리스 최적화(§5 참조)를 적용한 경우, 다음 구성이 동작할 것으로 예상됩니다:

- LLM만(~234 MB, ~180 MB의 여유)
- Whisper-tiny / Whisper-base만(쉽게 수용됨)
- LLM + Whisper-base 동시(합계 ~334 MB, ~80 MB의 여유)

Whisper-small과 LLM의 조합(추정 ~384 MB)은 이론상의 한계에 가까워집니다 — 신뢰하기 전에 실제 측정으로 확인하십시오.

자세한 내용은 [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md)의 동시 로드 테스트 결과를 참조하십시오.

---

## 4. CMA는 풀 리부트까지 회수되지 않는다

HailoRT로 할당된 CMA는 풀 시스템 재부팅 전까지 메모리에 남아 있습니다.
`VDevice.release()`, 서버 프로세스의 종료, 커널 모듈의 리로드와 무관하게 마찬가지입니다.

**근본 원인**(2026-04-15에 확인): `hailo1x_pci`는 디바이스 fd를 닫거나 모듈을 리로드한 후에도 DMA coherent 할당을 유지합니다.
풀 리부트(PCIe 전원 재투입)만이 이를 해제합니다. 버그는 Hailo에 보고 완료되었습니다.

| 단계 | CmaFree(CMA 512 MB, 헤드리스 최적화) |
|---|---|
| 부팅 | **~426 MB** |
| LLM 로드 후(~234 MB) | ~192 MB |
| Whisper-base 로드 후(~100 MB) | ~92 MB |
| `VDevice.release()` 후 | ~92 MB(**반환되지 않음**) |
| 서버 프로세스 종료 후 | ~92 MB(**반환되지 않음**) |
| `rmmod hailo1x_pci && modprobe hailo1x_pci` 후 | ~92 MB(**반환되지 않음**) |
| 풀 시스템 재부팅 후 | **~426 MB(복원)** |

**의미**: CMA 소비는 같은 부팅 세션 내에서 서버 재시작을 넘어 누적됩니다.
서버 재시작으로 CMA가 회수될 것을 기대하지 마십시오. VDevice를 **프로세스 라이프타임 싱글턴**으로 설계하십시오.
CMA가 고갈된 경우, 풀 시스템 재부팅으로만 복원됩니다.

---

## 5. 헤드리스 최적화: `/boot/firmware/config.txt`

기본 Pi OS `config.txt`에는 헤드리스(디스플레이 없음) 시스템에서조차 대량의 CMA를 소비하는 두 가지 설정이 포함되어 있습니다.

### 5.1 `dtoverlay=vc4-kms-v3d` 및 `max_framebuffers=2`

**효과**: Pi 5 firmware는 부팅 시 디스플레이 파이프라인용 CMA 프레임버퍼를 사전 할당합니다.
`max_framebuffers=2`에서는 이것이 **사용자 공간 프로세스가 실행되기 전에** ~157 MB의 CMA를 소비합니다.

이 할당은 Linux DRM 드라이버가 나중에 초기화에 실패한 경우에도(예: `[drm] Couldn't stop firmware display driver: -22` 또는 `dmesg`의 `Couldn't get core clock`) 지속됩니다.

| `config.txt` 상태 | 부팅 시 CmaFree |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` 활성화(기본값) | **~257 MB** |
| 둘 다 주석 처리 | **~305 MB**(+~48 MB) |

**수정**(헤드리스 / 서버 모드):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**트레이드오프**: 하드웨어 가속 디스플레이와 3D(V3D)에는 `vc4-kms-v3d`가 필요합니다.
시스템에 SSH나 웹 인터페이스로만 접근한다면 비활성화해도 안전합니다.

### 5.2 `camera_auto_detect=1` 및 `display_auto_detect=1`

**효과**: 이 오버레이들은 부팅 시 CSI 카메라와 DSI 디스플레이를 프로브하여, `pisp_be`(Pi ISP 백엔드)와 `videobuf2_dma_contig`를 로드합니다.
로드되는 모듈과 감지된 하드웨어는 각각 추가 CMA를 사전 할당합니다.

| `config.txt` 상태 | 부팅 시 CmaFree |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB(vc4 비활성화 후) |
| 둘 다 0으로 설정 | **~426 MB**(+~121 MB) |

**수정**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**주석**: `camera_auto_detect=0`은 CSI 카메라에만 영향을 줍니다. USB 카메라(UVC / `uvcvideo`)는 영향을 받지 않으며 정상적으로 계속 동작합니다.

### 5.3 헤드리스 AI HAT+ 용도를 위한 권장 최소 `config.txt`

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

이 설정에서의 부팅 시 CMA 추정값: **~98 MB 사용**, Hailo 모델용으로 ~414 MB 여유.

### 5.4 CMA 예산 요약(CMA 512 MB, 헤드리스 최적화)

| 구성 | CmaFree | Hailo용으로 사용 가능 |
|---|---|---|
| 기본값(vc4-kms-v3d + 카메라 활성화) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers 비활성화 | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| LLM 로드 후(~234 MB) | ~192 MB | Whisper용 |
| LLM + Whisper-base 로드 후(~100 MB) | ~92 MB | (여유) |

---

## 6. 권장 구성

### `dtoverlay=cma,cma-512`를 설정(2026-05-16 확정)

```bash
# 현재 CMA 상태를 확인
grep CmaTotal /proc/meminfo

# 1) cmdline.txt에서 기존 cma=를 삭제(새 firmware에서 mailbox를 망가뜨리기 때문)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) config.txt의 [all] 섹션에 dtoverlay=cma,cma-512를 추가
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) 콜드 재부팅 권장(전원 플러그 뽑았다 꽂기)
sudo sync && sudo poweroff

# 재부팅 후 검증(4개 항목 모두 확인할 것)
vcgencmd version                                # Broadcom 응답 필수(침묵이면 실패)
grep CmaTotal /proc/meminfo                     # 524288 kB 기대
journalctl -b -k | grep 'linux,cma'             # initialized node linux,cma가 나와야 함
journalctl -b -k | grep '0x00030087'            # 나오지 않아야 함
```

dmesg에 `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`이 나오면 DT 경로로 확보되었다는 증거입니다.
반대로 `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`가 나온다면 cmdline에 `cma=`가 남아 있는 것이므로 삭제하십시오.

### `vc4-kms-v3d`를 활성화하는 경우

디스플레이 KMS DRM이 필요하다면 overlay 인자 형태로 통합할 수 있습니다:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
다만 vc4-kms-v3d는 §5.1에서 설명한 대로 ~157 MB의 CMA를 소비하므로, Hailo GenAI 용도에서는 비활성화를 권장합니다.

### 커널 / firmware / 설정 변경 후에는 매번 검증

`/boot/firmware/cmdline.txt`나 `config.txt`에 대한 변경, 커널/firmware 업그레이드 후에는 CMA 상태와 mailbox 응답이 조용히 바뀔 수 있습니다.
위의 4개 항목 검증을 재부팅 후의 루틴으로 삼으십시오.

---

## 7. 다른 `numa=fake=8` 문제와의 상호작용

`numa=fake=8`은 이 프로젝트와 관련된 최소 2가지의 서로 다른 문제를 일으킵니다:

| 문제 | 증상 | 근본 원인 |
|---|---|---|
| CMA 조용한 실패 | `cma=1G`, `cma=768M` 이후 `CmaTotal=0` | NUMA 노드 경계가 연속 할당을 제한 |
| Node.js 설치 실패 | npm/node 인스톨러가 메모리 오류로 중단 | NUMA 노드당 메모리(1 GB)가 총 RAM으로 오검출됨. [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)로 업스트림에 보고 |
| `vc4-kms-v3d` CMA 드레인 | 부팅 시 ~157 MB 소비. DRM init이 실패해도 반환되지 않음 | `max_framebuffers=2`가 firmware에게 CMA 프레임버퍼를 예약시킴. Linux 드라이버 기동 전 |

조용한 실패와 vc4 드레인 모두, 동일한 근본적 제약(하위 4 GB의 DMA 존, NUMA 노드 경계)에서 비롯됩니다.
예기치 않은 메모리 관련 장애가 발생한 경우, 먼저 `/proc/meminfo`와 `config.txt`를 확인하십시오.

---

## 8. 빠른 진단 체크리스트

```bash
# 1. mailbox 응답(새 firmware에서 최우선 확인)
vcgencmd version                     # 침묵이면 cmdline에 cma=가 남아 있을 가능성

# 2. CMA 할당을 확인
grep CmaTotal /proc/meminfo          # 0 kB = 조용한 실패

# 3. DT 경로 vs cmdline 경로 확인
journalctl -b -k | grep 'linux,cma'
# 기대: "initialized node linux,cma, compatible id shared-dma-pool" (DT 경로 = 정상)
# 이상: "bypass linux,cma node, using cmdline CMA params instead" (cmdline 잔존)

# 4. NUMA 토폴로지를 확인
numactl --hardware                   # 노드 수와 노드당 메모리를 표시

# 5. 현재 커맨드라인과 overlay 설정을 확인
cat /boot/firmware/cmdline.txt       # cma=가 포함되어 있지 않은지 확인
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512가 존재

# 6. Hailo 디바이스 가용성을 확인
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # NPU에 접근 가능한지 확인

# 7. CMA 소비자에 대해 config.txt를 확인
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. 로드된 커널 모듈(CMA 사용자)을 확인
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**검증 환경**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**2026-05-16 재검증**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT에서 `dtoverlay=cma,cma-512` 경유로 524288 kB 확보, mailbox 응답 확인)
