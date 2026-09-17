# 메시 추론 아키텍처

> 대상 버전: v4.67.0 이후

## 개요

메시 추론 시스템은 LAN 상의 여러 yu_ai_manager 노드가 협력하여 추론 태스크 (tagger / clip / yolo / whisper)를 분산 처리하는 구조입니다. mDNS에 의한 자동 발견, asyncio.Queue를 사용한 워크 스틸링, 노드별 비활성화 필터를 조합하여 설정 없이 수평 확장합니다.

---

## 전체 아키텍처

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  시작 시 InferenceRouter를 생성하고              │
│  core.mesh_inference.set_router()에 등록        │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (LAN 피어 목록)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing 큐
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (병행 워커)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### 컴포넌트 책임

| 컴포넌트 | 위치 | 책임 |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | 파사드: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | 배치 분산 / 워크 스틸링 |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | 피어 관리 / 온라인 판정 |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | per-peer-per-type 비활성화 필터 |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | 로컬 엔진 참조 |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | async→thread 브리지 |
| `persistence` | `core/mesh_inference/persistence.py` | JSON 영구화 |

---

## 피어 자동 발견 (mDNS Phase B)

`_yu-ai._tcp.local.` 서비스를 LAN에 어드버타이즈하고, 동일 서비스를 브라우즈하여 상호 발견합니다.

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  PeerRegistry에 등록              │
```

발견 플로우 상세:
1. `LlmRouterMdnsBridge`가 mDNS 이벤트를 수신
2. `/api/mdns/identity` HTTP 검증으로 피어가 진짜 yu_ai_manager인지 확인
3. 검증 성공 후 `PeerRegistry`에 피어를 추가
4. `InferenceState.get_inference_types()`가 반환하는 타입 목록을 `PeerInfo.inference_types`에 반영

---

## 추론 타입과 백엔드

`InferenceState.get_inference_types()`가 반환하는 문자열이 `PeerInfo.inference_types`에 설정되며, 라우팅의 기준이 됩니다.

| 추론 타입 | 백엔드 | 용도 |
|---|---|---|
| `tagger` | ONNX (WD14 등) / Hailo NPU | 이미지 태그 부여 |
| `clip` | ONNX / Hailo / 리모트 | 이미지 임베딩 벡터 |
| `yolo` | ONNX / Hailo | 물체 검출 |
| `whisper` | faster-whisper / 리모트 | 음성 문자 변환 |
| `hailo` | Hailo-10H vdevice | Hailo 디바이스 직접 액세스 |
| `llm` | OpenAI-compat / Ollama | LLM 추론 |

엔진이 `None`인 타입은 `get_inference_types()` 목록에 포함되지 않으므로, 해당 피어에는 라우팅되지 않습니다.

---

## 워크 스틸링 알고리즘

```python
# router.py (개략)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty로 탈출
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**특성:**
- 피어당 1워커를 `asyncio.create_task()`로 기동
- 공유 큐에서 `batch_size` 단위로 추출 (`get_nowait()`로 논블로킹)
- 빠른 피어가 큐를 더 많이 소비 → 자연스러운 부하 균등
- `stats_lock`으로 `processed` / `errors`를 배타적 갱신

---

## DisableAwareStrategy (v4.67.0)

`BatchInferenceStrategy`를 상속하고, `MeshInferenceState`의 비활성화 오버레이로 추가 필터를 적용합니다.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()`가 온라인 / capability 필터를 적용
- 그 후 `(peer_id, inference_type)` 쌍이 비활성화되어 있으면 제외
- WebUI에서 특정 피어의 특정 타입을 일시 중지하는 용도로 사용

---

## 영구화: data/mesh_inference_state.json

비활성화 오버레이를 아토믹 기록으로 영구화합니다.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()`가 `.tmp` 파일에 기록한 후 `os.replace()`로 아토믹 교체
- `persistence.load_state()`는 파일 부재 / JSON 손상 / 버전 불일치 중 어떤 경우에도 빈 상태로 폴백
- `set_router()` 시 한 번만 로드 (`_load_persistence_once()`)하여 `DisableAwareStrategy`에 주입

---

## 폴백: 피어 장애 시 자동 복구

```
dispatch_inference() 호출
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
피어가 0건인 경우:
    경고 로그를 출력하고 {"status":"ok","processed":0,"errors":N}을 반환
    ↓
호출 측은 errors>0을 감지하여 로컬 처리로 폴백
```

- `PeerRegistry`는 피어의 생존 확인에 실패하면 `status="offline"`으로 전환
- `BatchInferenceStrategy.select_peers()`는 `status=="online"`만 반환
- 로컬 노드는 항상 `all_peers`의 선두에 포함되므로, 리모트가 전멸해도 로컬 처리로 자동 복구

---

## dispatch_sync: 동기 호출 브리지

백그라운드 스레드 (이벤트 루프 없음)에서 `InferenceRouter`를 호출하기 위한 브리지입니다.

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**주의:** 기존 `asyncio` 루프 내에서는 사용 불가. 코루틴 내에서는 `await router.dispatch_inference(...)`를 직접 사용하세요.

### tagger 배치 코디네이터

`run_tagger_batch()`는 `dispatch_inference_sync`를 사용한 고수준 유틸리티로, 백그라운드 스레드에서 태그 부여 작업을 기동합니다.

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

`job_manager`로 작업 중복 기동을 방지하고, 미태그 파일을 자동 선택합니다.

---

## 파사드 API 요약

```python
from core.mesh_inference import get_router, has_mesh, set_router

# 사용 예
router = get_router()
if router is not None:
    result = await router.dispatch_inference(
        inference_type="tagger",
        items=file_paths,
        batch_size=32,
        worker_fn=my_worker,
        result_fn=save_results,
        progress_fn=update_progress,
    )
```

| 함수 | 설명 |
|---|---|
| `get_router()` | 활성 InferenceRouter를 반환 (미등록 시 None) |
| `has_mesh()` | 메시가 이용 가능한지 bool로 반환 |
| `set_router(router)` | CoworkManager가 시작/종료 시 호출. 시작 시 영구화 로드 및 전략 주입을 실행 |

---

## 관련 파일

- `core/mesh_inference/__init__.py` — 파사드
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — JSON 영구화
- `core/mesh_inference/dispatch_sync.py` — 동기 브리지 + tagger 배치
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + 워크 스틸링
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — 비활성화 오버레이 영구화 대상
