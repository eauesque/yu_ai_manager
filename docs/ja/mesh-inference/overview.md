# メッシュ推論アーキテクチャ

> 対象バージョン: v4.67.0 以降

## 概要

メッシュ推論システムは、LAN 上の複数の yu_ai_manager ノードが協調して推論タスク（tagger / clip / yolo / whisper）を分散処理する仕組みです。mDNS による自動発見、asyncio.Queue を使ったワークスティーリング、ノードごとの無効化フィルタを組み合わせて、設定なしで水平スケールします。

---

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  起動時に InferenceRouter を生成し               │
│  core.mesh_inference.set_router() に登録        │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (LAN ピア一覧)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing キュー
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (並行ワーカー)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### コンポーネント責務

| コンポーネント | 場所 | 責務 |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | ファサード: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | バッチ分散・ワークスティーリング |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | ピア管理・オンライン判定 |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | per-peer-per-type 無効化フィルタ |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | ローカルエンジン参照 |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | async→thread ブリッジ |
| `persistence` | `core/mesh_inference/persistence.py` | JSON 永続化 |

---

## ピア自動発見 (mDNS Phase B)

`_yu-ai._tcp.local.` サービスを LAN にアドバタイズし、同一サービスをブラウズすることで相互発見します。

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  PeerRegistry に登録              │
```

発見フローの詳細:
1. `LlmRouterMdnsBridge` が mDNS イベントを受信
2. `/api/mdns/identity` HTTP 検証でピアが本物の yu_ai_manager か確認
3. 検証成功後、`PeerRegistry` にピアを追加
4. `InferenceState.get_inference_types()` が返す型一覧を `PeerInfo.inference_types` に反映

---

## 推論タイプとバックエンド

`InferenceState.get_inference_types()` が返す文字列が `PeerInfo.inference_types` に設定され、ルーティングの基準になります。

| 推論タイプ | バックエンド | 用途 |
|---|---|---|
| `tagger` | ONNX (WD14 等) / Hailo NPU | 画像タグ付け |
| `clip` | ONNX / Hailo / リモート | 画像埋め込みベクトル |
| `yolo` | ONNX / Hailo | 物体検出 |
| `whisper` | faster-whisper / リモート | 音声文字起こし |
| `hailo` | Hailo-10H vdevice | Hailo デバイス直接アクセス |
| `llm` | OpenAI-compat / Ollama | LLM 推論 |

エンジンが `None` のタイプは `get_inference_types()` のリストに含まれないため、そのピアにはルーティングされません。

---

## ワークスティーリング・アルゴリズム

```python
# router.py (概略)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty で抜ける
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**特性:**
- ピアごとに 1 ワーカーを `asyncio.create_task()` で起動
- 共有キューから `batch_size` 単位で取り出す（`get_nowait()` で非ブロッキング）
- 高速なピアがキューを多く消化 → 自然な負荷均等
- `stats_lock` で `processed` / `errors` を排他更新

---

## DisableAwareStrategy (v4.67.0)

`BatchInferenceStrategy` を継承し、`MeshInferenceState` の無効化オーバーレイで追加フィルタをかけます。

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` がオンライン・capability フィルタを適用
- その後、`(peer_id, inference_type)` ペアが無効化されていれば除外
- WebUI から特定ピアの特定タイプを一時停止する用途に使用

---

## 永続化: data/mesh_inference_state.json

無効化オーバーレイをアトミック書き込みで永続化します。

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` が `.tmp` ファイルに書いてから `os.replace()` でアトミック置換
- `persistence.load_state()` はファイル不在・JSON 破損・バージョン不一致のいずれでも空状態にフォールバック
- `set_router()` 時に一度だけロード（`_load_persistence_once()`）し、`DisableAwareStrategy` に注入

---

## フォールバック: ピア障害時の自動復帰

```
dispatch_inference() 呼び出し
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
ピアが 0 件の場合:
    警告ログを出力し {"status":"ok","processed":0,"errors":N} を返す
    ↓
呼び出し元は errors>0 を検知してローカル処理にフォールバック
```

- `PeerRegistry` はピアの生存確認に失敗すると `status="offline"` に遷移
- `BatchInferenceStrategy.select_peers()` は `status=="online"` のみを返す
- ローカルノードは常に `all_peers` の先頭に含まれるため、リモートが全滅してもローカル処理に自動復帰

---

## dispatch_sync: 同期呼び出しブリッジ

バックグラウンドスレッド（イベントループなし）から `InferenceRouter` を呼ぶためのブリッジです。

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**注意:** 既存の `asyncio` ループ内からは使用不可。コルーチン内では `await router.dispatch_inference(...)` を直接使うこと。

### tagger バッチコーディネータ

`run_tagger_batch()` は `dispatch_inference_sync` を使った高レベルユーティリティで、バックグラウンドスレッドでタグ付けジョブを起動します。

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

`job_manager` でジョブ重複起動を防止し、未タグファイルを自動選択します。

---

## ファサード API まとめ

```python
from core.mesh_inference import get_router, has_mesh, set_router

# 使用例
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

| 関数 | 説明 |
|---|---|
| `get_router()` | アクティブな InferenceRouter を返す（未登録時は None）|
| `has_mesh()` | メッシュが利用可能かを bool で返す |
| `set_router(router)` | CoworkManager が起動/停止時に呼ぶ。起動時に永続化ロードと戦略注入を実行 |

---

## 関連ファイル

- `core/mesh_inference/__init__.py` — ファサード
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — JSON 永続化
- `core/mesh_inference/dispatch_sync.py` — 同期ブリッジ + tagger バッチ
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + ワークスティーリング
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — 無効化オーバーレイ永続化先
