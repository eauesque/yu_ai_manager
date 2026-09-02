# 検索

## 基本検索

検索バーにタグをカンマ区切りで入力します。

```
1girl, blue_eyes, school_uniform
```

## 検索フィルタ

| フィルタ | 説明 |
|---------|------|
| 日付範囲 | 開始日〜終了日で絞り込み |
| ファイル形式 | PNG / WebP / JPG / GIF |
| 評価 | 星1〜5で絞り込み |
| お気に入り | お気に入り登録済みのみ表示 |
| コレクション | 特定コレクション内のみ表示 |

## プロンプト内検索

「in_prompt」フィールドを使うと、画像のプロンプトテキスト内を全文検索できます。
FTS (Full-Text Search) が有効な場合、高速に検索できます。

## ソート順

| ソート | 説明 |
|--------|------|
| date | 登録日（新しい順） |
| date_old | 登録日（古い順） |
| folder | フォルダ順 |
| path | パス順 |
| random | ランダム |
| rating_desc | 評価（高い順） |
| rating_asc | 評価（低い順） |

## セマンティック検索

Hailo-10H または ONNX CLIP モデルが設定されている場合、自然言語で画像を検索できます。
検索バーの右にあるセマンティック検索ボタンを使用してください。

### FAISS による高速化（推奨）

セマンティック検索はデフォルトで NumPy によるブルートフォース検索を使用しますが、
**FAISS をインストールすると大幅に高速化**されます。

| ライブラリ数 | NumPy (デフォルト) | FAISS (推奨) |
|-------------|-------------------|-------------|
| 1万件以下 | 数十ms | 数ms |
| 10万件 | 1〜3秒 | 数十ms |
| 100万件以上 | 10秒以上 | 100ms以下 |

FAISS は検索対象の規模に応じて自動的に最適なインデックスを選択します:
- **5万件未満**: IndexFlatIP（正確な全探索、十分高速）
- **5万件以上**: IndexIVFFlat（近似最近傍探索、大規模でも高速）

#### インストール方法

```bash
# venv を有効化してからインストール
source venv/bin/activate

# x86_64 (Intel/AMD) — pip で直接インストール可能
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — pip で入らない場合
# 方法1: conda 経由
conda install -c conda-forge faiss-cpu

# 方法2: ソースからビルド
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

インストール後はサーバーを再起動するだけで自動検出されます。
起動ログに以下が表示されれば FAISS が有効化されています:

```
FAISS x.x.x detected — using accelerated vector search
```

FAISS がインストールされていない場合でも、従来通り NumPy で動作します。
