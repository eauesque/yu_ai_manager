# YU AI Manager デバッグ命令書

## クイックスタート

```bash
# 全診断実行
python debug_check.py

# DB指定
python debug_check.py --db /path/to/tags.db

# 簡易チェック（構文/Extension省略）
python debug_check.py --quick
```

---

## よくある問題と対処

### 1. config.json が壊れた（バックスラッシュ問題）

**症状:** サーバー起動時に JSONDecodeError
**原因:** Windows パスの手動入力で `\U`, `\w` 等が不正エスケープになる
**対処:** サーバー起動で自動修復される。手動修復する場合:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all で特定フォルダがスキップされる

**症状:** 「全フォルダスキャン」で一部フォルダが処理されない
**確認手順:**
```bash
# scan_roots の中身を確認
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**チェック項目:**
- パスが短すぎないか（`\\wsl.localhost\` だけになっていないか）
- 末尾に `\` がないか
- `os.path.exists(path)` が True を返すか

### 3. QR共有が「内容がありません」

**症状:** QR共有ボタン → Positive/Negative が空
**原因候補:**
1. `templates` テーブルにレコードがない（meta_source=unknown）
2. API レスポンスのキーミスマッチ（v2.7.0 で修正済み）

**確認:**
```bash
# ファイルIDのテンプレート存在チェック
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # 問題のID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. WSL/UNC パスでスキャン失敗

**症状:** `\\wsl.localhost\...` パスでプローブ失敗
**確認:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**注意:** `pathlib.Path.exists()` は WSL UNC パスでバグがある。`os.path.exists()` を使う。

### 5. Extension が読み込まれない

**症状:** Extension 一覧に表示されない
**確認:**
```bash
python debug_check.py  # Extension チェックセクションを見る
```
**チェック項目:**
- `extension.json` or `extension.yml` が存在するか
- JSON/YAML が valid か（`safe_load_config` でチェック）
- `name` フィールドが存在するか

### 6. PIN 認証でロックアウトされた

**症状:** 5回失敗 → 60秒ロックアウト
**対処:** 60秒待つ。またはサーバー再起動でリセット。
**確認:** ブラウザの開発者ツール → Network → `/_pin_check` のレスポンスでエラーメッセージ確認

### 7. 500 エラーページの QR / Bundle バグ報告を確認したい

**症状:** ページ全体が 500 になり、専用エラーページが表示される  
**対象:** サーバー側未処理例外、HTML ページ全体の失敗

**最低限の確認項目:**
- 画面に QR コードが表示される
- `Bundle JSONをコピー` ボタンが表示される
- `Bundleをダウンロード (.json.gz)` ボタンが表示される
- QR を読んだ先の `docs/bugreport.html` で `AI Error Bundle` が見える

**確認手順:**
```bash
# まずサーバーを通常起動
venv\Scripts\python.exe web_ui.py
```

1. ブラウザで、意図的に 500 を起こすページ操作を行う  
2. 500 エラーページに QR と Bundle ボタンが出るか確認する  
3. `Bundle JSONをコピー` を押し、JSON に `schema`, `error_id`, `request`, `error`, `state` が入っているか見る  
4. `Bundleをダウンロード (.json.gz)` を押し、`err_*.json.gz` が保存できるか確認する  
5. QR をスマホ等で読むか、QR 文字列の URL を開いて `bugreport.html` に遷移する  
6. relay page 上で `AI Error Bundle` の全文が見えるか、GitHub Issue 生成時にその JSON が本文へ入るか確認する

**見るべきポイント:**
- `bundle.error.class` と `bundle.error.message` が空でないか
- `bundle.request.path` が実際の失敗 URL と一致しているか
- `bundle.error.frames` に失敗箇所の file/line/function が入っているか
- `bundle.state.server_info` と `bundle.state.extensions` が欠けていないか
- QR が長すぎる場合でも relay page で decode できるか

**切り分け:**
- QR は出るが relay page で decode 失敗する  
  `core/web/error_bundle.py` の pack/shrink と `docs/bugreport.html` の gzip decode を確認
- Copy/Download ボタンが出ない  
  `core/web/error_handlers.py` で `bundle_json` / `bundle_download_b64` が template に渡っているか確認
- ダウンロードだけ壊れる  
  `ui/default/templates/error.html` の base64 decode と `application/gzip` Blob 生成を確認

**関連ファイル:**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`
- `docs/bugreport.html`
- `docs/ja/features/qr-protocol-v1.md`

### 8. ページの一部だけ失敗する client error reporter を確認したい

**症状:** 画面全体は開くが、カード・セクション・API 読込だけ失敗する  
**対象:** `fetch` の 4xx/5xx、network error、`window.error`、`unhandledrejection`、tools page loader failure

**最低限の確認項目:**
- 右下に error reporter launcher が出る
- launcher から modal を開ける
- modal で `Copy JSON` / `Download .json.gz` / `GitHub Issue` が使える
- bundle に `X-Request-Id` と `ui_events` が入る

**確認手順:**
1. `apiFetch` を使う画面を開く  
2. 意図的に 500 を返す API、または存在しない API を叩く操作を行う  
3. 右下 launcher が出るか確認する  
4. modal を開いて bundle JSON を確認する  
5. `request.status`, `request.url`, `request.request_id`, `repro.ui_events` が入っているか見る  
6. `Download .json.gz` を押し、圧縮 bundle を保存できるか確認する

**開発者ツールでの確認:**
- Network タブで失敗した API の response header に `X-Request-Id` があるか
- Console に未処理例外が出ている場合、launcher 側 bundle に同じエラー内容が入っているか
- `/api/error-report/enrich` が 200 で返り、補完後 bundle に `state.server_info` や `artifacts.recent_logs` が入っているか

**簡易再現の例:**
- tools page の loader 内でわざと例外を投げる
- `apiFetch('/api/not-found-for-debug')` のような存在しない endpoint を一時的に叩く
- server 側で対象 route を一時的に `api_error(...)` や例外送出へ差し替える

**切り分け:**
- 失敗しているのに launcher が出ない  
  `src/ts/main/api-utils.ts` か `src/ts/shared/error-reporter.ts` を確認。共通 `apiFetch` を通っていない可能性が高い
- bundle に `request_id` が無い  
  `core/web/request_hooks.py` で `X-Request-Id` が全応答に付いているか確認
- enrich 後も server 情報が空  
  `routes/server_info.py` の `/api/error-report/enrich` と `core/web/error_bundle.py` の `enrich_error_bundle()` を確認
- tools page の一部失敗だけ拾えない  
  `src/ts/tools-page/index.ts` 側の `captureThrownError(...)` 呼び出しを確認

**関連ファイル:**
- `src/ts/shared/error-reporter.ts`
- `src/ts/main/api-utils.ts`
- `src/ts/tools-page/index.ts`
- `src/ts/nav/index.ts`
- `core/web/request_hooks.py`
- `routes/server_info.py`
- `core/web/error_bundle.py`

---

## デバッグログの読み方

### サーバーコンソール出力

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → config.json のバックスラッシュ自動修復が実行された

[DEBUG] scan/start: raw=..., sanitized=...
  → スキャン開始時のパス（生値 → サニタイズ後）

[DEBUG] scan-all root 0: repr=..., len=...
  → 全フォルダスキャン時の各ルートパス詳細

[Scan] Auto-registered scan root: /path/to/dir
  → スキャン成功時の自動登録

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR共有API: ファイルは存在するがテンプレートがない

[ERROR] file.json: JSON parse failed: ...
  → safe_load_json でのパースエラー（アプリは落ちない）
```

---

## ファイル構成とデバッグ対象

```
web_ui.py          ← エントリポイント（サーバー起動）
core/
  config.py        ← 設定管理、safe_load_*
  server.py        ← PIN認証、QuickLock
  scanner.py       ← スキャンエンジン
  extensions.py    ← Extension読み込み
  db.py            ← DB接続管理
  schema.py        ← テーブル定義
routes/
  scan.py          ← スキャンAPI
  search.py        ← 検索API
  share.py         ← QR共有API
  tools.py         ← ツールAPI + Inspect API
  debug.py         ← デバッグAPI
  pages.py         ← ページルーティング
  server_info.py   ← server-info / error-report enrich API
core/web/
  error_handlers.py ← 500エラーページ + QR バグレポート生成
  error_bundle.py   ← error bundle 生成 / 縮約 / enrich
  request_hooks.py  ← X-Request-Id 付与
ui/default/templates/
  error.html       ← 500 エラーページの Copy / Download UI
static/js/
  main.js          ← メインUI（検索、モーダル、QR、キーボード）
  scan-banner.js   ← スキャン進捗 + スクロールトップ（全ページ）
src/ts/shared/
  error-reporter.ts ← 部分失敗向け client-side error reporter
```
