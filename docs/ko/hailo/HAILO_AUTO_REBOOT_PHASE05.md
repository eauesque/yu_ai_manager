# Hailo 자동 재부팅 Phase 0.5 운용 가이드

**작성일**: 2026-05-17 (v4.215.0)
**대상**: Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0의 CMA leak 관측 운용
**상태**: 관측 단계. 실제 재부팅은 수행하지 않으며, `would_fire` 이벤트만 기록합니다.

---

## 1. Phase 0.5의 목적

Phase 0.5는 HailoRT 5.3.0 + `hailo1x_pci`의 CMA leak에 대한 자동 재부팅 설계의 관측 단계입니다.

이 단계에서 판정기는 다음 상태를 계산합니다.

| 상태 | 조건 |
|---|---|
| `idle` | 정상 상태 |
| `prewarn` | `CmaFree < 80 MB`가 180초 지속 |
| `draining` | `CmaFree < 30 MB`가 60초 지속, 또는 `acquire_genai`의 사전 reject가 3회 연속 발생 |
| `would_fire` | `draining`에서 120초 경과 |

중요: Phase 0.5에서는 `would_fire`에 도달해도 Pi를 재부팅하지 않습니다. `logs/hailo_auto_reboot.log`에 JSON Lines 형식으로 기록할 뿐입니다.

---

## 2. 기본값이 `mode = "off"`인 이유

`hailo.auto_reboot.mode`의 기본값은 `"off"`입니다. 자동 재부팅은 운용자의 작업을 중단시킬 수 있으므로, 운용자가 명시적으로 opt-in한 환경에서만 관측을 시작합니다.

Phase 0.5의 권장 설정은 다음과 같습니다.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true`는 Phase 0.5의 전제 조건입니다. 실제 재부팅 경로는 Phase 4 이후에 다룹니다.

### 2.1 Opt-in 절차

시작 시 config는 `--config` 또는 `TAGDB_CONFIG`로 지정한 파일을 우선합니다. 미지정 시 repository 루트의 `config.json`, 다음으로 `tagdb_config.json`을 읽습니다.

예시:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

`<repo>/config.json` 또는 운용 시 `--config` / `TAGDB_CONFIG`로 지정한 JSON에 다음 설정을 추가합니다.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

서버를 재시작하여 설정을 적용합니다. 시작 방법에 맞게 실제 사용하는 인수를 유지하세요.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

systemd로 운용 중인 경우, 해당 unit을 재시작합니다.

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 비활성화 절차

같은 config에서 `hailo.auto_reboot.mode`를 `"off"`로 되돌리고 서버를 재시작합니다.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

`mode = "off"`에서는 JSON Lines의 관측 이벤트는 남지만, `error.log`에 WARN 요약은 출력하지 않습니다.

---

## 3. 로그 읽는 방법

관측 로그는 다음 파일에 출력됩니다.

```text
logs/hailo_auto_reboot.log
```

형식은 JSON Lines입니다. 주요 이벤트는 다음과 같습니다.

| 이벤트 | 의미 |
|---|---|
| `boot_baseline` | 시작 시 관측 시작점 |
| `prewarn_entered` | PREWARN 조건 성립 |
| `drain_entered` | DRAIN 조건 성립 |
| `would_fire` | Phase 1+에서 재부팅 발동 후보가 되는 시점 |
| `drain_cleared` | CMA가 회복되어 DRAIN 해제 |

예시:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

확인 명령어 예시:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

`would_fire`가 빈번하게 발생하는 경우, 현재 임계값으로는 실제 운용 중 Pi 재부팅이 필요할 가능성이 높음을 나타냅니다. 반대로 `prewarn_entered`만 발생하고 `drain_entered`로 진행되지 않는 경우, Phase 1 이전에 임계값 또는 유예 시간을 재조정할 수 있습니다.

---

## 4. API 확인 절차

admin API key로 `/api/system/cma`를 확인합니다.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

응답 내의 `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state`, `cma.auto_reboot.consecutive_rejects`를 확인합니다.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. 관측 기간

목표는 1〜2주입니다. 최소한 다음 패턴을 포함하는 기간을 확보하세요.

- LLM의 일반 채팅 이용
- 장시간 채팅 이용
- Hailo GenAI model의 로드 실패 또는 사전 reject가 발생하는 조작
- Pi 재부팅 후 첫 번째 로드

관측 완료의 기준은 1〜2주분의 `prewarn_entered` / `drain_entered` / `would_fire` 발생 빈도를 집계할 수 있는 것입니다. 관측 후에는 `would_fire`의 횟수, `drain_entered`의 이유(`cma` / `rejects`), `CmaFree`의 감소 속도를 확인하여 Phase 1 투입 전에 임계값을 재확정합니다.

집계 예시:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. 관련 자료

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
