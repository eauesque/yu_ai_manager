# Sweeps API

Bridge sweep（NAI / SD WebUI / ComfyUI のパラメータ振り）の実行履歴を扱うエンドポイント群。

実行情報は v4.183.0 から `sweeps` / `sweep_axes` テーブル（migration 68）に保存され、`/sweep/<id>` ページの履歴表示はこの API を介して描画される。

## GET /api/sweeps/history

直近の sweep 一覧を返す。`/sweep/<id>` ページが「現在の sweep と同条件」で履歴を絞り込むのに使う。

### クエリパラメータ

| パラメータ | 型 | 既定値 | 説明 |
|---|---|---|---|
| `limit` | int (1..500) | 50 | 返却件数 |
| `ref` | string | — | リファレンス sweep id。`match` を使うときは必須 |
| `match` | CSV | — | マッチさせる項目のカンマ区切り。値は下表参照 |
| `tol_steps` | string | `exact` | ステップ数の許容幅: `exact` / `5` / `10` / `20`（%）|
| `tol_cfg` | string | `exact` | CFG の許容幅: 同上 |
| `completed_only` | `0`/`1` | `0` | `1` で `status='completed'` のみ |
| `saved_only` | `0`/`1` | `0` | `1` で `first_file_id IS NOT NULL` のみ |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### `match` で指定可能なキー

- `bridge` / `checkpoint` / `vae` / `sampler` — 文字列完全一致
- `positive` / `negative` — `prompt_template` / `negative_template` の完全一致
- `axisX` / `axisY` / `axisZ` — `sweep_axes` の axis_index=0/1/2 の `param` が一致
- `resolution` — `width` AND `height` 一致
- `steps` / `cfg` — 数値一致（`tol_steps` / `tol_cfg` で許容幅を指定可能）
- `baseSeed` — `base_seed` 一致

リファレンス sweep に値が存在しない項目は無視される（UI 側ではチェックボックスが disabled）。

### レスポンス

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "base_seed": 1234567,
        "created_at": 1714992000,
        "prompt_template": "best quality, ...",
        "negative_template": "worst quality, ...",
        "checkpoint": "nai-anime-v3",
        "vae": null,
        "sampler": "k_euler",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "last_file_id": 12399,
        "file_count": 6,
        "status": "completed",
        "updated_at": 1714992100,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

`total` は `sweeps` テーブルの全件数（フィルタ前）。UI の「{shown} / {total} 件一致」表示に使う。

## GET /api/sweep/info/<file_id>

指定した file_id の XMP packet から sweep meta を読み、構造化して返す。詳細は `core/bridge_core/sweep_xmp.py` 参照。

## GET /api/sweep/files/<sweep_id>

ヒント file_id の親フォルダを scandir し、同じ sweep id を持つファイルを集めて返す。

## DB 投入経路

- **保存時**: `core/bridge_core/bridge_save_batch.py` が画像保存後に `upsert_sweep_from_meta()` を呼ぶ。run header と axes は初回のみ書き、2 回目以降は `last_file_id` / `file_count` / `updated_at` だけ更新
- **既存ファイルの取り込み**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`。`has_sweep=1` のファイルから XMP を読み復元。idempotent

## 既知の制約

- 非同期 save 経路 (`return_file_ids=False`) では `first_file_id` が NULL のまま入ることがある。UI ではリンク不可として表示
- `prompt_template` / `negative_template` は run-level に 1 件しか持たない。S/R 等の per-axis 置換は復元せず、軸の値は per-image XMP から `/api/sweep/info/<file_id>` 経由で参照する設計
