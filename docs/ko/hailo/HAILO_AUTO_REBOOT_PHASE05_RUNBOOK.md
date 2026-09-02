# Hailo Auto-Reboot Phase 0.5 — 본 환경 운용 런북

**작성일**: 2026-05-17 (v4.215.1)
**대상 환경**: 본 저장소를 실행하는 Pi 5
**목적**: 기존 채팅 세션 로그가 유실되더라도 이 런북만으로 Phase 0.5 관측을 시작·확인·종료할 수 있도록 절차를 남긴다.
**설계 사양**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**일반 운영자 가이드**: `docs/ko/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (본 문서는 그 환경별 특화 버전)

---

## 0. 전제 조건 및 완료된 작업

- v4.215.1에서 Phase 0.5 관측 구현이 main에 병합·push 완료 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (저장소 루트)에 **2026-05-17 기준** `hailo.auto_reboot` 블록 추가 완료
  - 권장 설정: `mode = "lazy"` + `dry_run = true`
  - 백업: `config.json.bak.<타임스탬프>`
- **실제 재부팅은 호출되지 않음** (`dry_run = true` + Phase 0.5 설계는 `would_fire` 이벤트만 기록)

config.json 확인:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → {"mode":"lazy","dry_run":true,...} 가 출력되면 OK
```

---

## 1. 초기 시작 및 활성화 절차

### 1.1 서버 재시작

config 변경을 반영하려면 반드시 재시작이 필요합니다. **현재 사용 중인 시작 방식 그대로 재시작**하세요.

대표적인 시작 명령 (실제 환경에 맞게 조정):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

systemd 서비스로 등록된 경우 `sudo systemctl restart <unit>` 으로 해당 unit을 재시작합니다.

### 1.2 시작 후 30초 이내 확인 사항 (3가지)

#### A. `boot_baseline` 이벤트가 기록되었는가?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

예상 결과: `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}` 행이 1줄 있어야 함.

**출력되지 않을 경우 문제 해결**:

- `logs/hailo_auto_reboot.log` 자체가 없음 → judge loop가 시작되지 않음 (`["full"]` 모드로 시작하지 않았거나 `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 환경 변수가 설정된 경우)
- 파일은 있지만 비어 있음 → `core/hailo_device_core/auto_reboot_logger.py`의 경로 해석 실패; `logs/` 디렉터리의 권한 확인
- `cma_free_mb: null` → `/proc/meminfo` 읽기 실패 (Pi 이외 환경에서 실행 시 예상되는 동작, 무해함)

#### B. `/api/system/cma` 응답에서 opt-in이 적용되었는가?

브라우저에서 PIN으로 로그인 중이라면 API key 불필요. curl을 직접 사용하거나, PIN 로그인 중인 브라우저 DevTools 콘솔에서:

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

예상 결과:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

`enabled: false` 또는 `mode: "off"` 인 경우 → config.json의 `hailo.auto_reboot.mode`가 `"lazy"` 인지, 서버 재시작이 완료되었는지 확인.

#### C. `error.log`에 시작 오류가 없는가?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

아무것도 출력되지 않으면 OK. 오류가 있으면 본 문서 말미 「8. 알려진 함정」을 참조.

---

## 2. 관측 기간 중 일상 운용

### 2.1 평상시와 동일하게 사용

**주요 액션**:

- `/ext/hailo-genai/chat` 또는 `/tools`를 통해 **평소대로 LLM 채팅 사용** (Qwen3-1.7B 등)
- 필요하다면 VLM / S2T도 사용
- 장시간 채팅 (30분 이상 연속)이나 여러 모델 전환도 의도적으로 시도하면 관측 데이터의 폭이 넓어짐

특별한 검증은 불필요. **평소대로 사용할수록 데이터가 쌓이는 것**이 Phase 0.5의 설계 의도.

### 2.2 주간 리뷰 (주 1회, 5분)

```bash
cd /home/pi/GitHub/yu_ai_manager

# 이벤트 종류별 발생 횟수
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# would_fire 의 발생 시각과 CmaFree
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# drain_entered 의 reason (cma / rejects 중 어느 쪽으로 진입했는가)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**체크포인트**:

- `would_fire` 가 1건 이상 → Phase 1 전환에 가치 있음 (기록된 시각과 수동으로 재부팅했던 시각이 일치하는지 확인)
- `prewarn_entered` 가 빈발하지만 `drain_entered` 로 진행하지 않음 → `prewarn_threshold_mb` (80 MB)가 너무 낮을 가능성, 재확인 필요
- `drain_entered` 의 reason이 `rejects` 뿐 → reject 기인 DRAIN이므로 임계값 재확인과는 별도의 대책 필요

---

## 3. 관측 종료 및 Phase 1 투입 판단 기준

### 3.1 필요한 관측 기간

**최소 7일 / 권장 14일**. 최소한 다음 패턴을 포함하는 기간을 확보:

- LLM 일반 채팅
- LLM 장시간 연속 채팅 (1세션 30분 이상)
- VLM / S2T 전환
- `acquire_genai` 사전 reject (CmaFree 부족)가 최소 1회 발생하는 조작
- Pi 재부팅 후 첫 로드

### 3.2 Phase 1 투입의 수치 기준

집계:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

판단:

| 관측 결과 | Phase 1 판단 |
|---|---|
| `would_fire` ≥ 1건 | **GO** (실제 재부팅 자동화에 가치 있음) |
| `would_fire` = 0, `drain_entered` ≥ 1건 | 임계값 재조정 후 Phase 1 투입 검토 (DRAIN까지는 오지만 would_fire에 도달하지 않음 = `fire_grace_seconds` 단축 여지) |
| `prewarn_entered` 만, `drain_entered` = 0 | 현재 임계값으로는 한 번도 「중증」이 되지 않음 → 사용 패턴에 따라 Phase 1 전환 불필요 |
| 전체 이벤트 0 (`boot_baseline` 만) | CMA가 고갈되지 않는 사용 방식 → Phase 1 불필요 |

### 3.3 관측 완료 후 작업

1. 집계 결과를 `docs/ko/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (신규)에 저장
2. Phase 1 투입 시: spec rev3 §5.2의 Phase 1 (UI DRAIN 배너 + i18n)으로 진행; §3.1 임계값을 관측 기반으로 재확정
3. Phase 1 불필요 시: config.json에서 `mode = "off"` 로 되돌리고 관측 로그를 아카이브

---

## 4. 비활성화 절차 (긴급 시 / 관측 중단 시)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# 서버 재시작
```

`mode = "off"` 로 해도 JSONL 이벤트는 계속 기록됨 (`error.log` 에의 WARN 출력은 억제됨). 완전히 멈추려면 환경 변수로:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. 로그 파일 목록 (관련)

| 파일 | 용도 |
|---|---|
| `logs/hailo_auto_reboot.log` | **본 기능의 주 로그**. JSONL, 10 MB × 30 백업으로 로테이션 |
| `logs/hailo_cma.log` | 기존 CMA 이벤트 로거 (v4.214.10~). `acquire_genai` 등의 VDevice/모델 라이프사이클 이벤트 |
| `logs/error.log` | 앱 전체 오류. `mode != "off"` 일 때 `drain_entered` / `would_fire` 의 WARN 요약도 출력됨 |

---

## 6. 관련 코드 위치 (향후 조사용)

| 기능 | 파일 |
|---|---|
| 상태 머신 + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| 백그라운드 루프 진입점 | `core/web/startup_background_hailo_judge.py` |
| 백그라운드 태스크 등록 | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Config 기본값 | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| acquire_genai hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma` 확장 | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| 단위 테스트 | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. 리뷰 이력 (참고용)

본 구현은 AGENTS 규정의 전체 플로우를 통과함 (v4.215.1 commit 메시지 참조). 각 보고서 파일은 `.claude/agent-outputs/` 아래에 작성되었으나, 해당 디렉터리는 `.gitignore` 대상으로 git 관리 외. 필요 시 재생성 가능.

---

## 8. 알려진 함정

| 증상 | 원인 및 대처 |
|---|---|
| `logs/hailo_auto_reboot.log` 에 아무것도 출력되지 않음 | 서버 미재시작 / `mode = "off"` 유지 / `["full"]` 모드로 시작하지 않음 / `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 환경 변수가 설정됨 |
| `cma_free_mb: null` 계속 | Pi 이외 환경(WSL2 등)에서 시작하거나 `/proc/meminfo` 읽기 실패. Pi 실기에서 재확인 |
| `hailo_runtime_version: null` | `hailo_platform` 패키지가 미설치된 환경. 실제 Pi 5에서는 HailoRT 5.3.0 런타임이 있으면 취득됨 |
| `would_fire` 가 전혀 출력되지 않음 | 사용 부하가 너무 가볍거나 임계값이 너무 느슨함. 장시간 연속 채팅 / 모델 전환을 시도하고 재관측 |
| `eager` 모드를 설정했지만 작동하지 않음 | Phase 0.5에서 `eager` 는 의도적으로 `off` fallback (경고 로그 출력). Phase 1+에서 구현 예정 |

---

## 9. 긴급 롤백

만일 Phase 0.5 구현 자체에 문제가 발생한 경우 (실제 재부팅은 호출되지 않으므로 가능성은 낮지만):

```bash
cd /home/pi/GitHub/yu_ai_manager
# v4.215.1 → v4.214.13 (사양만, 구현 이전)으로 롤백
git revert -m 1 69be148c6
git push
```

또는 **설정만으로 완전 비활성화** (권장):

```bash
# 시작 환경에 추가하고 서버 재시작
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. 본 문서의 유지보수

- 관측 완료 시 **§3.3 집계 결과를 본 문서 말미에 추가** 할 것 (향후 채팅 세션에서 Phase 1 판단 시 필요)
- Phase 1 투입 후에는 본 문서를 `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` 로 이름 변경하고, Phase 1용 런북을 새로 작성
- 본 문서는 `/home/pi/GitHub/yu_ai_manager/docs/ko/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` 에 배치 (git 관리하)
