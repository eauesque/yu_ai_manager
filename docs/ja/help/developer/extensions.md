# 拡張機能

YU AI Manager は Extension システムで機能を追加できます。
現在 43 のビルトイン Extension が搭載されており、6 つのカテゴリに分類されています。

## ビルトイン Extension 一覧

### メタデータ抽出 (metadata)

| Extension | 説明 |
|-----------|------|
| builtin-a1111 | Automatic1111 / SD WebUI の PNG/WebP/WebM メタデータ抽出 |
| builtin-novelai-v3 | NovelAI V3 以前のメタデータ抽出 |
| builtin-novelai-v4 | NovelAI V4 メタデータ抽出（Character Prompts, Vibe Transfer 対応） |
| builtin-comfyui | ComfyUI ワークフロー JSON 解析 |
| builtin-annotations | ファイルアノテーションの保存・検索・一括操作 |
| builtin-ratings | 星評価システム（1〜5 星） |
| builtin-tag-dictionary | Danbooru タグ辞書の検索・インポート・分割 |

### Bridge 連携 (bridge)

| Extension | 説明 |
|-----------|------|
| builtin-sd-webui-bridge | SD WebUI / Forge 連携（画像生成・モデル管理） |
| builtin-nai-bridge | NovelAI API 連携（画像生成） |
| builtin-comfyui-bridge | ComfyUI 連携（ワークフロー実行） |

### プロンプト (prompt)

| Extension | 説明 |
|-----------|------|
| builtin-prompt-library | プロンプトライブラリ・整理 |
| builtin-prompt-syntax | プロンプト構文ハイライト・エラー検出（NAI/SD/DP 対応） |
| builtin-prompt-simulator | Dynamic Prompts シミュレーター・重み計算・変換 |
| builtin-sd-nai-convert | SD ↔ NovelAI プロンプト相互変換 |

### AI (ai)

| Extension | 説明 |
|-----------|------|
| builtin-analysis | AI 画像分析（Claude, OpenAI, Ollama, Hailo VLM） |
| builtin-wd-tagger | WD-Tagger 自動タグ付け（ONNX + VLM エンジン） |
| builtin-ocr | VLM OCR — テキスト抽出・構造化解析・翻訳 |
| builtin-clip-search | CLIP セマンティック画像検索エンジン |
| builtin-clip-onnx | CLIP ONNX Runtime エンコーダバックエンド |
| builtin-clip-coreml | CLIP Core ML エンコーダ（Apple Neural Engine） |
| builtin-hailo-semantic-search | Hailo-10H セマンティック検索 |
| builtin-hailo-yolo-detect | Hailo-10H YOLO オブジェクト検出 |
| builtin-hailo-genai | Hailo-10H GenAI（LLM/VLM/S2T） |
| builtin-speech-to-text | 音声テキスト化（Hailo NPU / CUDA / ROCm / CPU） |
| builtin-audio-analysis | 音声分析（Whisper ローカル / OpenAI API） |
| builtin-video-analysis | 動画 AI 分析（マルチキーフレーム + Gemini） |
| builtin-inference | ONNX Runtime プロバイダ検出・GPU アクセラレーション |

### ライブラリ (library)

| Extension | 説明 |
|-----------|------|
| builtin-favorites-manager | お気に入り・コレクション管理 |
| builtin-freeze-pullback | Freeze & Pull-back ビデオ生成（Ken Burns エフェクト） |
| builtin-download | 選択画像の一括 ZIP ダウンロード |
| builtin-chatlog | チャットログインポーター・ビューワー（Claude / ChatGPT） |
| builtin-md-viewer | Markdown ファイルビューワー（FTS5 全文検索） |
| builtin-cross-search | クロス検索（MD, チャットログ, プロンプト, テキスト横断） |
| builtin-lan-share | LAN コレクション共有（時間制限トークン認証） |
| builtin-stats | 統計インサイト（タイムライン、マイルストーン） |
| builtin-trophy | トロフィー・実績システム |
| builtin-export | エクスポートフック（CSV 出力時のレコード変換） |

### システム (system)

| Extension | 説明 |
|-----------|------|
| builtin-auto-scan-watcher | ファイル変動の自動検知・差分更新 |
| builtin-mcp-client | 外部 MCP サーバー接続管理 |
| builtin-backup | DB バックアップ・リストア・スケジューラ |
| builtin-sns-share | SNS 共有（Bluesky, X/Twitter） |
| builtin-webhook | Webhook ディスパッチャー（イベント駆動 HTTP 配信） |
| builtin-debug-check | デバッグ診断 CLI |
| builtin-github-integration | GitHub Issue 監視・トリアージ・PR/Discussion/Release 追跡 |

## Extension の管理

Settings > Extensions タブで以下の操作が可能です:

- **有効/無効切替**: トグルスイッチで即座に切替
- **新規インストール**: Git リポジトリ URL を指定してインストール
- **Marketplace**: 公開 Extension の検索・ワンクリックインストール
- **更新**: Git ベースの Extension を最新版に更新
- **アンインストール**: サードパーティ Extension の削除

### API による管理

```bash
# Extension 一覧
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# 有効/無効切替
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Git からインストール
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

サードパーティ Extension はサンドボックスで保護されます。

### 信頼レベル

| レベル | 対象 | 制限 |
|--------|------|------|
| L0 (TRUSTED) | `builtin-*` | 制限なし |
| L2 (UNTRUSTED) | その他 | DB/FS/ネットワーク制限あり |

### サンドボックスの 4 フェーズ

1. **Capability Token**: HMAC-SHA256 署名付きトークンで権限を管理。24 時間有効期限
2. **SandboxedDB / SandboxedFS**: `db:read` のみの Extension は SELECT のみ許可。ファイルアクセスはパスベースで制御
3. **SandboxedHTTPClient / ImportGuard**: SSRF 防止、ランタイム import 監視、SHA-256 改竄検知
4. **プロセス隔離 (Linux)**: L2 Extension を別プロセスで実行。Unix socket JSON-RPC 2.0 IPC

### OS レベル隔離（オプション）

- **Linux**: AppArmor プロファイル自動生成
- **macOS**: sandbox-exec（実験的）
- **Windows**: Restricted Token + Job Object

> **Tip**: Extension 開発の詳細は「Extension 開発」セクションを参照してください。

## ディレクトリ構成

```
extensions/builtin_<name>/
  extension.json            # マニフェスト（名前、バージョン、権限等）
  <name>_ext.py             # エントリポイント（get_blueprint() を公開）
  templates/<name>/          # Jinja2 テンプレート
  core_impl/                 # ビジネスロジック（任意）
```

### extension.json の必須フィールド

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

カテゴリは `metadata`, `bridge`, `prompt`, `ai`, `library`, `system` の 6 種類です。

## Extension Module API v2（ES Module 対応）

v4.29.0 以降、Extension は `<script type="module">` と Import Maps を使った ES Module パターンで記述できます。

### 有効化方法

`extension.json` に `"script_type": "module"` を追加します：

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### 使い方

テンプレートの `<script>` を `<script type="module">` に変更し、`yu-api` から import します：

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast 通知
showToast('保存しました');

// SSE イベント購読
sseSubscribe('scan.progress', (data) => {
  console.log('進捗:', data);
});

// i18n 翻訳
const label = tr('my_ext.title', 'My Extension');

// API 呼び出し（CSRF ヘッダ自動付与）
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### 公開 API 一覧

| 関数 | 説明 |
|---|---|
| `showToast(message, isError?)` | トースト通知を表示 |
| `sseSubscribe(eventType, handler)` | SSE イベントを購読 |
| `sseUnsubscribe(eventType, handler)` | SSE イベント購読を解除 |
| `tr(path, a?, b?)` | i18n 翻訳キーを解決 |
| `apiFetch(path, opts?)` | CSRF 付き fetch ラッパー |
| `apiUrl(path)` | API URL を構築 |
| `escapeHtml(text)` | HTML 特殊文字をエスケープ |

### TypeScript 型定義

`src/ts/extension-api/extension-api.d.ts` を Extension プロジェクトにコピーすると、IDE の補完・型チェックが有効になります。

### レガシー互換

`"script_type": "classic"`（既定値）の Extension は従来通り `window.showToast()` 等のグローバル関数を使えます。既存 Extension の書き換えは不要です。

## 開発ドキュメント

Extension 開発やシステム内部の設計判断・既知の注意点・デバッグ Tips などの開発知見は [MD Viewer](/ext/md-viewer/) で閲覧できます。`docs/development/development_docs/` が登録済みで、FTS5 全文検索にも対応しています。
