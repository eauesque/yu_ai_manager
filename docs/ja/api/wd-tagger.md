# WD Tagger API

WD Tagger (Waifu Diffusion Tagger) による Danbooru タグ自動推論に関する API。設定管理、単一/バッチタグ付け、タグ CRUD、モデル管理、XMP 読み取り、VLM 接続テストを提供する。

## GET /api/wd-tagger/config

WD Tagger の現在の設定を取得。

### パラメータ

なし

### レスポンス

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

WD Tagger の設定を保存・更新。

### レート制限

WRITE

### リクエスト

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| *(任意のキー)* | any | いいえ | 設定フィールド。不明なキーや無効な値は `400` エラーになる |

### レスポンス

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `invalid_json` | 400 | リクエストボディが JSON オブジェクトでない |
| `invalid_value` | 400 | 設定値が無効 |

## POST /api/wd-tagger/tag/<file_id>

指定ファイルに対して WD Tagger で Danbooru タグを推論・付与する。

### レート制限

HEAVY

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `file_id` | int | ファイル ID (パスパラメータ) |

### リクエスト

```json
{
  "force": false
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `force` | boolean | いいえ | `true` の場合、既存のタグを上書きして再推論する。デフォルト `false` |

### レスポンス

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `tag_error` | 400 | タグ付けに失敗（ファイル不在、画像読み込み失敗等） |

## GET /api/wd-tagger/tags/<file_id>

指定ファイルに保存済みの WD Tagger タグを取得。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `model` | string | いいえ | モデル名でフィルタ (クエリパラメータ) |
| `all` | boolean | いいえ | `1`, `true`, `yes` の場合、active model と `model` フィルタを無視して全モデルのタグを返す |

### レスポンス

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

指定ファイルの WD Tagger タグを削除。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `model` | string | いいえ | モデル名でフィルタ (クエリパラメータ)。省略時は全モデルのタグを削除 |

### レスポンス

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

複数ファイルの WD Tagger タグを一括削除。

### レート制限

WRITE

### リクエスト

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_ids` | list | はい | ファイル ID の配列 (最大 500) |
| `model` | string | いいえ | モデル名でフィルタ。省略時は全モデルのタグを削除 |

### レスポンス

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

複数の WD Tagger model で同じファイルを再タグ付けすると、`file_wd_tags` には
model ごとのタグが履歴として残る。Active model を設定すると、詳細表示、
`ai_analyzed` 検索、WD Tagger 内部の「タグ付きファイル」判定は active model
のタグだけを見る。未設定の場合は従来通り全 model のタグを混在して扱う。

### UI での設定

retag modal の上部に現在の `Active model` が表示される。`Change` dropdown から
利用可能な model を選ぶと active model が切り替わる。`(none / reset)` を選ぶと
未設定に戻る。

retag 完了時は、デフォルトでその model が active model に自動切替される。
この挙動は retag modal の「再タグ付け後にアクティブモデルにする」チェックを
OFF にすると抑止できる。

旧 model の row は自動では物理削除されない。履歴保持のため DB 上に残る。
不要な場合のみ、retag modal の「他のモデルのタグも削除」を ON にし、確認
ダイアログで承認すると旧 model のタグを明示削除できる。


### GET /api/wd-tagger/profiles

登録済み WD Tagger profile と現在の active model を取得する。admin scope 必須。

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

現在の active model と、DB に存在する model 一覧を取得する。admin scope 必須。

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

active model を変更する。admin scope 必須。`model_id` に `null` または空文字を
渡すと未設定に戻る。

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| コード | ステータス | 説明 |
|--------|-----------|------|
| `invalid_model_id` | 400 | model_id が長すぎる、または制御文字を含む |
| `unknown_model` | 400 | 指定 model のタグが DB に存在しない |

## POST /api/wd-tagger/batch

複数ファイルに対してバッチでタグ付けを実行。`file_ids` を指定した場合はそのファイルのみ、省略した場合は未タグ付けファイルを `limit` 件まで処理する。

### レート制限

HEAVY

### リクエスト

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| パラメータ | 型 | 必須 | 制限 | 説明 |
|-----------|------|------|------|------|
| `file_ids` | int[] | いいえ | 最大 500 件 | 対象ファイル ID の配列。省略時は未タグ付けファイルを自動選択 |
| `limit` | int | いいえ | - | `file_ids` 省略時の処理件数上限。デフォルト `100` |
| `force` | boolean | いいえ | - | `true` の場合、既存タグを上書き。デフォルト `false` |
| `scan_root` | string | いいえ | - | スキャンルートでフィルタ。空文字で全対象 |

### レスポンス

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `batch_too_large` | 400 | `file_ids` が 500 件を超えている |
| `batch_error` | 409 | バッチジョブが既に実行中 |

## POST /api/wd-tagger/batch/cancel

実行中のバッチタグ付けジョブをキャンセルする。

### レート制限

WRITE

### リクエスト

ボディ不要。

### レスポンス

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `job_not_running` | 404 | 実行中のバッチジョブが存在しない |

## GET /api/wd-tagger/stats

WD Tagger のタグ付け統計情報を取得。

### パラメータ

なし

### レスポンス

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `total_tagged` | int | タグ付け済みファイル数 |
| `total_tags` | int | 保存済みタグ総数 |
| `models` | object | モデル別のタグ付けファイル数 |
| `untagged_unknown` | int | メタデータなし (`unknown`) かつ未タグ付けのファイル数 |

## GET /api/wd-tagger/untagged

メタデータなし (`unknown`) かつ未タグ付けのファイル一覧を取得。ページネーション対応。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `limit` | int | いいえ | 取得件数。1-500、デフォルト `100` |
| `offset` | int | いいえ | スキップ件数。デフォルト `0` |

### レスポンス

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

指定ファイルの XMP メタデータを読み取る。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `file_id` | int | ファイル ID (パスパラメータ) |

### レスポンス

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `file_not_found` | 404 | ファイルが存在しないか論理削除済み |

## GET /api/wd-tagger/vlm/test

VLM (Vision Language Model) サーバーへの接続テストを実行。OpenAI 互換 API エンドポイントの到達性を確認する。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | VLM サーバーの URL (クエリパラメータ) |

### レスポンス

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `missing_url` | 400 | `url` パラメータが未指定 |
| `invalid_url` | 400 | URL の形式が不正 |

## GET /api/wd-tagger/vlm/models

VLM サーバーで利用可能なモデル一覧を取得。OpenAI 互換 `/v1/models` エンドポイントに問い合わせる。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | VLM サーバーの URL (クエリパラメータ) |

### レスポンス

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `missing_url` | 400 | `url` パラメータが未指定 |
| `invalid_url` | 400 | URL の形式が不正 |
| `vlm_connection_error` | 502 | VLM サーバーへの接続に失敗 |

## POST /api/wd-tagger/model/download

WD Tagger モデルをダウンロード。Hugging Face からモデルファイルを取得してローカルに保存する。

### レート制限

HEAVY

### リクエスト

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `repo` | string | いいえ | Hugging Face リポジトリ名。省略時は設定の `model` 値を使用 |

### レスポンス

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### エラー

| コード | ステータス | 説明 |
|--------|-----------|------|
| `unknown_model` | 400 | 未知のモデルリポジトリ。`hint` に既知モデル一覧が含まれる |
| `download_failed` | 500 | ダウンロードに失敗 |

## GET /api/wd-tagger/model/status

WD Tagger モデルのダウンロード状態を確認。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `repo` | string | いいえ | Hugging Face リポジトリ名 (クエリパラメータ)。省略時は設定の `model` 値を使用 |

### レスポンス

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (推奨)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `repo` | string | 確認対象のリポジトリ名 |
| `downloaded` | boolean | モデルがローカルにダウンロード済みかどうか |
| `path` | string/null | ダウンロード済みの場合、モデルのローカルパス |
| `known_models` | object | サポートされている全モデルの一覧 (リポジトリ名 -> 表示名) |

## User profile CRUD (v4.197.0+)

user 自作 tagger profile を Tools ページ UI から CRUD するための API。すべて admin scope 必須。共通 error shape は `{ok: false, error, code, ...extra}`。リクエスト body は **1MB hard cap** (`code: profile_too_large`、413)。`id` は `^[a-z0-9][a-z0-9_-]{0,63}$` regex 必須。

### POST /api/wd-tagger/profiles

新規 user profile を作成。

**リクエスト**: profile JSON (schema v2、`profile_version: "2"`)。`builtin` フィールドはサーバ側で `false` に強制上書きされる。

**レスポンス (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| フィールド | 説明 |
|---|---|
| `profile` | 保存された profile (`builtin: false` 確定) |
| `origin` | 常に `"user"` |
| `overrides_builtin` | 同 id の builtin profile が存在する場合 `true` (advanced 経路) |

**エラー**:

| status | code | 条件 |
|---|---|---|
| 400 | `validation_failed` | JSON が schema v2 違反 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | body の `id` が regex 不一致 |
| 409 | `id_conflict` | 既存 user profile と同 id |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

指定 id の full schema v2 profile を取得 (UI が編集 / 複製 / Export 時に呼ぶ)。

**path**: `id` (regex check 必須)

**レスポンス (200)**:
{POST と同形: profile / origin / overrides_builtin}

**エラー**:
- 400 `invalid_id` (path id regex 不一致)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

既存 user profile を更新。

**path**: `id` (regex check 必須)

**リクエスト**: profile JSON。`body.id` は path id と一致必須 (rename は `Duplicate → Delete` で UI 誘導)。

**レスポンス (200)**: POST と同形。

**エラー**:

| status | code | 条件 |
|---|---|---|
| 400 | `id_immutable` | path id と body id が不一致 |
| 400 | `invalid_id` | path id が regex 不一致 |
| 400 | `validation_failed` | schema 違反 |
| 403 | `builtin_read_only` | path id が builtin profile (user 側に該当ファイル無し) |
| 404 | `not_found` | id 未登録 |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

user profile を削除。

**path**: `id`

**レスポンス (200)**:
```json
{"ok": true, "deleted": true}
```

**エラー**:

| status | code | 条件 |
|---|---|---|
| 400 | `invalid_id` | path id 不正 |
| 403 | `builtin_read_only` | builtin のみで user override 無し |
| 404 | `not_found` | id 未登録 |
| 409 | `in_use` | 当該 profile が active model (`extra.active_model_id` 同梱)。UI 側で `PUT /api/wd-tagger/active-model` 経由で active 切替後 retry を促す |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download。各 `files[]` を HuggingFace に HEAD し、`required: true` のものは file 単位の atomic download を実行 (キャッシュは既存パス再利用)。

**path**: `id`

**body**: 不要

**動作**:
- per-file timeout: 30s
- 全体 timeout: 60s
- redirect: `huggingface.co` / `hf.co` サブドメイン allowlist のみ、最大 5 hop、userinfo (`user:pass@`) は SSRFBlocked

**レスポンス (200, 成功)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

`status` 値:
- `downloaded`: 今回ダウンロード完了
- `cached`: 既にローカルに存在 (HEAD のみ)
- `skipped_optional`: `required: false` で 404 / HEAD 失敗

**エラー (status / code)**:

| status | code | 条件 |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | path id 不正 / required ファイル HF 404 |
| 404 | `not_found` | profile 未登録 |
| 408 | `timeout` | 全体 60s 超過 |
| 502 | `ssrf_blocked` | redirect が HF allowlist 外 / userinfo 含む / scheme http(s) 以外 |
| 502 | `hf_unavailable` | HF が 5xx を返した |

エラー時 body は `{"ok": false, "code": ..., "error": ..., "files": [...部分結果...], "detail": "..."}` 形。

### profile JSON 形式 (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // HF repo path "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // user 由来は常に false (サーバが強制)
}
```

詳細は `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`)、または builtin の参考実装 (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`) を参照。

---

## Retag ジョブ API

モデルを切り替えてタグを付け直す（retag）ためのジョブ API。5 エンドポイントすべて `POST`、admin scope 必須。

### POST /api/wd-tagger/retag/single

1 ファイルを同期的に再タグ付けし、結果をそのまま返す。

**リクエスト**:

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `file_id` | int | ✓ | 対象ファイル ID |
| `model_id` | string | ✓ | 使用するモデル ID（profile の `id`） |
| `thresholds` | object | — | `{"general": 0.35, "character": 0.85}`（省略時デフォルト） |
| `overwrite_same_model` | bool | — | 同モデルの既存タグを上書き（デフォルト `true`） |
| `set_active` | bool | — | 完了後そのモデルをアクティブに設定（デフォルト `true`） |

**レスポンス**: `{"data": {タグ結果}}`

**エラー**: `404 file_not_found` / `400 invalid_input`

### POST /api/wd-tagger/retag/batch

複数ファイルを非同期でバッチ再タグ付け。

**リクエスト**:

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `model_id` | string | ✓ | 使用するモデル ID |
| `file_ids` | int[] | ✓ | 対象ファイル ID（最大 500） |
| `thresholds` | object | — | 閾値 |
| `batch_size` | int | — | 並列処理サイズ（1〜64、デフォルト 8） |
| `limit` | int | — | 処理件数上限（0=無制限） |
| `set_active` | bool | — | 完了後アクティブ設定（デフォルト `true`） |

### POST /api/wd-tagger/retag/backfill

スキャンルート単位で未タグ付けファイルを非同期再タグ付け。

**リクエスト**:

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `model_id` | string | ✓ | 使用するモデル ID |
| `scan_root` | string | — | スキャンルートパスでフィルタ（空=全対象） |
| `force` | bool | — | 既存タグがあっても再実行（デフォルト `false`） |
| `thresholds` | object | — | 閾値 |
| `batch_size` | int | — | 並列処理サイズ |
| `limit` | int | — | 処理件数上限 |

### POST /api/wd-tagger/retag/query

検索クエリで絞り込んだファイルを非同期再タグ付け。

**リクエスト**:

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `model_id` | string | ✓ | 使用するモデル ID |
| `query_params` | object | ✓ | `/api/search` と同じ検索パラメータ |
| `thresholds` | object | — | 閾値 |
| `batch_size` | int | — | 並列処理サイズ |
| `limit` | int | — | 処理件数上限 |

### POST /api/wd-tagger/retag/cancel

実行中の retag ジョブをキャンセル。

**レスポンス**: `{"data": {"status": "cancelling"}}`

**エラー**: `404 job_not_running`（実行中ジョブなし）
