# OCR API

画像・動画・PDF からのテキスト抽出 (OCR)、翻訳、オーバーレイ画像生成、エクスポート、ベンチマーク、エンジン管理に関する API。

## POST /api/ocr/<file_id>

単一ファイルに対して OCR を実行し、結果を DB に保存する。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | OCR タスク種別。`ocr` / `ocr_document` / `ocr_manga` のいずれか。デフォルト: `ocr` |
| `language` | string | いいえ | 言語ヒント。デフォルト: `auto` |
| `server_id` | string | いいえ | 使用する分析サーバー ID。省略時は自動選択 |

### レスポンス (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "抽出されたテキスト...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### エラー

- `400` — 無効な task 値
- `404` — ファイルが見つからない
- `500` — OCR エンジンの解決に失敗 / OCR 実行エラー

---

## GET /api/ocr/result/<file_id>

保存済みの OCR 結果を取得する。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | タスク種別でフィルタ |
| `engine` | string | いいえ | エンジン名でフィルタ |
| `all` | string | いいえ | 任意の値を指定すると全結果を返す |

### レスポンス (結果あり)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "抽出されたテキスト...",
  "language": "ja",
  "regions": [...]
}
```

### レスポンス (`?all=1` 指定時)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### レスポンス (結果なし)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

保存済みの OCR 結果を削除する。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "",
  "engine": ""
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | タスク種別で絞り込み。空文字の場合は全タスク対象 |
| `engine` | string | いいえ | エンジン名で絞り込み。空文字の場合は全エンジン対象 |

### レスポンス

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

複数ファイルに対して一括 OCR を実行する。

### レート制限

WRITE

### リクエスト

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| パラメータ | 型 | 必須 | 制限 | 説明 |
|-----------|------|------|------|------|
| `file_ids` | int[] | はい | 最大 500 件 | 対象ファイル ID の配列 |
| `task` | string | いいえ | — | OCR タスク種別。`ocr` / `ocr_document` / `ocr_manga`。デフォルト: `ocr` |
| `language` | string | いいえ | — | 言語ヒント。デフォルト: `auto` |
| `server_id` | string | いいえ | — | 使用する分析サーバー ID |

### レスポンス (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### エラー

- `400` — `file_ids` が空 / 500 件超 / 無効な task 値
- `500` — OCR エンジンの解決に失敗

---

## POST /api/ocr/video/<file_id>

動画ファイルからキーフレームを抽出し、各フレームに対して OCR を実行する。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | OCR タスク種別。デフォルト: `ocr` |
| `language` | string | いいえ | 言語ヒント。デフォルト: `auto` |
| `server_id` | string | いいえ | 使用する分析サーバー ID |
| `keyframe_count` | int | いいえ | 抽出するキーフレーム数。1〜16。デフォルト: `4` |
| `strategy` | string | いいえ | キーフレーム抽出戦略。デフォルト: `uniform` |

### レスポンス (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "フレームから抽出されたテキスト...",
  "frame_count": 4,
  "row_id": 5
}
```

### エラー

- `400` — 動画ファイルではない
- `404` — ファイルが見つからない
- `500` — OCR エンジンの解決に失敗 / Video OCR 実行エラー

---

## POST /api/ocr/pdf/<file_id>

PDF ファイルのページを画像に変換し、OCR を実行する。テキストレイヤーのないスキャン PDF に有効。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | OCR タスク種別。デフォルト: `ocr_document` |
| `language` | string | いいえ | 言語ヒント。デフォルト: `auto` |
| `server_id` | string | いいえ | 使用する分析サーバー ID |
| `page_range` | string | いいえ | ページ範囲 (例: `"1-5"`, `"1,3,5"`)。空文字の場合は全ページ |
| `dpi` | int | いいえ | レンダリング解像度。72〜400。デフォルト: `200` |

### レスポンス (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "PDF から抽出されたテキスト...",
  "page_count": 10,
  "row_id": 6
}
```

### エラー

- `400` — PDF ファイルではない
- `404` — ファイルが見つからない
- `500` — OCR エンジンの解決に失敗 / PDF OCR 実行エラー

---

## POST /api/ocr/bbox/<file_id>

既存の OCR 結果に対してテキスト領域のバウンディングボックス (座標) 検出を実行する。OCR の第2パスとして使用し、位置情報を付加する。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "",
  "server_id": ""
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `task` | string | いいえ | 対象の OCR タスク種別 |
| `server_id` | string | いいえ | 使用する分析サーバー ID |

### レスポンス (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "テキスト領域",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### エラー

- `400` — テキスト領域がない / VLM エンジンが必要
- `404` — OCR 結果が見つからない (先に OCR を実行する必要あり) / ファイルが見つからない
- `500` — OCR エンジンの解決に失敗 / bbox 検出エラー

---

## GET /api/ocr/engines

利用可能な OCR エンジン (分析サーバー) の一覧を取得する。各エンジンのタスク別スコアも含まれる。

### パラメータ

なし

### レスポンス

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

NPU (Neural Processing Unit) デバイスの状態と推奨設定を取得する。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `task` | string | いいえ | 最適化推奨を取得するタスク種別。デフォルト: `ocr` |

### レスポンス

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

既存の OCR 結果を指定言語に翻訳する。翻訳結果は DB に保存される。

### レート制限

WRITE

### リクエスト

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `target_lang` | string | はい | 翻訳先言語コード (例: `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | いいえ | 使用する分析サーバー ID |
| `task` | string | いいえ | 対象の OCR タスク種別 |

### レスポンス (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "元のテキスト", "translated": "Original text" }
  ]
}
```

### エラー

- `400` — `target_lang` が未指定
- `404` — OCR 結果が見つからない
- `500` — 翻訳実行エラー

---

## GET /api/ocr/translations/<file_id>

ファイルに紐づく翻訳結果の一覧を取得する。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `target_lang` | string | いいえ | 言語コードでフィルタ |

### レスポンス

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

OCR 結果 (または翻訳結果) をオーバーレイした画像を生成して返す。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `mode` | string | いいえ | 表示モード。`translated` / `original` / `both`。デフォルト: `translated` |
| `target_lang` | string | いいえ | 翻訳言語でフィルタ |
| `format` | string | いいえ | 出力画像形式。`png` / `jpeg`。デフォルト: `png` |
| `task` | string | いいえ | 対象の OCR タスク種別 |

### レスポンス

- Content-Type: `image/png` または `image/jpeg`
- ファイル名: `ocr_overlay_{file_id}.{ext}`

### エラー

- `400` — 無効な mode / format 値
- `404` — OCR 結果が見つからない / ファイルが見つからない
- `500` — オーバーレイ画像生成エラー

---

## GET /api/ocr/export/<file_id>

OCR 結果を指定フォーマットでエクスポートしてダウンロードする。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | ファイル ID (パスパラメータ) |
| `format` | string | いいえ | エクスポート形式。`txt` / `md` / `json` / `pdf`。デフォルト: `md` |
| `task` | string | いいえ | 対象の OCR タスク種別 |
| `include_translation` | string | いいえ | 任意の値を指定すると翻訳を含める |
| `target_lang` | string | いいえ | 含める翻訳の言語コード |

### レスポンス

- Content-Type: フォーマットに応じた MIME タイプ
- Content-Disposition: `attachment; filename=...`

### エラー

- `400` — 無効な format 値
- `404` — OCR 結果が見つからない

---

## POST /api/ocr/export/batch

複数ファイルの OCR 結果を一括エクスポートする。ZIP ダウンロードまたはサーバーサイドへの直接保存が可能。

### レート制限

WRITE

### リクエスト

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_ids` | int[] | はい | 対象ファイル ID の配列 |
| `format` | string | いいえ | エクスポート形式。`txt` / `md` / `json` / `pdf` / `overlay`。Extension 設定からデフォルトを取得 |
| `output_dir` | string | いいえ | サーバーサイド保存先の絶対パス。省略時は ZIP ダウンロード |
| `overlay_mode` | string | いいえ | オーバーレイモード (`format=overlay` 時)。`translated` / `original` / `both`。デフォルト: `translated` |
| `target_lang` | string | いいえ | 翻訳言語コード |
| `include_translation` | bool | いいえ | 翻訳を含めるかどうか。デフォルト: `false` |

### レスポンス (ZIP ダウンロード)

- Content-Type: `application/zip`
- ファイル名: `ocr_export_batch.zip` (テキスト形式) または `ocr_overlay_batch.zip` (オーバーレイ形式)

### レスポンス (サーバーサイド保存)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### エラー

- `400` — `file_ids` が空 / 無効な format 値 / `output_dir` が絶対パスでない
- `403` — `output_dir` が禁止ディレクトリ
- `404` — OCR 結果が見つからない

---

## POST /api/ocr/benchmark

OCR ベンチマークを実行し、精度とパフォーマンスを計測する。ベンチマークケース (画像+正解テキストのペア) が必要。

### レート制限

WRITE

### リクエスト

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `task` | string | いいえ | ベンチマーク対象のタスク種別。デフォルト: `ocr` |
| `server_id` | string | いいえ | 使用する分析サーバー ID |
| `benchmark_dir` | string | いいえ | ベンチマークケースのディレクトリパス。省略時はデフォルトディレクトリ (`extensions/builtin_ocr/benchmarks/`) |

### レスポンス (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### エラー

- `404` — ベンチマークケースが見つからない
- `500` — OCR エンジンの解決に失敗 / ベンチマーク実行エラー

---

## GET /api/ocr/benchmark/cases

利用可能なベンチマークケースの一覧を取得する。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `dir` | string | いいえ | ベンチマークケースのディレクトリパス |

### レスポンス

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

OCR モデルプロファイル (タスク別スコア設定) の一覧を取得する。

### パラメータ

なし

### レスポンス

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

コミュニティ公開のモデルプロファイルを URL から取得し、ローカル設定にマージする。

### レート制限

WRITE

### リクエスト

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | プロファイル JSON の URL |

### レスポンス (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### エラー

- `400` — `url` が未指定
- `500` — 取得またはマージに失敗

---

## PUT /api/ocr/profiles/<model_prefix>

モデルプロファイルのスコアを手動で更新する。

### レート制限

WRITE

### リクエスト

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `model_prefix` | string | はい | モデル名プレフィックス (パスパラメータ) |
| `scores` | object | はい | タスク種別をキー、スコア (整数) を値とするオブジェクト |

### レスポンス

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### エラー

- `400` — `scores` が未指定
