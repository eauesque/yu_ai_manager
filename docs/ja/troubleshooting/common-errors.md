# Tag Database - Debug Checklist

**優先度順のデバッグリスト**
**ステータス**: レガシー (v2.5.x 時代の記録、項目は全て対応済み)
**最終更新**: 2026-02-13

---

## P0 (Critical): 即修正（ユーザビリティに影響）

### ✅ 1. UIレイアウトのズレ修正

**問題:**
```
検索フィールドが横並びで入りきらず、
ボタンがズレている
```

**確認方法:**
1. WebUI起動
2. ブラウザを1366x768にリサイズ
3. 検索欄の並びを確認

**修正箇所:** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- flex-wrap: wrap を追加 -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**検証:**
- [ ] 1920x1080で正常表示
- [ ] 1366x768で正常表示
- [ ] 768x1024（タブレット）で正常表示

---

### ✅ 2. タグオートコンプリート重複除去

**問題:**
```
オートコンプリート候補に重複が出る

表示例:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ スペースの有無だけの違い
```

**確認方法:**
1. タグ入力欄で "sample_creator" と入力
2. オートコンプリートを確認
3. 重複があるか確認

**修正箇所:** `static/js/main/main.js`
```javascript
// initTagAutocomplete() 内
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // 正規化して重複除去
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // カンマ後にスペース
      .replace(/\s+/g, ' ')        // 複数スペース → 単一
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // カウント合算
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**検証:**
- [ ] 重複なくなるか
- [ ] カウントが合算されるか
- [ ] パフォーマンス問題ないか

---

## P1 (High): 改善（機能に影響）

### ✅ 3. 検索時の括弧正規化テスト

**問題:**
```
\(tag\) と (tag) が等価になっているか確認
```

**確認方法:**
1. タグに `\(emphasis\)` を持つ画像を用意
2. 検索欄で `(emphasis)` で検索
3. ヒットするか確認

**確認ポイント:**
- [ ] `(tag)` で検索 → `\(tag\)` もヒット
- [ ] `\(tag\)` で検索 → `(tag)` もヒット
- [ ] 正規表現モードでは変換しない

**関連コード:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. ZIP内ファイル読み込みテスト

**問題:**
```
ZIP内の画像が正常に表示されるか
メタデータが正しく抽出されるか
```

**テストケース:**

#### Test 1: 基本動作
```bash
# 1. テストZIP作成
zip test.zip image1.png image2.png

# 2. スキャン
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. 確認
python tagdb_tool.py search --db test.db --q "*"
```

**確認:**
- [ ] ZIP内ファイルが `test.zip!image1.png` 形式で登録
- [ ] メタデータが抽出されている
- [ ] サムネイルが表示される

#### Test 2: 解凍機能
```
1. WebUIでZIP内ファイルを開く
2. "解凍して編集" ボタンをクリック
3. エクスプローラが開くか確認
4. 解凍されたファイルが存在するか確認
```

**確認:**
- [ ] 解凍ボタンが表示される
- [ ] クリックでエクスプローラが開く
- [ ] extracted/ ディレクトリに解凍される
- [ ] DBに解凍後のファイルが登録される

#### Test 3: 大容量ZIP
```bash
# 1) 1.1GB ZIP を作成（Zip64）
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) ZIP内スキャン
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**確認:**
- [x] メモリ使用量が異常に増えないか
- [x] スキャン時間が許容範囲か（5分以内）
- [x] エラーが出ないか

**実測（2026-02-17）:**
- ZIPサイズ: `1,153,433,914 bytes`（約1.1GB）
- 実行時間: `elapsed=0:00.14`
- 最大RSS: `maxrss_kb=23864`
- DB登録: `zip_members=1`（`large_1_1gb.zip!images/sample.png`）

---

### ✅ 5. チェックポイント検索テスト

**問題:**
```
モデル名が正しく抽出・検索できるか
```

**テストケース:**

#### Test 1: モデル名抽出
```python
# 各形式でモデル名が抽出されるか確認

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**確認:**
- [ ] NovelAI形式で抽出できる
- [ ] SD形式で抽出できる
- [ ] ComfyUI形式で抽出できる

#### Test 2: 検索機能
```
1. WebUIでチェックポイント入力欄をクリック
2. オートコンプリートが表示されるか
3. "animagine" で検索
4. 該当モデルの画像のみ表示されるか
```

**確認:**
- [ ] オートコンプリートが機能する
- [ ] 部分一致で検索できる
- [ ] 使用頻度順にソートされる

---

## P2 (Medium): 将来対応（パフォーマンス改善）

### ✅ 6. サムネイルキャッシュ実装

**問題:**
```
ZIP内ファイルのサムネイルが毎回生成される
→ 遅い
```

**実装案:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # キャッシュパス生成
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # キャッシュがあれば返す
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # なければ生成
    thumbnail = generate_thumbnail(...)

    # キャッシュに保存
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**検証:**
- [ ] 2回目のアクセスが高速化
- [ ] ディスク使用量が許容範囲
- [ ] キャッシュクリア機能

---

### ✅ 7. 大量データでのパフォーマンス計測

**テストケース:**

#### Test 1: 100,000ファイル
```bash
# スキャン時間計測
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# 検索時間計測
time python tagdb_tool.py search --db large.db --q "1girl"
```

**目標:**
- [ ] スキャン: 50,000件/時間 以上
- [ ] 検索: 1秒以内（100,000件中）

#### Test 2: WebUI応答性
```
1. 100,000件のDBでWebUI起動
2. 検索実行
3. スクロール
```

**確認:**
- [ ] 検索結果が3秒以内に表示
- [ ] スクロールがスムーズ
- [ ] ブラウザがフリーズしない

---

## テスト実行チェックリスト

### 環境準備
- [ ] Python 3.8+ インストール確認
- [ ] 依存パッケージインストール
- [ ] テストデータ準備（各形式の画像）

### 機能テスト
- [ ] ZIP読み込み
- [ ] 複数ディレクトリスキャン
- [ ] タグ正規化
- [ ] チェックポイント検索
- [ ] モデルフィルタ

### UI/UXテスト
- [ ] レイアウト（複数解像度）
- [ ] ダークモード
- [ ] キーボードショートカット
- [ ] オートコンプリート

### パフォーマンステスト
- [ ] 10,000件
- [ ] 50,000件
- [ ] 100,000件
- [ ] ZIP大容量（500MB+）

### ブラウザ互換性
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### OS互換性
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## デバッグツール

### ログ有効化
```bash
# tagdb_tool.py の先頭に追加
import logging
logging.basicConfig(level=logging.DEBUG)
```

### パフォーマンス計測
```python
import time

start = time.time()
# ... 処理 ...
print(f"Time: {time.time() - start:.2f}s")
```

### メモリ使用量確認
```python
import tracemalloc

tracemalloc.start()
# ... 処理 ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**作成日:** 2026-02-13
**優先度:** P0 → P1 → P2 の順で対応
**注記:** 本チェックリストは v2.5.x 時代に作成されたもので、記載項目は全て対応済みです
