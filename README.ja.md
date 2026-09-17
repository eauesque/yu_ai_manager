# YU AI Manager

AI 生成画像のメタデータ管理 WebUI。

## 概要

AI 生成画像に埋め込まれたメタデータ（プロンプト・モデル・シード等）を抽出・検索・管理する WebUI ツールです。

**こんなことができます:**

- フォルダや ZIP アーカイブを丸ごとスキャンして画像を自動登録
- プロンプト・タグ・モデル名・シード値などで横断検索・絞り込み
- 気に入った画像を SD / ComfyUI / NovelAI に即送信して再生成
- WD-Tagger で自動タグ付け、Ollama/OpenAI で内容を分析
- LAN 上の別デバイス（スマホ等）から QR コードでアクセス

**対応ソース**: Stable Diffusion (A1111/Forge)、NovelAI V3/V4、ComfyUI

## 動作環境

- Windows / Linux / macOS

> **手動インストール不要。** `start.sh` / `start.bat` が必要なツールをすべてプロジェクト配下に bootstrap します（システムへの書き込み・管理者権限なし）。

## セットアップ・起動

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

初回起動時の自動セットアップ:

| ツール | 入手方法 |
| --- | --- |
| `uv` | `./bin/uv` に自動 DL |
| Python 3.11+ | `uv` が自動インストール |
| Node.js 22 LTS | 任意 — `./bin/node/` への DL を確認（約 30 MB） |
| pnpm | Node.js が入った時点で `corepack` 経由で有効化 |
| ffmpeg | 任意 — Windows/macOS は `./bin/ffmpeg/` への DL を確認（約 80 MB）、Linux は distro の `apt`/`dnf`/`pacman` コマンドを案内 |

`YU_AUTO_INSTALL=1` を設定すると非対話環境（CI 等）でもプロンプトをスキップして全自動インストールします。ffmpeg は動画分析・S2T・OCR 等の拡張機能専用なので、本体起動には不要です。

2 回目以降は依存関係や TypeScript ソースが更新されたときのみ再インストール・再ビルドします。

`launch-args.txt` に `--db`, `--port`, `--lan`, `--pin` 等を記載すれば永続設定できます。

## 主な機能

### スキャン・登録
- PNG / WebP / JPEG のメタデータ自動抽出
- ZIP / 7z アーカイブを展開せずに透過スキャン
- ドラッグ＆ドロップでファイル追加

### 検索・閲覧
- プロンプト・タグ・モデル名・シード値の全文検索
- 正規表現検索、複合条件フィルタ
- pHash 類似画像検索、CLIP セマンティック検索

### 整理・管理
- お気に入り、星レーティング（1〜5）、メモ（アノテーション）
- コレクション（グループ分け）
- 統計ダッシュボード・月次レポート・トロフィーシステム

### 生成ツール連携（Bridge）
- SD WebUI / Forge / ComfyUI / NovelAI へのプロンプト即送信
- クリップボード経由の送信にも対応

### AI 補助
- WD-Tagger による自動タグ付け
- Ollama / OpenAI を使った画像内容分析
- 音声テキスト変換（S2T）

### ネットワーク・共有
- LAN 共有モード（QR コードでスマホからアクセス）
- MCP サーバー（AI エージェントから操作）
- Fleet 管理（複数インスタンスの一元管理）

### カスタマイズ
- カスタム UI・Extension システム
- テーマ対応（ライト / ダーク）
- Tauri デスクトップアプリ（ブラウザ不要で起動）

## 多言語対応

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## ドキュメント

- [クイックスタート](docs/ja/help/user/quickstart.md)
- [ユースケース集](docs/ja/help/user/use-cases.md)
- [API リファレンス](docs/ja/api/README.md)
- [パフォーマンス調整](docs/ja/help/user/performance-tuning.md)
- [デプロイメント](docs/ja/help/user/deployment.md)
- [Extension 開発](docs/ja/plugin-development/getting-started.md)
- [カスタム UI](docs/ja/custom-ui/README.md)
- [MCP ツール](docs/ja/api/MCP_TOOLS_REFERENCE.md)
- [全ドキュメント一覧](docs/ja/README.md)

## 開発・カスタマイズ

[DEVELOPMENT.ja.md](DEVELOPMENT.ja.md) を参照 ([English](DEVELOPMENT.en.md))

## 困ったときは AI に聞く

### 起動しない場合

Claude Code Desktop などの AI エージェントに、このプロジェクトのフォルダを作業ディレクトリとして開いた上で、次のように伝えてください:

> `start.bat`（または `start.sh`）を起動させても止まります。調べてください。

> **補足**: Claude Code Desktop では、会話を始める前にプロジェクトフォルダを指定しておく必要があります。

### 起動後の問題・設定・使い方

**ステップ 1 — コンテキストを取得する**

ヘルプページ（`/help`）を開き、**「AI コンテキストをコピー」** ボタンを押してください。
ログイン済みブラウザセッションを使って `GET /api/ai-context` を fetch し、JSON をクリップボードにコピーします（http:// LAN 環境でも動作）。

> **補足（API キーをお持ちの場合）**: admin スコープの API キーがあれば `Authorization: Bearer <key>` ヘッダを付けて直接 `GET /api/ai-context` を呼ぶことができます。

**ステップ 2 — AI に渡す**

コピーした JSON を AI チャットに貼り付け、続けて質問を書いてください:

> 〔貼り付けた JSON〕
> これを踏まえて、〔問題の説明〕を解決してください。

`/api/ai-context` には現在のバージョン・有効機能・設定ヒント・API 一覧・CSRF ルールが含まれており、AI が正確に支援するために必要な情報が揃っています。

## FAQ

[docs/ja/FAQ.md](docs/ja/FAQ.md) ([English](docs/en/FAQ.md))

## バグ報告

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## ライセンス

MIT License — [LICENSE](LICENSE) / [口語訳](docs/ja/LICENSE.md) ([English](docs/en/LICENSE.md))
