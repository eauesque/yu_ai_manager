# 🔬 YU AI Manager デバッグ命令書

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

**症状:** サーバー起動時にJSONDecodeError
**原因:** Windowsパスの手動入力で `\U`, `\w` 等が不正エスケープになる
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
2. APIレスポンスのキーミスマッチ（v2.7.0で修正済み）

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

### 4. WSL/UNCパスでスキャン失敗

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
**注意:** `pathlib.Path.exists()` はWSL UNCパスでバグがある。`os.path.exists()` を使う。

### 5. Extension が読み込まれない

**症状:** Extension一覧に表示されない
**確認:**
```bash
python debug_check.py  # Extension チェックセクションを見る
```
**チェック項目:**
- `extension.json` or `extension.yml` が存在するか
- JSON/YAMLが valid か（`safe_load_config` でチェック）
- `name` フィールドが存在するか

### 6. PIN認証でロックアウトされた

**症状:** 5回失敗 → 60秒ロックアウト
**対処:** 60秒待つ。または サーバー再起動でリセット。
**確認:** ブラウザの開発者ツール → Network → `/_pin_check` のレスポンスでエラーメッセージ確認

---

## デバッグログの読み方

### サーバーコンソール出力

```
[WARN] config.json had invalid escapes — auto-repaired and saved
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
static/js/
  main.js          ← メインUI（検索、モーダル、QR、キーボード）
  scan-banner.js   ← スキャン進捗 + スクロールトップ（全ページ）
```
