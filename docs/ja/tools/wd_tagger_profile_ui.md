# WD-Tagger プロファイル UI 操作ガイド

このドキュメントは、WD-Tagger の「プロファイル管理 UI」（v4.197.0+）の使い方を説明します。

## 1. 概要

- WD-Tagger で使う「モデル設定・ファイル構成・タグ定義・閾値定義・前処理」を 1 つの **プロファイル**として管理できます。
- Tools ページの **WD-Tagger** セクションから `プロファイルを管理...`（`Manage profiles...`）を押すと、モーダルで開きます。
- モーダル内は **一覧画面（List）** と **フォーム画面（Form）** を行き来します。

## 2. 一覧画面（List）

### 2.1 バッジ（Builtin / User）

- `builtin` バッジ: 組み込みプロファイル（読み取り専用）
- `user` バッジ: ユーザープロファイル（作成・編集・削除が可能）
- `↻` 表示: 同じ `id` の組み込みプロファイルを **上書き**していることを示します

### 2.2 フィルタ（All / User / Builtin）

上部のフィルタで表示対象を絞り込みます。

- `すべて`（All）
- `ユーザー`（User）
- `組み込み`（Builtin）

### 2.3 ボタン（操作）

各行の右側に、次のボタンがあります。

- `複製`（Duplicate）: 選択したプロファイルをコピーしてフォームを開きます（builtin を編集したい場合はこれを使用）
- `編集`（Edit）: user プロファイルを編集します（builtin は編集不可）
- `削除`（Delete）: user プロファイルを削除します（builtin は削除不可）
- `エクスポート`（Export）: そのプロファイルを `.json` としてダウンロードします
- `テスト (dry-run download)`（Test）: **実ダウンロードを行わず**、必要ファイルを HuggingFace から取得できるかを確認します

右上のボタン:

- `+ 新規`（+ New）: 空の新規プロファイルを作成します
- `インポート`（Import）: 既存 JSON からプロファイルを作成します（Upload / Paste）

## 3. フォーム画面（Form）

フォームは 5 つのアコーディオン（accordion）で構成されます。

### 3.1 Metadata

- `id`: プロファイルの識別子（後から変更できません）
- `表示名`: 一覧に表示される名前
- `profile_version`: プロファイルのスキーマ版（通常はそのままで OK）

### 3.2 Model & Files

- `model_id`: HuggingFace 上のモデル ID（例: `SmilingWolf/wd-swinv2-tagger-v3`）
- `adapter_family`: アダプタ（互換）ファミリー（必要な場合のみ）
- `backend`: バックエンド指定（必要な場合のみ）
- `hf_subdir`: HuggingFace リポジトリ内のサブディレクトリ（必要な場合のみ）
- `ファイル`:
  - `name`: ダウンロード対象ファイル名（例: `model.onnx`）
  - `必須`: チェックすると Test 時に存在必須として扱われます
  - `size_hint_mb`: サイズの目安（任意）
  - `+ ファイル追加` / `削除`: 行の追加・削除

### 3.3 Tag source

タグ定義をどのファイル（または構成）から読み込むかを指定します。

- `csv`: CSV から読み込み
  - `ファイル (file)`: files の中から参照するファイルを選択
  - `区切り文字 (delimiter)`: 例: `,`
  - `タグ列 (name_col)`: タグ名が入る列名
  - `カテゴリ列 (category_col)`: カテゴリが入る列名（任意）
  - `カテゴリ変換 (category_map)`: カテゴリ名→正規化名の変換（任意）
- `json_list`: JSON 配列から読み込み
  - `ファイル (file)`
  - `スキーマ (schema)`: 配列要素のスキーマ指定（必要な場合のみ）
- `json_dict`: JSON の辞書（map）から読み込み
  - `ファイル (file)`
  - `マッピング (mapping)`: キー/値の意味づけ（必要な場合のみ）
- `composite`: 複数ソースを合成
  - `ソース (sources)`: どのソースをどう合成するか

### 3.4 Threshold source

カテゴリ別の閾値をどこから読むかを指定します。

- `global_per_category`: 画面内でカテゴリ別に直接指定（`一般` / `キャラクター` / `著作権` / `作者` / `メタ`）
- `per_tag`: ファイル参照 + フォールバック指定
  - `ファイル (file)`: per-tag 閾値ファイル
  - `フォールバックモード (fallback.mode)`: `global` / `category_default`
  - `フォールバック値 (fallback.value)`: 参照できない時の既定値

### 3.5 Preprocess & Categories

前処理パラメータとカテゴリ関連の設定です。

- 前処理（`preprocess_spec`）:
  - `input_size`: 入力解像度
  - `dtype`: 入力 dtype
  - `layout`: レイアウト
  - `channel_order`: チャンネル順
  - `resize_strategy`: `letterbox` / `longest_side_pad` / `stretch`
  - `scale`: スケール
  - `mean` / `std`: 正規化パラメータ（3 要素）
- カテゴリ:
  - `対応カテゴリ`: どのカテゴリを有効にするか
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 Import（インポート）

`インポート` を押すと、次の 2 タブが表示されます。

- `JSON をアップロード`: `.json` ファイルを選択して取り込み
- `JSON を貼り付け`: テキストエリアに JSON を貼り付けて取り込み

取り込み後はフォーム画面が開き、必要に応じて修正してから `保存` します。

### 4.2 Export（エクスポート）

一覧の `エクスポート` で、対象プロファイルを JSON としてダウンロードします。

## 5. Test（dry-run download）

- `テスト (dry-run download)` は、プロファイルの `files` に記載されたファイルが **HuggingFace から取得可能か**を検証します。
- 成功時はバナーに `全 {n} ファイル ({total} MB) ダウンロード OK` のようなメッセージが表示されます。
- 失敗時はバナーにエラーが表示され、原因に応じて内容が変わります（次章参照）。

## 6. よくあるエラー（短い説明）

- `id_conflict`: 同じ `id` の user プロファイルが既に存在します
- `id_immutable`: `id` は変更できません（リネームは Duplicate → Delete）
- `in_use`: そのプロファイルが現在アクティブのため削除できません
- `validation_failed`: 入力 JSON / フォーム値がスキーマ検証に通りません（`{detail}` に詳細）
- `profile_too_large`: インポートした JSON が大きすぎます（上限 1MB）
- `ssrf_blocked`: HuggingFace 以外への redirect が拒否されました（SSRF 対策）
- `hf_unavailable`: HuggingFace に接続できない、または応答が不正です
- `timeout`: 取得がタイムアウトしました（60s）
- `required_missing`: 必須ファイルが見つかりません（`required` が付いたファイル）

## 7. 制限事項（重要）

- `builtin` は **編集/削除不可**です。変更したい場合は `複製` して user として保存してください。
- `id` は **immutable（変更不可）**です。リネームしたい場合は `複製` → `削除` を使います。
- Import できるプロファイル JSON は **最大 1MB** です。
- Test（dry-run download）は SSRF 対策のため、HuggingFace の allowlist のみ許可されます:
  - `huggingface.co`
  - `hf.co`
