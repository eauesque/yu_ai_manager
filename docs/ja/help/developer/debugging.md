# デバッグマニュアル

YU AI Manager のデバッグに必要な情報を網羅的にまとめたマニュアルです。
開発者や AI エージェントがバグの調査・修正を効率的に進めるための手引きとなります。

---

## 目次

1. [サーバー起動](#サーバー起動)
2. [デバッグログ](#デバッグログ)
3. [テスト実行](#テスト実行)
4. [DB デバッグ](#db-デバッグ)
5. [認証のバイパスとテスト](#認証のバイパスとテスト)
6. [MCP デバッグ](#mcp-デバッグ)
7. [フロントエンド デバッグ](#フロントエンド-デバッグ)
8. [環境変数一覧](#環境変数一覧)
9. [よくあるエラーと対処法](#よくあるエラーと対処法)
10. [パフォーマンス デバッグ](#パフォーマンス-デバッグ)

---

## サーバー起動

### 検証用（推奨）

PIN なし・ローカルバインドで起動します。テストやデバッグの基本形です。

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

`config_test.json` が存在しない場合は以下の内容で作成してください:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### 本番相当（LAN 公開）

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **注意**: `0.0.0.0` バインド時は PIN が必須です。v4.8.1 以降、LAN 公開時は `--debug` フラグが無視されます（スタックトレース漏洩防止）。

### ポート選択ルール

5100 → 5200 → 5300 → 以降 100 刻み。起動前に確認:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### CLI オプション一覧

| オプション | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `--db` | path | `data/tags.db` | SQLite DB ファイルパス |
| `--config` | path | `config.json` | 設定ファイルパス |
| `--host` | str | `127.0.0.1` | バインドアドレス |
| `--port` | int | 5000 | バインドポート |
| `--lan` | flag | - | `0.0.0.0` にバインド（LAN 公開） |
| `--pin` | str | - | PIN 認証を有効化 |
| `--debug` | flag | - | Quart デバッグモード有効化 |
| `--debug-log` | `on`/`off` | - | 構造化デバッグログの有効/無効 |
| `--debug-log-file` | path | `logs/debug.log` | ログファイル出力先 |
| `--debug-log-max-mb` | int | 10 | ログファイル回転サイズ（MB） |
| `--debug-log-backups` | int | 5 | ログバックアップ世代数 |
| `--debug-log-stdout` | `on`/`off` | `on` | ログを stderr にも出力 |
| `--allow-restart` | flag | - | `/api/server/restart` を有効化 |
| `--trusted-proxy-auth` | flag | - | Trusted Proxy 認証を有効化 |
| `--profile` | str | - | 起動プロファイル名 |

### launch-args.txt

プロジェクトルートに `launch-args.txt` を配置すると、記載された引数が起動時に自動読み込みされます。CLI 引数が優先されます。

---

## デバッグログ

### 有効化

```bash
# CLI で有効化
python web_ui.py --db ./tags.db --debug-log on

# 環境変数で有効化
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### ログ形式

構造化デバッグログ（`core/infra_core/debug_log.py` の `dlog()` 関数）:

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

形式: `[DEBUG] タイムスタンプ | ソース | イベント名 | key=value, ...`

### リアルタイム監視

```bash
# ファイルを tail
tail -f logs/debug.log

# API 経由で取得
curl http://127.0.0.1:5100/api/debug/logs

# SSE ストリーミング
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### ログリングバッファ

走行中のログはメモリ内リングバッファ（最大 1000 エントリ）にも保存されます。サーバー再起動で消えるため、永続化が必要な場合はファイルログを使ってください。

---

## テスト実行

### ユニットテスト

```bash
source venv/Scripts/activate

# 全テスト実行
python -m pytest tests/test_basic.py -v

# 特定テストのみ
python -m pytest tests/test_basic.py::TestImports -v

# 失敗で即停止
python -m pytest tests/test_basic.py -x
```

### API 統合テスト

```bash
python -m pytest tests/api/ -v
```

### Playwright ブラウザテスト

```bash
# 1. 検証サーバーを起動
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. テスト実行
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v

# クロス検索テスト
TARGET_URL=http://localhost:5100 python -m pytest tests/test_cross_search_browser.py -v
```

### テスト出力

- スクリーンショット: `screenshots/`
- レポート: `reports/`

### テスト方針

1. テストを先に実行して現状の失敗を把握する
2. 失敗したテストのスクリーンショットを確認する
3. 修正は最小限の変更に留める
4. 修正後に再テストして確認する

---

## DB デバッグ

### スキーマバージョン確認

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### DB 整合性チェック

```bash
python db_health.py --db ./tags.db
```

テーブル存在、スキーマバージョン、外部キー制約、インデックスをチェックします。

### SQL クエリのデバッグ実行

`YU_DEBUG_MODE=1` で起動した場合のみ使用可能です。

```bash
# API 経由
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **注意**: v4.8.1 以降、SELECT 文のみ許可されます。ATTACH, PRAGMA, INSERT 等は拒否されます。

### よく使う調査クエリ

```sql
-- ファイル数（ソース別）
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- モデル使用ランキング
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- 孤立タグ
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- 重複パス検出
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;

-- アノテーション概要
SELECT source, key, COUNT(*), AVG(confidence) FROM file_annotations GROUP BY source, key;
```

### DB 接続の使い分け

| 関数 | 用途 | 使う場面 |
|------|------|---------|
| `get_readonly_db()` | 読み取り専用 | GET API、検索、サムネイル参照、統計 |
| `get_db()` | 書き込み可（Row factory 付き） | POST/PUT/DELETE API |
| `get_raw_db()` | 書き込み可（Row factory なし） | バッチ処理、スキャン、マイグレーション |

> **重要**: 読み取り専用の API で `get_db()` を使うと、スキャン中にライトロック競合が発生してビューワーが数秒ブロックされます。必ず `get_readonly_db()` を使ってください。

---

## 認証のバイパスとテスト

### PIN 認証をスキップ

`config_test.json`（PIN 未設定）で起動すれば全認証がスキップされます。

### API Key テスト

```bash
# Bearer トークンで API リクエスト（CSRF ヘッダ不要）
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API Key のスコープ

v4.8.1 以降、スコープ未設定のキーは**読み取りのみ**許可されます。書き込み操作には明示的なスコープ付きキーが必要です。

| スコープ | 許可される操作 |
|---------|--------------|
| `read` | 検索、ファイル詳細、サムネイル、統計 |
| `rate` | レーティング設定/取得/バッチ |
| `tag.write` | タグ追加/削除 |
| `collection.write` | コレクション CRUD、お気に入り |
| `annotate` | アノテーション読み書き |
| `scan` | スキャン開始/中止/再開 |
| `admin` | API Key 管理、設定変更、バックアップ/復元 |

### 認証チェーン順序

```
static → /s/ (LAN Share) → /_pin → API Key Bearer
→ QuickLock → Trusted Proxy → session → cookie → PIN 画面表示
```

詳細: `core/web/auth_chain.py`

### curl で PIN 認証を通す

```bash
# 1. CSRF トークン取得
CSRF=$(curl -s -c cookies.txt http://127.0.0.1:5000/_pin | grep _csrf_token | sed 's/.*value="\([^"]*\)".*/\1/')

# 2. PIN 送信
curl -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:5000/_pin_check \
  -d "pin=1234&_csrf_token=$CSRF"

# 3. 認証済みリクエスト
curl -b cookies.txt http://127.0.0.1:5000/api/stats/all
```

---

## MCP デバッグ

### MCP サーバー起動

```bash
source venv/Scripts/activate
python -m mcp_server
```

### デバッグツールの有効化

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Claude Desktop 設定

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "<プロジェクトルート>",
      "env": {
        "YU_API_KEY": "sk_...",
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_DEBUG_MODE": "1"
      }
    }
  }
}
```

### MCP デバッグツール一覧

`YU_DEBUG_MODE=1` で 9 個のデバッグツールが追加登録されます:

| ツール | 用途 |
|--------|------|
| `debug_health_check` | サーバー・DB・テーブルの生存確認 |
| `debug_validate_counts` | API 統計と DB 実数の突合 |
| `debug_validate_search` | 検索 API のリグレッション検証 |
| `debug_validate_collection` | コレクション件数の内部整合性 |
| `debug_validate_annotations` | アノテーションテーブルの整合性 |
| `debug_sample_files` | ランダムサンプリングでフィールド分析 |
| `debug_roundtrip_test` | annotation/rating/tag の往復テスト |
| `debug_readonly_query` | 任意 SELECT クエリの実行 |
| `debug_full_report` | 全観察系ツール(1-5)の統合レポート |

### MCP インポート確認

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Extension セキュリティスキャン

YU AI Manager には Extension のコードスキャン機能が組み込まれています。スキャンは **Extension ロード時に自動実行** されるため、新しい Extension を追加・変更した場合はサーバーを再起動して一度読み込ませてください。

### 自動スキャンの仕組み

Extension のロード時に以下の検査が順番に実行されます:

```
1. ManifestAuthority.review()   — マニフェスト審査（形式・権限の妥当性）
2. CodeVerifier.verify()        — AST 静的解析（全 .py ファイルのコードスキャン）
3. ユーザー承認確認             — 権限の承認/拒否
4. Capability Token 発行        — 実行権限トークン
```

### CodeVerifier が検出するもの

| カテゴリ | 検出対象 | severity |
|---------|---------|----------|
| 危険モジュール | `subprocess`, `ctypes`, `importlib` | block |
| 直接 DB アクセス | `import sqlite3`（SandboxedDB を使うべき） | block |
| ネットワーク | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| 動的コード実行 | `eval()`, `exec()`, `__import__()`, `compile()` | block |

severity が `block` の場合、Extension のロードが拒否されます。

### スキャンの実行方法

**通常のフロー（推奨）:**

Extension を追加・変更したらサーバーを再起動します。ロード時にスキャンが自動実行され、結果がログに出力されます。

```bash
# サーバー再起動で Extension を再ロード（スキャンが自動実行される）
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**手動でスキャンだけ実行したい場合:**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# 結果確認
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### Trust Level

Extension は 3 段階の信頼レベルで分類されます:

| レベル | 条件 | 制約 |
|--------|------|------|
| L0 Trusted | `builtin-` プレフィックス | 制限なし |
| L1 Verified | 署名検証済み | 宣言済み権限のみ |
| L2 Untrusted | 手動インストール | 宣言済み権限 + ユーザー承認必須 |

### ランタイム保護

ロード後もランタイムで保護が継続します:

- **Import Guard**: `sys.meta_path` で未許可モジュールの import をブロック
- **Integrity Monitor**: 5 分間隔で SHA-256 ハッシュを比較し、ファイル改竄を検知
- **Token 自動失効**: 違反検出時に Capability Token を失効させて実行を停止

### 関連ドキュメント

| ドキュメント | 場所 |
|-------------|------|
| 三権分立セキュリティモデル | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| Sandbox 仕様 | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| Hook 仕様 | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## フロントエンド デバッグ

### TypeScript ビルド

```bash
pnpm run build        # esbuild でバンドル
pnpm run typecheck    # tsc --noEmit（型チェックのみ）
```

出力先: `ui/default/static/dist/`（gitignore 対象）

### エントリポイント構成

- 全ページ共通: `src/ts/nav/index.ts` → `static/dist/nav.js`
- ページ別: `src/ts/apps/*-app.ts` → `static/dist/*-app.js`

### CSRF インターセプター

`src/ts/nav/csrf-fetch.ts` がグローバル `fetch` を Proxy でラップし、全 POST/PUT/DELETE に `X-Requested-With` ヘッダを自動注入します。

```javascript
// ブラウザコンソールで確認
fetch('/api/stats/all').then(r => r.json()).then(console.log);
```

### SSE 共有エンジン

`window.EventSource` は Proxy で上書きされており、直接 `new EventSource()` するとエラーになります。

```javascript
// 正しい使い方
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// 誤り（ランタイムエラー）
// new EventSource('/api/events/...')
```

### i18n デバッグ

```javascript
// 言語切り替え
window.setLang('en');

// 翻訳キーの確認
console.log(window.tr('search.count.normal', { count: 5 }));
```

i18n ファイル: `ui/default/static/i18n/{lang}.json`

---

## 環境変数一覧

### デバッグ・ログ

| 変数 | 値 | デフォルト | 説明 |
|------|-----|----------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | 構造化デバッグログの有効/無効 |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | ログファイルパス |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | ログ回転サイズ（MB） |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | バックアップ世代数 |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | ログの stderr 出力 |

### サーバー

| 変数 | 値 | 説明 |
|------|-----|------|
| `TAGDB_DB` | path | DB ファイルパス |
| `TAGDB_CONFIG` | path | config.json パス |
| `TAGDB_PROFILE` | str | 起動プロファイル名 |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | 再起動 API の有効化 |

### MCP

| 変数 | 値 | 説明 |
|------|-----|------|
| `YU_DEBUG_MODE` | `1` | デバッグツール 9 個を追加登録 |
| `YU_BASE_URL` | URL | MCP クライアント用 BASE URL |
| `YU_API_KEY` | `sk_...` | MCP クライアント用 API Key |

---

## よくあるエラーと対処法

### サーバー起動

| エラー | 原因 | 対策 |
|--------|------|------|
| `Address already in use` | ポート占有 | `--port 5200` で別ポート指定 |
| `database is locked` | DB ロック競合 | DB がネットワークパス上にないか確認 |
| `--pin is required` | LAN バインドで PIN 未設定 | `--pin <digit>` で設定 |
| `ModuleNotFoundError` | venv 未有効化 or パッケージ不足 | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### 認証

| エラー | 原因 | 対策 |
|--------|------|------|
| PIN 画面が繰り返し表示 | Cookie 設定エラー | ブラウザの Cookie を確認（DevTools → Application） |
| `CSRF header missing` (403) | `X-Requested-With` ヘッダ不足 | fetch に `-H "X-Requested-With: XMLHttpRequest"` 追加 |
| API Key 拒否 | スコープ不足 | v4.8.1 以降、スコープなしキーは読み取りのみ。必要なスコープを付与 |

### DB

| エラー | 原因 | 対策 |
|--------|------|------|
| `no such table: schema_version` | 初回起動 | 自動生成されるので無視 |
| マイグレーション失敗 | スクリプトバグ | `db_health.py` で整合性確認 → 手動修正 |
| `SQLITE_BUSY` (タイムアウト) | 長時間トランザクション | 読み取り API が `get_db()` を使っていないか確認 |

### Windows 固有

| エラー | 原因 | 対策 |
|--------|------|------|
| `UnicodeEncodeError` (print 時) | cp932 で em dash 等が出力不可 | ASCII セーフな文字のみ使用 |
| `pkill` が効かない | Git Bash の制約 | `tasklist \| grep python` → `taskkill //F //PID <pid>` |
| `os.replace()` 失敗 | ファイルハンドルが開いている | プロセスを終了してリトライ |

### TypeScript

| エラー | 原因 | 対策 |
|--------|------|------|
| 変更が反映されない | ビルドしていない | `pnpm run build` |
| 型エラー | 型定義の不整合 | `pnpm run typecheck` で確認 |
| `EventSource` エラー | 直接 new した | `window.sseSubscribe()` を使用 |

---

## パフォーマンス デバッグ

### スキャン中のビューワーブロック

**症状**: スキャン中に画像の表示が 5-10 秒止まる

**原因**: 読み取り API が `get_db()`（書き込み可能接続）を使用していた

**対策**: 読み取り専用 API は必ず `get_readonly_db()` を使用する

### デバッグログで遅延検出

```bash
# 120 秒超のエントリを検索
grep "per-entry.*120" logs/debug.log

# スキャン中のブロック検出
grep "SQLITE_BUSY" logs/debug.log
```

### レートリミット確認

3 ティアのトークンバケット方式:

| ティア | 対象 | 制限 |
|--------|------|------|
| **HEAVY** | 類似検索、ハッシュ計算、AI 分析、スキャン | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, cache clear, config write | ~12 req/min (burst 3) |
| **WRITE** | その他の POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | 読み取り | 無制限 |

429 が返る場合は `Retry-After` ヘッダを確認してください。

---

## 関連ドキュメント

| ドキュメント | 場所 |
|-------------|------|
| DB 読み書き分離 | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| エラー形式統一 | `docs/development/development_docs/ERROR_HANDLING.md` |
| クロスプラットフォーム | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP デバッグツール仕様 | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Quart 移行ログ | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| QA 申し送り | `docs/development/development_docs/QA_HANDOFF.md` |
| セキュリティチェック | `/security-check` スキル |
