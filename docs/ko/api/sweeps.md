# Sweeps API

Bridge sweep (NAI / SD WebUI / ComfyUI 매개변수 축 스윕)의 실행 이력 엔드포인트.

v4.183.0부터 실행 정보가 `sweeps` / `sweep_axes` 테이블 (migration 68)에 영속화됨. `/sweep/<id>` 페이지의 이력 목록은 이 API를 통해 렌더링.

## GET /api/sweeps/history

최근 sweep 목록 반환. "현재 sweep과 동일 조건" 필터링 지원.

### 쿼리 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `limit` | int (1..500) | 50 | 반환 건수 |
| `ref` | string | — | 참조 sweep id; `match` 사용 시 필수 |
| `match` | CSV | — | 참조와 비교할 필드 (콤마 구분) |
| `tol_steps` | string | `exact` | steps 허용폭: `exact` / `5` / `10` / `20` (%) |
| `tol_cfg` | string | `exact` | CFG 허용폭 (동일) |
| `completed_only` | `0`/`1` | `0` | `1`이면 `status='completed'`만 |
| `saved_only` | `0`/`1` | `0` | `1`이면 `first_file_id`가 있는 것만 |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### 사용 가능한 `match` 키

- `bridge` / `checkpoint` / `vae` / `sampler` — 문자열 완전 일치
- `positive` / `negative` — `prompt_template` / `negative_template` 완전 일치
- `axisX` / `axisY` / `axisZ` — axis_index 0/1/2의 `sweep_axes.param` 일치
- `resolution` — `width`와 `height` 동시 일치
- `steps` / `cfg` — 수치 일치 (허용폭은 `tol_*`로 제어)
- `baseSeed` — `base_seed` 일치

참조 sweep에 값이 없는 필드는 무시됨.

### 응답

```json
{
  "ok": true,
  "data": {
    "entries": [{
      "id": "uuid-xxxx", "bridge": "nai",
      "created_at": 1714992000,
      "checkpoint": "nai-anime-v3", "sampler": "k_euler",
      "width": 832, "height": 1216, "steps": 28, "cfg": 5.5,
      "axis_count": 1, "first_file_id": 12345,
      "axes_params": ["cfg_rescale"]
    }],
    "total": 142
  }
}
```

## 데이터 입력 경로

- **저장 시**: `core/bridge_core/bridge_save_batch.py`가 auto-import 후 `upsert_sweep_from_meta()` 호출
- **기존 파일**: `uv run python scripts/backfill_sweeps.py`가 `has_sweep=1` 파일을 스캔하여 XMP에서 재구성. idempotent
