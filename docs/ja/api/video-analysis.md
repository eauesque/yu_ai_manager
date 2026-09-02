# Video Analysis API

動画解析の設定管理とステータス確認に関する API。動画ファイルからキーフレームを抽出する機能の設定を制御する。

## GET /api/video-analysis/config

現在の動画解析設定を取得する。保存済みの設定とデフォルト値がマージされた結果を返す。

### パラメータ

なし

### レスポンス

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| フィールド | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `enabled` | boolean | `true` | 動画解析機能の有効/無効 |
| `keyframe_count` | int | `4` | 抽出するキーフレームの数 (1-16) |
| `strategy` | string | `"uniform"` | キーフレーム抽出戦略。`uniform` (均等間隔), `scene` (シーン変化検出), `single` (1フレームのみ) |
| `scene_threshold` | float | `0.4` | シーン変化検出の閾値 (0.0-1.0)。`strategy` が `scene` の場合に使用 |
| `store_per_keyframe` | boolean | `false` | キーフレームごとに個別保存するかどうか |

## POST /api/video-analysis/config

動画解析設定を保存する。指定したフィールドのみ更新され、省略されたフィールドは既存値が維持される。

### レート制限

WRITE

### リクエスト

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

全フィールドが省略可能。指定されたフィールドのみ更新される。

| パラメータ | 型 | 必須 | 制約 | 説明 |
|-----------|------|------|------|------|
| `enabled` | boolean | いいえ | - | 動画解析機能の有効/無効 |
| `keyframe_count` | int | いいえ | 1-16 | 抽出するキーフレームの数 |
| `strategy` | string | いいえ | `uniform`, `scene`, `single` のいずれか | キーフレーム抽出戦略 |
| `scene_threshold` | float | いいえ | 0.0-1.0 | シーン変化検出の閾値 |
| `store_per_keyframe` | boolean | いいえ | - | キーフレームごとに個別保存するかどうか |

### レスポンス

保存後のマージ済み設定を返す (GET と同じ形式)。

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### エラー

| ステータス | コード | 条件 |
|-----------|--------|------|
| 400 | `invalid_json` | リクエストボディが JSON オブジェクトでない |
| 400 | `invalid_value` | バリデーションエラー (型不正、範囲外の値、不正な strategy 等) |

## GET /api/video-analysis/status

動画解析のステータス情報を取得する。ffmpeg の利用可否、動画ファイル数、キーフレーム抽出済みファイル数を返す。

### パラメータ

なし

### レスポンス

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `ffmpeg` | boolean | ffmpeg がシステムで利用可能かどうか |
| `video_files` | int | DB 内の動画ファイルの総数 (論理削除済みを除く)。対象拡張子: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | キーフレームが抽出済みのファイル数 |
