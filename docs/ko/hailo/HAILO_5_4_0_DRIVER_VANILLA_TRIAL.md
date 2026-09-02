# HailoRT / driver 5.4.0 CMA 미회수 판정의 정정과 검증 기록

작성: 2026-08-16 / 최종 수정: 2026-08-17 / 대응 버전: yu_ai_manager 4.623.1

CMA를 회수하지 않는다고 판정했던 사안(`docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` 참조)에 대해, `hailo-ai/hailort-drivers` v5.4.0(2026-08-16 공개, GPL-2.0, 소스 공개)에서 가설 검증과 공식 vanilla / `FOLL_LONGTERM` 수정판의 A/B 시험을 실시하여 측정 측의 오판정을 정정한 기록.

---

## 1. 결론

**2026-08-17 최종 추가 시험(4차): 3차까지의 `VERDICT: FAIL`은 최초 HEF 로드 후 `CmaFree` 절대 회복량만을 리크 판정에 사용한 데서 비롯된 오판정이었다. 공식 vanilla 5.4.0과 `FOLL_LONGTERM` 수정판을 A/B 비교한 결과, 낮은 `CmaFree`에서의 연속 로드, 동일 프로세스 내 해제·재로드, 20회 생성, 그리고 더 낮은 `CmaFree` 상태에서의 전체 시험 반복이 모두 성공했다. 생성 중 RSS와 `CmaFree`에 단조 증감은 없었고, CMA 할당 실패도 0건이었다. 최초의 `CmaFree` 저하는 multi-GB HEF의 페이지 캐시 증가와 대응하며, `MemAvailable`은 약 7GB를 유지했다. 이번에 시험한 Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, 단일 모델·단일 디바이스·단시간 반복 조건에서는 실용상의 CMA 리크는 재현되지 않았으며, `FOLL_LONGTERM` 수정에도 측정 가능한 개선은 없다. 장시간 연속 가동, 복수 모델 동시 사용, Hailo-8, IOMMU 하에서는 미시험이며, 이 결론의 적용 범위 밖이다.**

### 1.1 판정의 변천

| 회 | 날짜 | 그 시점의 판정 | 갱신·정정의 근거 |
|---|---|---|---|
| 1차 | 2026-08-16 | 판정 불능 | driver만 5.4.0으로 올리자 library 5.3.0과의 완전 일치 검사에서 API가 거부됨(§3) |
| 2차 | 2026-08-17 | 제한적인 시험만 완료 | driver / library / firmware를 5.4.0으로 맞췄고 `run2` 반복은 플래토에 도달했으나, pyhailort 경유의 직접 repro는 미실시(§4) |
| 3차 | 2026-08-17 | 잠정 `FAIL`(후에 오판정으로 판명) | 최초 HEF 로드 후 `CmaFree` 절대 회복량만을 판정한 구 진단 결과. 단발 측정으로는 메모리 손실과 페이지 캐시 이용을 구별할 수 없었음(§5, §7) |
| 4차 | 2026-08-17 | 실용상의 리크는 재현되지 않음 | vanilla / `FOLL_LONGTERM` A/B, 낮은 CMA 반복, 동일 프로세스 재로드, 20회 생성, RSS·`MemAvailable`·할당 실패를 측정하여 3차를 정정함(§8) |

---

## 2. v5.3.0 → v5.4.0 소스 차이(`hailo-ai/hailort-drivers`)

GitHub API로 두 태그 간의 전체 파일을 diff. 단일 스쿼시 커밋이었기 때문에 커밋 메시지에서는 아무것도 읽어낼 수 없었고, 실제 파일 diff로 확인했다. CMA 확보·해제의 **로직 자체**(`dma_alloc_coherent`/`dma_free_coherent` 페어)에는 변경이 없으며, 이하는 리팩터·방어적 수정이 중심이다:

| 파일 | 변경 내용 |
|---|---|
| `linux/utils/compact.h` → `compat.h` | 커널 호환 레이어 파일명 리네임 |
| `linux/vdma/memory.c` | `hailo_desc_list_release()`에 NULL 체크 추가, 해제 후 포인터를 NULL로 클리어(**이중 해제 방지**를 위한 방어적 수정) |
| `linux/vdma/vdma.h` | `hailo_descriptors_list_buffer`에서 중복 필드 `kernel_address` 제거(`desc_list.descs`로 통합) |
| `common/vdma_common.c` | DMA 전송 완료 판정을 `hw_num_proc` 직접 계산 방식에서 `num_proc`/`num_avail` 비교 방식으로 재작성(전송 완료 추적 버그 수정 가능성) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync`(새 커널 API 이름으로의 추종) |
| `common/pcie_common.c` | FW 제어 프로토콜에서 md5 필드 제거, SCU 로그 손상 판정을 앞 4바이트만 체크하던 것에서 앞 5워드 전체 체크로 강화 |

에러 메시지 문구도 변경(긴 설명문 → `out of CMA memory.`로 축약)되었으나, 확보·해제의 제어 흐름은 동일하다. **이 diff만으로는 당시의 가설(모델 재로드 시 CMA 미회수)에 대응하는 변경은 확인되지 않는다**.

---

## 3. 실기에서의 교체 작업과 막힌 지점(2026-08-16, 1차 시행)

Raspberry Pi 5 + Hailo-10H, 가동 중인 `hailo1x_pci 5.3.0`(dkms 관리)을 대상으로 수동 빌드로 v5.4.0 교체를 시도.

### 3.1 `make install`은 `all`에 의존하지 않는다

`linux/pcie/Makefile`의 `install` 타겟은 `modules_install`만 수행하며, 빌드 산출물(`.ko`)이 존재하지 않는 상태에서도 경고 없이 완료된다(정확히는 `System.map` 누락 경고는 뜨지만, 빌드 미실시가 원인이라는 것은 알 수 없다).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**반드시 `make all && sudo make install` 순서로 실행할 것.**

### 3.2 Raspberry Pi 커널 헤더에 `System.map`이 동봉되어 있지 않다

`modules_install` 실행 시 다음 경고가 뜨며 `depmod`이 조용히 스킵된다:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

`/usr/src/linux-headers-<kernelver>/System.map`이 존재하지 않기 때문. `/boot/System.map-<kernelver>`는 존재하므로 복사하면 해결된다:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

이를 하지 않으면 `modprobe`가 새로 설치한 `.ko`를 해석하지 못해 `FATAL: Module hailo1x_pci not found`가 발생한다(`.ko` 파일 자체는 `/lib/modules/<kernelver>/kernel/drivers/misc/`에 존재하는데도 그렇다).

### 3.3 udev 규칙은 reload/trigger하지 않으면 즉시 반영되지 않는다

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

모듈 교체 직후는 `/dev/h1x-0`이 `crw-------`(root 전용)이 된다. 다음으로 해결한다:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 드라이버와 라이브러리의 버전 불일치는 치명적이다

커널 드라이버만 5.4.0으로 올린 상태에서 `hailortcli`를 실행하면:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

HailoRT 라이브러리는 커널 드라이버와의 **완전 일치**를 요구하며, 한쪽만 먼저 업그레이드하면 모든 API 호출이 즉시 거부된다. 드라이버 단독으로의 vanilla 검증은 불가능하며, `hailort`(SDK 본체)의 사용자 공간 패키지도 동시에 올려야 한다.

- `apt-cache policy hailort` → 후보 5.3.0(오늘 시점, 공식 apt에 5.4.0 미배포)
- `gh api repos/hailo-ai/hailort/releases` → `v5.4.0` 태그는 존재하지만 `assets`는 비어 있음(빌드된 deb 없음, 소스만)

즉 **HailoRT 본체를 deb로 넣거나, 소스에서 풀 빌드하지 않으면 5.4.0의 실지 검증은 불가능**하다. 풀 빌드는 C++ CMake + Python 바인딩의 대규모 빌드가 되며, `hailo-tappas`·`python3-hailort` 등의 의존 패키지도 끌어들일 위험이 있으므로, 1차에서는 일단 보류하고 공식 deb 배포를 기다리기로 했다.

---

## 4. 자체 빌드 절차 기록(2026-08-17, 2차 시행)

apt/공식 deb 배포를 기다리지 않고, GitHub 소스(driver: GPL-2.0, `hailort` 본체: MIT)에서 직접 빌드하여 시스템에 투입했을 때의 절차·막힌 지점.

### 4.1 빌드 환경

- `checkinstall`을 도입(`sudo apt-get install -y checkinstall`). 다만 커널 모듈의 `xz` 압축 단계와 `installwatch`(checkinstall의 LD_PRELOAD 기반 파일 추적 기구)가 충돌하여, `make install`을 checkinstall 경유로 실행하면 `xz: ... そのようなファイルやディレクトリはありません`로 매번 실패했다. **커널 모듈의 패키지화에는 checkinstall을 사용하지 말고, dkms(driver 본체의 경우) 또는 순수한 `make install`(사용자 공간 라이브러리의 경우)을 사용할 것**
- 빌드 전에 메모리를 확보: `headroom mcp serve`의 중복 프로세스 및 `rust-analyzer`를 일시 정지(합계 1GB 가까이 해제). Pi의 메모리는 7.9Gi, 빌드 중에도 available 3.8Gi 정도를 유지할 수 있었다

### 4.2 `hailort`(사용자 공간 라이브러리) 빌드

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # ディレクトリを作成してから
cmake .. -DCMAKE_BUILD_TYPE=Release   # 外部依存(protobuf/spdlog/eigen等)を FetchContent で自動取得、約4分
cmake --build . -j2   # -j2 に制限(メモリ逼迫回避)、約15分
sudo make install     # /usr/local/{include,lib,bin} に配置。apt 版(5.3.0, /usr 配下)と共存可能
```

기본 `option()` 값은 모두 중량급 컴포넌트(GStreamer·테스트·서버·Ollama 연동 등)가 OFF이므로, `libhailort.so`·`hailortcli`·`libhailopp`만 빌드되는, 비교적 경량 구성이었다.

**주의**: `make install`의 산출물은 `/usr/local` 아래에 들어가며, apt 판(`/usr` 아래, 5.3.0)을 덮어쓰지 않는다. 동작 확인 시에는 `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`처럼 명시적으로 경로를 지정해야 한다.

### 4.3 driver(커널 모듈) 교체와 firmware 갱신

driver 자체는 dkms 경유(부록 A의 복구 절차와 같은 요령으로 `-v 5.4.0`으로 교체)로 빌드·설치하고, `rmmod`/`modprobe`로 다시 읽었다. 이 시점에서 `hailortcli`는 `HAILO_DRIVER_OPERATION_FAILED(36)` / dmesg 상 `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`이 되었고, **디바이스 상의 펌웨어(SoC 측, pci_ep)도 별도로 5.4.0으로 올려야 한다**는 것이 판명되었다.

```bash
# 公式 S3 から firmware を取得(driver リポジトリ同梱のスクリプトを使用)
bash hailort-drivers/download_firmware_hailo10h.sh
# 既存 firmware をバックアップしてから新版に差し替え
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展開先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

여기서 모듈 재로드(`rmmod`/`modprobe`, `support_soft_reset=1` 지정 포함)를 시도했으나, dmesg는 일관되게 `SOC Firmware batch was already loaded`를 반환했다. 드라이버 소스를 확인한 결과, `load_soc_firmware()`(Hailo-10H의 SoC 펌웨어 로드 경로)에는 `support_soft_reset`에 의한 소프트 리셋 처리가 구현되어 있지 않았고(Hailo-8의 `load_nnc_firmware()`에만 구현), `hailo_pcie_is_firmware_loaded()`가 true를 반환하는 한 무조건 스킵되는 구현이었다. 즉 **SoC 상의 펌웨어 상태는 모듈 재로드로는 변경할 수 없으며, 실기의 전원 재투입이 필수**이다.

재부팅 후, dmesg는 firmware batch의 기록(`customer_certificate.bin`·`scu_fw.bin`·`u-boot-*.dtb.signed`·`u-boot-spl.bin`·`fitImage`·`image-fs` 순, 4064ms) → `SOC Firmware Batch loaded successfully`를 기록했고, `hailortcli fw-control identify`가 `Firmware Version: 5.4.0 (release,app)`으로 정상 응답했다.

### 4.4 간이 CMA 거동 확인과 한계

`hailortcli run2`(resnet_v1_18.hef, `hailo_tutorials` 패키지 동봉 소형 모델)로 단발 load/run/exit, 그리고 8회 연속 실행 시의 `CmaFree`(`/proc/meminfo`) 추이를 관찰했다.

| 실행 | CmaFree (kB) |
|---|---|
| baseline (재부팅 직후) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744(변화 없음, 플래토) |

몇 회 만에 플래토에 도달했고, 8회째까지 추가 leak은 관찰되지 않았다. 다만 이것은 CLI 경유의 단순한 load/run/exit(프로세스별 개별 기동)이며, `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`가 보고하는 2가지 기존 leak——(a) **동일 프로세스 내**에서의 `VDevice.release()`/모델 재로드 시 미회수, (b) `generate_stream()`(LLM 추론) 실행 중의 지속적 leak——의 어느 경로와도 다르며, 이 결과는 "해결되었다"는 증거가 되지 않는다.

본명의 repro(`tools/diag_hailo_cma_reclaim.py` 및 forum-followup doc 기재 스크립트)는 Python의 `hailo_platform`(pyhailort) 바인딩 경유로 GenAI LLM을 로드하는 방식이라, 그대로는 5.4.0 환경에서 동작시킬 수 없었다.

```
$ .venv 内の hailo_platform は libhailort.so.5.3.0 に固定リンク(ldd で確認)
$ VDevice() 構築時に driver(5.4.0)/library(5.3.0) のバージョン不一致で同じ HAILO_INVALID_DRIVER_VERSION に該当する見込み
```

이 시점에서는 pyhailort(Python 바인딩)를 5.4.0 소스에서 재빌드하여 `.venv`에 교체하는 작업은 미착수였으나, 3차 시행(§5)에서 실시했다.

---

## 5. pyhailort 재빌드와 repro 재실행(2026-08-17, 3차 시행)

본 절은 3차 시행 시점의 잠정 판정을 기록한다. 판정 방법과 결론은 4차 A/B 시험(§8)에서 정정되었다.

### 5.1 pyhailort(Python 바인딩)의 빌드

`hailort` 본체 저장소의 `hailort/libhailort/bindings/python/platform/`가 pyhailort의 pip 패키지 소스(`pyproject.toml`, scikit-build-core + pybind11 기반)이다. §4.2에서 `/usr/local`에 배치한 libhailort 5.4.0을 명시적으로 링크시켜 빌드했다.

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

build isolation 내에서 `scikit-build-core`/`pybind11`을 PyPI에서 자동으로 가져와 빌드하고, `.venv`의 `hailort`를 5.3.0 → 5.4.0 wheel로 교체했다. `ldd`로 `_pyhailort*.so`가 `/usr/local/lib/libhailort.so.5.4.0`에 링크되어 있음을 확인했고, `VDevice()`의 construct/release도 단독으로 정상 동작했다.

### 5.2 기존 repro(`tools/diag_hailo_cma_reclaim.py`)의 재실행

2026-05와 동일한 repro 스크립트·동일한 판정 기준·동일 HEF(`~/hailo_models/Qwen3-1.7B-Instruct.hef`)로, `.venv`의 `hailo_platform`을 5.4.0으로 교체한 동일 환경 그대로 재측정했다.

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

결과(`logs/hailo_cma_reclaim_poc.json`):

| 이벤트 | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22(소비 137 MB) |
| child kill(`terminate`) 직후 | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0**(29 MB에서 다시 약 28.5 MB 저하, 이후 수 분이 지나도 `CmaFree`는 512 kB 부근에 붙박인 채) |

이 29 MB → 512 kB 부근의 재저하는, 동시각 다른 프로세스 경합으로는 확인되지 않았지만, 이번 측정만으로는 원인을 특정할 수 없는 미해명 관찰로 남긴다. 초회 로드 후의 페이지 캐시 이용(§8.4)만으로는 이 도중 경과를 설명할 수 없고, RSS·`MemAvailable`·할당 실패를 동시 채취한 반복 시험도 이 실행에는 없기 때문에, §8의 최종 판정 근거로는 사용하지 않는다.

다만 이 512 kB 부근은 §8.3의 `FOLL_LONGTERM` 시험 중에 관찰한 464→1,648 kB와 같은 대역이며, 그 상태에서 20회 생성, 해제, 재로드까지 성공하고 있다. 저값에 이른 과정은 미해명인 채이지만, **이 대역의 `CmaFree` 자체는 즉각적인 위험 상태나 로드 불가를 의미하지 않는다**는 것은 실기에서 확인되었다.

구 진단 도구가 출력한 원문(3차 시행 시점의 잠정 판정. 최종 판정은 §8에서 정정됨):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

이 시행에서 확정된 것은, 초회 HEF 로드 후의 `CmaFree`가 구 판정 기준대로는 회복되지 않았다는 것뿐이다. 프로세스 종료 후 이용 가능 메모리의 상실이나 v5.4.0의 leak 미수정까지는 입증하지 않았다. 3차 시행에서는 잠정적으로 미회수로 해석했지만, 그 해석과 판정 방법은 §8에서 정정했다.

---

## 6. 3차 시행 중의 커널 크래시와 CMA 디버그 코드의 복구(2026-08-17)

### 6.1 사건과 원인 후보

CMA의 해제 경로를 조사하기 위해, 로컬 DKMS 소스의 `linux/vdma/memory.c`에 `linux/mm.h`의 include와, `dma_free_coherent()` 직전에 `virt_to_page()` / `page_count()`를 호출하는 계측 코드를 추가해 두었다. 이 변경을 포함한 모듈을 로드하면 Hailo 이용 시 행(hang)이 걸려 기동 불가가 되었기 때문에, 현재는 `/boot/firmware/cmdline.txt`의 `module_blacklist=hailo1x_pci,hailo_pci`로 자동 로드를 막고 있다.

`dma_alloc_coherent()`가 반환하는 CPU 가상 주소를 `virt_to_page()`로 직접 페이지로 변환하는 것은 DMA API의 계약이 아니다. 반환 주소의 매핑 형식은 allocator 측에 위임되어 있으므로, 여기서 얻는 `page_count()`는 CMA의 참조 수를 올바르게 관측하는 수단이 아니며, 부정한 페이지 참조를 일으킬 수 있다. 계측 코드는 descriptor list와 continuous buffer 양쪽의 해제 경로에서 실행된다.

추가 시각이 10:15:36, 해당 DKMS 빌드 시작이 10:15:39이며, 행이 걸린 모듈에는 이 코드가 포함되어 있었다고 판단할 수 있다. 크래시 직전의 스택 트레이스는 취득하지 못했기 때문에 엄밀한 원인 확정은 아니지만, 바닐라 v5.4.0에는 존재하지 않는 유일한 로컬 실행 코드 변경이며, 가장 유력한 원인 후보로 삼는다.

### 6.2 복구된 상태

다음 7행(`linux/mm.h`의 include, 두 곳의 `virt_to_page()` / `page_count()` 로그)을 제거하고, DKMS를 재빌드하여 `depmod`까지 완료했다.

- 커널: `6.18.39+rpt-rpi-2712`
- 재빌드된 모듈: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- `modules.dep`에는 위 모듈이 등록됨
- blacklist는 유지 중이며, 재빌드 후 모듈은 아직 로드하지 않았다

다음번에는 시리얼 콘솔 등의 복구 경로를 확보한 후 blacklist를 해제하고, 재부팅에 의한 초회 로드를 확인한다. CMA 미회수 문제 자체의 조사에서는, DMA API의 반환 주소를 내부 페이지로 변환하는 계측을 재도입하지 않고, 드라이버가 보유한 버퍼 대장·할당 크기·`dma_free_coherent()` 호출 횟수를 관측 대상으로 한다.

**추기(2026-08-17 후각)**: `cmdline.txt` 백업(`cmdline.txt.bak-blacklisted`)을 준비한 상태에서 blacklist를 해제하고 재부팅하여, 정상 기동함을 확인했다(시리얼 콘솔 `console=serial0,115200`도 설정되어 있어 복구 경로는 확보되어 있다). 이후 §7의 안전한 계측(생 페이지 검사 없음, 기존 카운터·크기의 로그 출력만)으로 조사를 계속했다.

---

## 7. 원인 가설의 형성과 배제 — `FOLL_LONGTERM`의 검증과 반증(2026-08-17)

본 절은 3차 시행을 받은 원인 가설의 형성과, 실험으로 배제할 수 있었던 원인 후보를 기록한다. 여기서의 역할은 후보의 압축이며, CMA leak 유무의 최종 판정은 4차 A/B 시험(§8)에 의존한다.

§6의 크래시를 감안하여, `virt_to_page()` 등 페이지 내부로의 직접 접근을 피한 안전한 계측(`dev_err()`에 의한 로그 출력만. 생 포인터의 검사·변환 없음)으로 조사를 계속했다.

### 7.1 계측 내용

`linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c`의 다음 위치에, 기존 아토믹 카운터(`controller->desc_cma_in_use` / `controller->cma_in_use`)와 할당 크기를 출력하는 로그를 추가했다(페이지 내부로의 접근은 일절 하지 않는다):

- `hailo_desc_list_create`/`hailo_desc_list_release`(descriptor list의 alloc/free)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free`(continuous buffer의 alloc/free)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl`(명시적 해제 ioctl 경로)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy`(사용자 공간 버퍼의 DMA 매핑·언매핑 경로. `buffer_type`/`is_mmio`/`is_dmabuf`도 출력)
- `hailo_vdma_file_context_finalize`(fops_release 시의 일괄 클린업, ENTER/EXIT에서 카운터를 출력)

### 7.2 관측 결과

재부팅 직후(`CmaFree` ≈ 451 MB)부터 `tools/diag_hailo_cma_reclaim.py --signal terminate`를 실행하고, `sudo dmesg | grep CMA_DBG`로 전체 로그를 회수·집계했다.

- **`/proc/meminfo`의 `CmaFree`**: 451 MB → 195 MB(**256 MB 소비**) → kill+30초 대기 후에도 204 MB(**baseline 대비 247 MB 낮은 값**)
- **드라이버 자신의 `desc_cma_in_use`(descriptor list, `dma_alloc_coherent` 경유)**: 최대치도 2〜4 MB 정도. `file_context_finalize`의 EXIT 시점에 확실히 0으로 돌아가 있음
- **`cma_in_use`(continuous buffer, `dma_alloc_coherent` 경유)**: 이 세션 중, 계속 0(continuous buffer는 한 번도 사용되지 않았다)
- **사용자 공간 버퍼의 DMA 매핑(`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: 621회 호출되었고, 이 중 **342회가 8 MB(`0x800000`) 크기**(합계 2.7 GB분의 매핑 호출. 동일한 host측 스테이징 버퍼가 파이프라인 처리로 재사용되고 있는 것으로 보인다). `hailo_vdma_buffer_destroy`는 628회 호출되었고, `buffer_map`과 거의 1대1로 대응하고 있어, **드라이버 자신의 매핑 대장으로서는 파탄나 있지 않다**(`dma_unmap_sg`는 올바르게 호출되고 있다)
- **SWIOTLB(`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. 바운스 버퍼는 한 번도 사용되지 않았다
- Hailo 디바이스는 IOMMU 산하에 있지 않음(`/sys/bus/pci/devices/0001:01:00.0/iommu_group` 없음)

이 시점에서는, `dma_alloc_coherent()` 계열의 드라이버 자신의 할당(desc list·continuous buffer)이 아니라, `hailo_vdma_buffer_map()`이 다루는 「사용자 공간이 확보한 기존 메모리를 DMA용으로 매핑하는」경로(`HAILO_DMA_USER_PTR_BUFFER`)를 CMA 저하의 원인 후보로 해석했다. 이 경로에서는 드라이버가 신규로 CMA를 확보하지 않고, 기존 사용자 페이지를 DMA 가능하게 하기 위해 고정화(pin)한다.

### 7.3 원인 가설: `get_user_pages()`에 `FOLL_LONGTERM`이 지정되어 있지 않다

`linux/vdma/memory.c`의 `prepare_sg_table()`(`hailo_vdma_buffer_map()` 내부에서 호출됨)을 확인한 결과:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages`은(본 커널 6.18.39는 `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`에 해당하므로) 단순한 `get_user_pages()`의 별칭이며, **`FOLL_LONGTERM` 플래그가 지정되어 있지 않다**. 해제 측(`clear_sg_table()`)도 대응하는 `put_page()`를 호출하고 있으며, 신형 `pin_user_pages()`/`unpin_user_pages()` API 계열이 아니라 구식 `get_user_pages()`/`put_page()` 그대로이다.

Linux 커널의 문서화된 작법(`Documentation/core-api/pin_user_pages.rst`)에서는, DMA 전송처럼 **장시간 페이지 참조를 보유하는 코드는 `pin_user_pages()`를 `FOLL_LONGTERM`과 함께 사용해야 한다**고 되어 있다. `FOLL_LONGTERM`을 지정하지 않는 경우, 우연히 CMA 영역 내에 존재하던 사용자 페이지가 `get_user_pages()`로 고정화되어도, CMA가 본래 갖는 「필요할 때 다른 용도로 옮길 수 있는(migratable)」성질이 장기간에 걸쳐 무효화된다. CMA 할당기는 통상, 장기 고정 전에 그 페이지를 CMA 영역 밖으로 마이그레이션하지만, `FOLL_LONGTERM`을 쓰지 않는 경로에서는 이 migration이 일어나지 않기 때문에, **고정화되어 있는 동안은 CMA 영역에서 그만큼이 실질적으로 사라지며, 해제(`put_page()`) 후에도 즉시 CMA의 빈 영역으로 인식되지 않는다**(마이그레이션·컴팩션이 별도로 필요하기 때문).

이 가설은 3차 시행 시점의 단발 측정(§7.2)과는 정합했다:
- 드라이버 자신의 CMA 카운터는 무관(`get_user_pages`는 `dma_alloc_coherent`를 경유하지 않는다)
- map/destroy 호출 횟수는 올바르게 균형을 이루고 있다(`put_page()` 자체는 올바르게 호출되고 있다. 문제는 해제 후 CMA로의 "복귀"가 느리거나/불완전한 것)
- Qwen3-1.7B-Instruct 같은 대형 LLM을 읽어들이면 대량의 8 MB 버퍼가 host 메모리 상에 확보·DMA 매핑되고, 그 일부가 CMA 영역 내의 페이지를 포함하고 있었을 경우 본 문제가 현재화된다
- kill 후의 완만하고 부분적인 `CmaFree` 회복(30초에 +15〜30MB 정도, 그 후도 수 분에 걸쳐 완만하게 증가)과도 정합한다(`put_page()` 자체는 프로세스 종료 시에 확실히 호출되지만, CMA의 빈 영역으로서의 회수에는 추가 처리가 더 필요한 것으로 보인다)

### 7.4 수정 후보의 구현과 실기 검증 → 반증(2026-08-17 속보)

`prepare_sg_table()`을 `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()`에서 `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`로 실제로 치환하고, `<linux/mm.h>`의 include를 추가한 후 빌드·dkms 재등록·실기 로드까지 완료시켰다(`pin_user_pages`/`unpin_user_page` 심볼은 `modprobe --dump-modversions`로 정상 해결됨을 확인).

재부팅 직후의 높은 `CmaFree`(453 MB) 상태부터 동일 repro를 실행한 결과:

| | 수정 전(n=복수 런) | 수정 후(n=1) |
|---|---|---|
| baseline | 436〜451 MB | 453 MB |
| after_llm_loaded | 173〜195 MB(소비 256〜263 MB) | 180 MB(소비 273 MB) |
| after_post_wait | 188〜204 MB(회수 9〜15 MB) | 190 MB(**회수 10 MB**) |
| 구 판정 기준에 의한 `VERDICT` | `FAIL` | **`FAIL`(변화 없음)** |

> 이 표는 런 수와 집계 방법이 비대칭이며, 엄밀한 A/B 비교는 아니다. A/B의 판정은 동일 조건으로 반복한 §8의 결과에 따른다.

`dmesg`로 `CMA_DBG buffer_map`을 확인한 결과, 수정 후에도 동일한 0x800000(8 MB) 크기의 버퍼가 `pin_user_pages` 경유로 문제없이 매핑되고 있어(pin 실패나 커널의 경고는 일절 나오지 않음), 코드 경로 자체는 의도대로 실행되고 있었다. `echo 1 > /proc/sys/vm/compact_memory`에 의한 강제 컴팩션도 효과 없었다. `MemAvailable`은 7.1 GB로 건전한 상태 그대로였고, 시스템 전체의 메모리 부족이 아니라 `CmaFree`라는 특정 회계만 회복되지 않는 점도 수정 전과 동일했다.

**결론: `FOLL_LONGTERM` 결여 가설은 실험에 의해 반증되었다.** `get_user_pages()`→`pin_user_pages()`+`FOLL_LONGTERM`으로의 치환은 Linux 커널의 문서화된 작법에 따르는 정당한 개선이기는 하지만, 본 세션에서 관측하고 있는 CMA 미회수 증상의 직접 원인은 아니었다. 가설 자체는 이론적으로는 앞뒤가 맞으며(CMA의 마이그레이션 기구와 장기 고정의 상호작용은 실재하는 기지의 문제 유형이다), 코드 품질상의 지적으로서는 여전히 유효하지만, **이번 실측 결과를 단독으로 설명하는 근본 원인은 아니다**라고 판단한다.

### 7.5 원인 후보의 배제(최종 판정은 §8)

이하는 실험에 의해 명확하게 **배제**할 수 있었던 원인 후보이다. 이 목록은 가설 검증의 성과로서 유효하지만, leak 유무의 판정 그 자체는 아니다.

- 드라이버 자신의 `dma_alloc_coherent()` 경유의 할당(desc list·continuous buffer) — 수 MB뿐이며, 올바르게 0으로 돌아간다
- SG 매핑의 map/destroy 호출의 불일치 — 균형을 이루고 있다
- SWIOTLB 바운스 버퍼 — 한 번도 사용되지 않았다(`io_tlb_used_hiwater=0`)
- `get_user_pages()`의 `FOLL_LONGTERM` 결여 — 수정을 구현·실기 검증했으나 개선 없음

3차 시행까지 남은 사실은, `MemAvailable`이 건전한 채 `CmaFree`만 초회 로드 후에 저하한다는 것이었다. 당시는 이를 미회수로 해석했지만, 단일 시행으로는 「이용 가능 메모리의 상실」과 「movable CMA 페이지의 페이지 캐시로의 전용」을 구별할 수 없다. 4차에서는 낮은 `CmaFree`인 채로 재시행하여, 실제 로드 가부·반복 시의 순감·RSS·CMA 할당 실패를 측정하여 판정을 정정했다.

---

## 8. 4차 시행: vanilla / `FOLL_LONGTERM` A/B 추시(追試)와 오판정의 확정(2026-08-17)

### 8.1 비교 대상

- `FOLL_LONGTERM` 수정판: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, 로드 시 `srcversion=C84A00ABB326748A1832CE1`
- 공식 vanilla 5.4.0: tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, 로드 시 `srcversion=A260C39C9F2C06DD4FB072E`
- 커널: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef`(2,880,748,478 bytes)

### 8.2 독립 프로세스에서의 2회 연속 로드

| 드라이버 | 시행 | baseline | loaded | exit 후 | baseline 대비 증감 | 로드 |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB(감소)** | 성공 |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB(증가)** | 성공 |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB(감소)** | 성공 |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB(감소)** | 성공 |

두 드라이버 모두, 초회에만 `CmaFree`가 크게 저하하고, 그 낮은 값에서의 2회째 로드는 성공하여 순감이 거의 0이 되었다. 종래의 진단은 「로드 중에 소비한 양 중 몇 MB 되돌아왔는가」만으로 판정했기 때문에, 2회째처럼 개시 시점부터 이미 `CmaFree`가 낮은 정상 케이스까지 `FAIL`로 만들었다.

### 8.3 동일 프로세스 내의 생성·해제·재로드

| 지표 | `FOLL_LONGTERM` | vanilla 1회째 | vanilla 저CMA 반복 |
|---|---:|---:|---:|
| 생성 완료 | 20/20 | 20/20 | 20/20 |
| 1회째 로드 | 성공 | 성공 | 성공 |
| 해제 후 2회째 로드 | 성공 | 성공 | 성공 |
| 생성 1→20의 `CmaFree` | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| 생성 1→20의 `MemAvailable` | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| 생성 중 RSS | 63,888 kB 고정 | 63,904〜63,920 kB | 63,936〜63,952 kB |
| CMA 할당 실패 | 0 | 0 | 0 |

vanilla 저CMA 반복은 `CmaFree=87,424 kB`부터 개시하여, 전체 해제 직후는 79,520 kB, 그 후 87,344 kB까지 되돌아왔다(순차 80 kB). 로드·생성·해제를 반복할수록 잃어가는 거동은 없다. vanilla의 `nr_foll_pin_*`가 0인 것은 `FOLL_PIN` API를 사용하지 않기 때문이며, pin 해제의 성패 비교에는 이용할 수 없다.

### 8.4 초회 저하의 해석

vanilla 재부팅 직후부터 전체 추시 후까지 `Cached`는 1,845,872 kB에서 약 4,988,224 kB로 늘어난 한편, `MemAvailable`은 7,071,280 kB에서 약 6,962,816 kB를 유지했다. 증가량은 multi-GB HEF의 읽기와 정합하며, 초회의 `CmaFree` 저하가 접근 불가능한 메모리의 상실이 아니라, movable CMA 페이지를 포함한 빈 페이지의 페이지 캐시 이용으로서 설명할 수 있다.

### 8.5 운용상의 결론

1. `CmaFree`의 절대값만으로 모델 로드를 거부해서는 안 된다. 실기에서는 1 MB 미만에서도 Qwen 로드에 성공했다.
2. 낮은 `CmaFree`는 텔레메트리로 기록하고, 실제 HailoRT 메모리 할당 에러를 실패 판정에 사용한다.
3. `CmaFree`의 관측값, 실 로드 실패, leak 진단을 혼동하지 않고, 다음 3상태로 다룬다.

| 상태 | 판정 조건 | 제품상의 처치 | 재부팅·조사 |
|---|---|---|---|
| `INCONCLUSIVE` | 초회 저하뿐, 3회 미만, 또는 아래 `FAIL` 조건을 만족하지 않음 | 텔레메트리를 기록하고 로드를 시도한다. 낮은 `CmaFree` 단독으로는 거부하지 않는다 | 재부팅하지 않는다. 동일 조건으로 측정을 추가한다 |
| `OPERATIONAL_FAIL` | HailoRT가 실제 host-memory allocation error를 반환했다 | 그 로드 요청만을 실패로 하고, 불필요한 Hailo workload를 정지하여 재시도한다 | 단발로는 재부팅하지 않는다. 실 실패가 반복되고 workload 해제 후에도 회복되지 않는 경우에만 운용 정책에 따른다. 현행 Phase 0.5는 `would_fire`의 기록만 하고 자동 재부팅하지 않는다 |
| `FAIL` | 낮은 CMA 상태부터 동일 조건을 3회 반복하여, 해제 후 baseline 대비 순감이 **1회 10 MB 초과인 시행이 3회 중 2회 이상**, 3회의 정의 순감 합계가 **20 MB 초과**, 또한 RSS의 단조 증가 또는 `MemAvailable`의 128 MB 초과 저하를 동반 | 개별 로드 가부와는 별개의 leak 진단으로서 기록한다 | 커널 / HailoRT 측의 조사를 재개하고, 직접 증거를 채취한다. 진단 성립만으로는 자동 재부팅하지 않는다 |

이 3회 기준은 향후 진단용이며, 독립 프로세스 시행이 각 드라이버 2회였던 본 절 §8.2에는 소급 적용하지 않았다. 4차의 결론은 §8.2의 A/B에 더해, §8.3의 동일 프로세스 20회 생성·해제·재로드와 저CMA 반복을 종합한 것이다.
4. `FOLL_LONGTERM` 치환은 Linux DMA API의 일반적 작법으로서는 타당하지만, 본건에 대한 효과는 없어, 실기는 공식 vanilla 5.4.0으로 되돌렸다.
5. 자동 재부팅 판정은 낮은 `CmaFree` 단독으로는 발동시키지 않고, 실 로드 실패의 관측을 필수 조건으로 한다.

---

## 9. 향후 액션(2026-08-17 시점)

1. `FOLL_LONGTERM` 수정의 검토와 실기 반증은 완료했다. 재현용 diff와 복원 방법은 부록 B에 보존하며, 프로덕션 드라이버에는 적용하지 않는다.
2. **제품 측은 대응 완료**: `core/hailo_device_core/device_manager_genai.py::acquire_genai`는 v4.620.8에서, 추정 필요량보다 `CmaFree`가 낮아도 `acquire_low_cma_observed`를 기록하고 실 로드를 계속하도록 개수했다. 거부 tracker에 기록하는 것은 factory가 반환한 실 HailoRT host-memory error뿐이며, `tests/test_hailo_cma_false_positive.py`로 낮은 값에서의 로드 계속을 고정하고 있다.
3. 구 포럼 초안의 「후속 `LLM(...)`이 HailoRT에 insufficient host CMA로 거부되었다」는 기술을 로그와 구 구현으로 재감사했다. 인용원 PID 3237 세션에는 release 후의 acquire 기록이 없고, 같은 날짜 로그로 추적할 수 있는 낮은 CMA 거부는 모두 HailoRT 호출 전의 자체 이벤트 `acquire_rejected_low_cma`였다. 다른 세션에서 factory까지 도달한 실패는 status 8(`HAILO_INTERNAL_FAILURE`)이며, host-memory error인 status 3이 아니다. 따라서 구 기술을 뒷받침하는 HailoRT OOM 증거는 없으며, `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`에서는 자체 가드 유래의 거부를 보고에 혼입시킨 취지를 명기하여 철회한다.
4. 정정 게시물은 §8의 수치·적용 범위, 구현 가드의 정정, `FOLL_LONGTERM` 반증, 계측상의 경고를 하나의 현행 초안으로 통합하고, 구 영문 초안을 복사 가능한 형태로 남기지 않는다.
5. 실 로드 실패 또는 반복마다의 누적적 이용 가능 메모리 상실이 재현된 경우에만, 커널 / HailoRT 측의 leak 조사를 재개한다. 그때는 `page_owner`, CMA debug 정보, 할당 실패 status, RSS, `MemAvailable` 등의 직접 증거를 채취한다.

---

## 부록 A. v5.3.0으로의 복구 절차

dkms에서 한 번 `remove --all`한 후의 복구는, apt 캐시에 `.deb`가 남아 있지 않으면 `apt-get install --reinstall`이 실패한다(본건에서도 실패했다: `다운로드할 수 없어 재설치는 불가능`). dpkg는 `hailort-pcie-driver` 패키지를 `ii`(설치 완료)인 채로 인식하고 있기 때문에, 패키지의 소스 전개처 `/usr/src/hailort-pcie-driver/`가 사라지지 않았다면, 거기서 dkms 트리를 수동 재구축할 수 있다.

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf はツリー直下に置く必要がある(linux/pcie/ 配下ではエラーになる)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

복구 확인:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → 정상 응답이면 복구 완료
```

---

## 부록 B. 반증 실험용 드라이버 patch의 보존·적용·vanilla 복원 절차

### B.1 보존물과 위치 설정

A/B에서 실제로 사용한 드라이버 diff를, 다음 파일에 그대로 보존했다.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- 기준 소스: `hailo-ai/hailort-drivers` tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- 대상 파일: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

이 patch는 `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`로의 치환뿐 아니라, §7.1에서 사용한 `CMA_DBG` 계측도 포함한다. 즉, A/B 시의 실험 모듈을 재현하기 위한 **검증용 완전 diff**이며, 프로덕션 권장 patch가 아니다. 실험에서는 효과가 인정되지 않아, 현재 실기는 공식 vanilla 5.4.0으로 복원 완료되었다. HailoRT 사용자 공간 라이브러리에는 변경을 가하지 않았다.

동일한 커널·소스·빌드 환경에서 확인한 식별값은 다음과 같다.

| 상태 | `srcversion` |
|---|---|
| 실험patch | `C84A00ABB326748A1832CE1` |
| 공식vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 적용 전 확인

이하는 Raspberry Pi 상의 `/usr/src/hailo1x_pci-5.4.0`이 위 공식 commit을 가리키고, 대상 3파일에 로컬 변경이 없는 경우에만 실행한다. commit, patch checksum, vanilla `memory.c` checksum 중 어느 하나라도 일치하지 않으면 정지하고, patch를 강제 적용해서는 안 된다.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 실험 patch의 적용

확인이 모두 성공한 경우에 한해, patch를 적용하고 DKMS 모듈을 다음번 boot용으로 설치한다. 로드 중인 모듈을 `rmmod` / `modprobe`로 수동 교체하지 않고, 빌드 후 통상의 재부팅으로 전환한다.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo`는 다음번 boot용으로 설치된 모듈, `/sys/module/.../srcversion`은 현재 로드 중인 모듈을 나타낸다. 이 시점에서 값이 다른 것은 정상이다. 준비가 되면 재부팅하여, 기동 후 양쪽이 일치하는지 확인한다.

```bash
sudo reboot

# 再接続後
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

동일한 검증 환경에서는, patch 적용 후의 기대값은 `C84A00ABB326748A1832CE1`이다. 다를 경우 추측으로 시험을 계속하지 말고, 소스 diff, 커널, DKMS 빌드 로그를 확인한다.

### B.4 공식 vanilla 5.4.0으로의 복원

복원에서는 patch의 역적용에 의존하지 않고, 검증된 commit에서 대상 3파일을 명시적으로 되돌린다. 이로써 부분 적용이나 계측만 남는 상태를 피한다.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

동일한 검증 환경에서는, 설치된 vanilla 모듈의 기대값은 `A260C39C9F2C06DD4FB072E`이다. 현재 로드 중인 값이 다름을 확인한 후 재부팅하고, 재접속 후 양쪽 모두 `A260C39C9F2C06DD4FB072E`가 되는지 확인한다.

---

## 참고: 관련 문서

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — 구 측정에 기반한 CMA leak의 실측 데이터·repro 스크립트·포럼 게시 초안(결론은 본서 §8에서 정정됨)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — v5.2.0 → v5.3.0 이행 시의 기록(디바이스 노드명 `/dev/h1x-0`으로의 변경 등)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — 구 진단에 기반한 CMA leak 문제의 일본어 기록(결론은 본서 §8에서 정정됨)
- `hailo-ai/hailort-drivers` GitHub 저장소(GPL-2.0, 소스 공개): <https://github.com/hailo-ai/hailort-drivers>
