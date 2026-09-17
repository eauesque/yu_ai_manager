# CJK / 2バイト文字エンコーディングの罠と対策

本ドキュメントは、日本語 (CP932/Shift-JIS) を中心とした 2 バイト圏特有のバグと、
本プロジェクトで採用した解決策をまとめたものです。
同様の問題に遭遇した開発者・AI エージェントの参考になることを意図しています。

---

## 1. Windows コンソール cp932 クラッシュ

### 症状

Windows の `cmd.exe` / PowerShell / Git Bash は既定の出力エンコーディングが **cp932 (Shift-JIS)** です。
`print()` で cp932 に存在しない Unicode 文字を出力すると `UnicodeEncodeError` で即クラッシュします。

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### 踏んだ文字の例

| 文字 | 名前 | どこで使った |
|------|------|------------|
| `—` (U+2014) | em dash | ログ出力の区切り |
| `–` (U+2013) | en dash | 進捗表示 |
| `✓ ✗ ✅ ❌ ⚠️` | チェックマーク・絵文字 | 成功/失敗表示 |
| `🧹 📦 📁 🔍 🔧` | 絵文字 | 処理内容の表示 |
| `█ ░` | ブロック文字 | プログレスバー |

### 対策

- **`print()` には ASCII セーフな文字のみ使う**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-` 等
- ロガー (`logging`) を使う場合も同様。ハンドラの encoding が cp932 なら同じ問題が起きる
- `PYTHONIOENCODING=utf-8` を設定すれば回避可能だが、ユーザー環境に依存するため防御的に ASCII に寄せる方が安全

### 影響範囲

本プロジェクトでは **19 ファイル** を一括修正した (v2.28.0)。
AI (Claude/GPT) にコード生成させると高確率で絵文字や em dash を使うため、
**AI 生成コードのレビュー時に最も注意すべきポイントの一つ**。

---

## 2. ZIP ファイル名の文字化け (CP437 mojibake)

### 症状

古い Windows (95/98/XP 時代) で作成された ZIP ファイルは、
ファイル名を **Shift-JIS (CP932)** で格納しているが、ZIP 仕様ではエンコーディング情報がない。
Python の `zipfile` は UTF-8 フラグ (bit 11) が立っていない場合 **CP437** でデコードするため、
日本語ファイル名が `âwâCâèâb` のような文字化けになる。

### 対策: 10段階フォールバックチェーン

`core/infra_core/encoding.py` に CJK エンコーディングの優先順序リストを定義:

```
UTF-8 (zipfile が先に試行) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- `chardet` / `cchardet` は**使わない**: 短いファイル名 (10-30 bytes) では誤判定が多すぎる
- 固定優先順序方式の方が再現性が高く、デバッグも容易

### Python 3.11+ の `metadata_encoding` パラメータ

```python
# Python 3.11+ なら metadata_encoding で直接指定可能
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

ただし CP932 以外のエンコーディングの ZIP には対応できないため、
失敗時は `metadata_encoding` なしで開き直して `repair_cp437_name()` で復元を試みる。

### 7z の場合

7-Zip は独自のファイル名処理を持つ。7z CLI 経由では
CP437 mojibake が発生することがあり、`repair_cp437_name()` で同様に復元する。

---

## 3. ZIP/7z 2バイト文字でスキャンがハングする

### 症状

`zipfile.ZipFile()` が Shift-JIS エンコードされた古い ZIP の中央ディレクトリを
読み取る際、特定のバイト列でブロッキング I/O に入りハングする。
特にファイル数が多いアーカイブで発生しやすい。

### 対策

1. **タイムアウト保護**: `run_with_timeout()` デーモンスレッドヘルパーを導入
   - ファイル一覧取得 (listing): 30 秒
   - スキャン I/O: 60 秒
2. **scan_errors テーブル** (migration v24): タイムアウトやエンコーディングエラーを DB に永続記録
   - エラータイプ分類: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars の引用符問題

### 症状

SQLite FTS5 の `tokenize` ディレクティブで `tokenchars` オプションを使う際、
引用符の組み合わせによってパースエラーになる。

```sql
-- NG: 外側シングルクォート + 内側ダブルクォート → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK: 外側ダブルクォート + 内側シングルクォート
tokenize="unicode61 tokenchars '_:.'"
```

### 原因

SQLite FTS5 トークナイザのパーサーが、外側シングルクォート内のダブルクォートを
正しく解析できない。SQLite のバージョン (3.45.1 で確認) による挙動差の可能性もある。

### 対策

Python コード側で triple-quote の種類を使い分ける:

```python
# OK: Python の ''' 内で SQL の " と ' を両方使う
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### 発見経緯

本プロジェクトの migration 29 で FTS5 テーブルを再構築する際に発生。
AI が生成したコードがシングルクォート外側の構文を使っており、
SQLite 3.45.1 環境でサーバー起動時にクラッシュした (v2.70.1 で修正)。

---

## 5. WebP EXIF の UTF-16 エンコーディング

### 症状

一部の画像生成ツール (特に NAI 系) が WebP の EXIF メタデータを
**UTF-16 (BOM 付き)** でエンコードして格納することがある。
通常の UTF-8 デコードでは文字化けする。

### 対策

- BOM (Byte Order Mark) を検出して UTF-16 BE/LE を判定
- BOM がない場合はヒューリスティクスで BE/LE を推定
- フォールバックとして UTF-8 → latin-1 の順で試行

---

## 6. PNG tEXt チャンクのエンコーディング

### 症状

PNG 仕様では tEXt チャンクは **Latin-1 (ISO-8859-1)** と定義されているが、
AI 画像生成ツールの多くは UTF-8 でエンコードした文字列をそのまま格納している。
`latin-1` でデコードすると日本語が文字化けする。

### 対策

UTF-8 優先でデコードし、失敗時に latin-1 にフォールバック:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. config.json の Windows パスバックスラッシュ

### 症状

Windows のファイルパスにはバックスラッシュ (`\`) が含まれるため、
JSON ファイルに手動でパスを書くと不正なエスケープシーケンスになる。

```json
{"scan_roots": ["C:\Users\test"]}  // \U と \t がエスケープシーケンスに
```

### 対策

- `_repair_json_backslashes()` でサーバー起動時に自動修復
- 内部的にはパスを正規化して保存

---

## 8. pathlib と WSL UNC パス

### 症状

WSL (Windows Subsystem for Linux) 上で `pathlib.Path.exists()` が
UNC パス (`\\server\share\...`) に対して誤った結果を返すことがある。

### 対策

- UNC パスの存在確認には `os.path.exists()` を使う
- `pathlib` は便利だが、ネットワークパスでは信頼性が低い

---

## 9. CSV エクスポートの UTF-8 BOM

### 症状

UTF-8 の CSV ファイルを Excel で開くと、BOM がないと文字化けする。
Excel は BOM なし UTF-8 を ANSI (日本語環境では CP932) として解釈するため。

### 対策

```python
buf.write("\ufeff")  # UTF-8 BOM for Excel compatibility
```

CSV の先頭に BOM (`\ufeff`) を付与する。
これにより Excel が UTF-8 として正しく認識する。

---

## 10. JSON の `ensure_ascii=False`

### 症状

Python の `json.dumps()` はデフォルトで非 ASCII 文字を `\uXXXX` エスケープする。
MCP ツールのレスポンスで日本語タグ名やファイルパスが `\u30bf\u30b0` のように
エスケープされると、AI エージェントが内容を理解しづらくなる。

### 対策

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

本プロジェクトでは全 MCP ツールモジュール (10 ファイル) で統一的に使用。

---

## 11. フォルダ選択ダイアログの出力デコード

### 症状

Windows の PowerShell でフォルダ選択ダイアログを呼び出す際、
`subprocess` の出力が CP932 でエンコードされている。
デフォルトの UTF-8 デコードでは `UnicodeDecodeError` が発生する。

### 対策

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` でデコード失敗時も安全に処理する。

---

## AI エージェントへの注意事項

上記の問題の多くは **AI がコードを生成する際に見落としやすい** パターンです:

1. **`print()` に絵文字や装飾文字を使わない** — AI は見栄えを良くしようとして高確率で使う
2. **ファイル名のエンコーディングを仮定しない** — UTF-8 前提で書くと CP932 環境で壊れる
3. **SQLite の引用符は実機テストが必須** — ドキュメント通りでも動かないケースがある
4. **`json.dumps()` には `ensure_ascii=False`** — 日本語データを扱うなら必須
5. **subprocess の出力は環境のエンコーディングでデコードする** — Windows は CP932 が多い
6. **CSV は BOM 付きにする** — Excel 互換のため

---

## 参考: 本プロジェクトの関連ファイル

| ファイル | 内容 |
|---------|------|
| `core/infra_core/encoding.py` | CJK フォールバックチェーン、CP437 mojibake 修復 |
| `core/schema_core/schema_migrate_steps_29.py` | FTS5 tokenchars 引用符の正しい書き方 |
| `core/tools/fs_dialog.py` | フォルダ選択ダイアログの CP932 デコード |
| `core/configuration/json_rw.py` | config.json バックスラッシュ修復 |
| `routes/collections.py` | CSV エクスポート BOM 付与 |
| `CLAUDE.md` | 「Windows 環境の注意事項 > コンソール出力」セクション |
