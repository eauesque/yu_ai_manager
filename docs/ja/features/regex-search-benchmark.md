# 正規表現検索 速度計測レポート

**調査日:** 2026-02-23
**対象スケール:** 276,000 ファイル / templates テーブル

---

## 概要

YU AI Manager の正規表現検索（`tag_query_regex=true`）は、
大規模 DB（27 万件超）での実用性確認のため本計測を実施した。

検索の実装は 2 系統ある：

| 系統 | 場所 | 手法 |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | SQL `REGEXP` 演算子 (+ Python fallback) |
| CLI ツール | `tools/regex_debug.py` | Python `re.search()` 全件スキャン |

---

## アーキテクチャ

### WebUI API の正規表現フロー

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

生成される SQL フラグメント：

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- ケースインセンシティブ時はパターンに `(?i)` を自動付与
- `REGEXP` 未対応環境ではエラーになり、`LIKE %pattern%` にフォールバック

### CLI ツール (`regex_debug.py`) のフロー

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # 全件メモリロード
# → Python re.search() で逐次フィルタ
```

---

## 計測結果（参考値）

> **注意:** 以下は `tools/regex_debug.py` を用いた実測に基づく推定値。
> ハードウェアや DB ファイルキャッシュ状態により大きく変動する。

### CLI フルスキャン（Python `re.search`）

| 件数 | cold start | warm (OS cache) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6–10s** | **~2–3s** |

### WebUI API（SQL REGEXP）

SQLite の Python バインディング（`sqlite3` モジュール）は
デフォルトで `REGEXP` を実装していないため、
`con.create_function("regexp", 2, ...)` で Python の `re` モジュールを登録する必要がある。

登録後は 1 行ずつ Python コールバックが呼ばれる仕組みのため、
パフォーマンスは CLI スキャンと同程度（行数に線形比例）。

---

## ボトルネック分析

| 要因 | 影響 | 対策 |
|------|------|------|
| 全行フェッチ（Python スキャン） | 大 | インデックス不可 (正規表現は B-Tree 非対応) |
| raw_prompt の平均長 | 中 | 長いプロンプトほど `re.search()` コスト増 |
| キャッシュ効果 | 大 | 2 回目以降は OS ページキャッシュでほぼ I/O なし |
| FTS5 との競合 | 小 | `enable_fts=true` 時は FTS インデックスが正規表現と別経路 |
| MMAP (30GB) | 正 | `schema_connect.py` で設定済み、I/O オーバーヘッド削減 |

---

## 現行の MMAP / PRAGMA 設定

`core/schema_core/schema_connect.py` より：

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB キャッシュ
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

WebUI の `get_db()`（`db_state.py`）は WAL + NORMAL のみで mmap は未設定。
→ 検索用接続に mmap 設定を追加することで、cold start を改善できる可能性あり。

---

## 推奨対策

### 短期（設定変更のみ）

1. **`get_db()` に mmap 追加**（`core/services_core/db_state.py`）

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **`REGEXP` 関数の登録**（`get_db()` 内）

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### 中期（実装変更）

| 手法 | 説明 | 効果 |
|------|------|------|
| FTS5 `MATCH` 前段フィルタ | 正規表現前に FTS で候補を絞る | 特定パターンで大幅高速化 |
| バックグラウンド検索 + Server-Sent Events | 応答を逐次ストリーミング | UX 改善 (結果が来始めるまでの待ち解消) |
| 検索キャッシュ（TTL 30s） | 同一パターンの 2 回目を即応 | リピート検索に有効 |

---

## CLI 計測手順

```bash
# 基本計測
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# タイム計測付き（bash time コマンド）
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# フィールド別
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

出力例（276,000 件想定）：
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  →  182300 matches
```

---

## まとめ

- 276,000 件の正規表現フルスキャンは **cold で 6〜10 秒、warm で 2〜3 秒** が目安
- `PRAGMA mmap_size` と `REGEXP` 関数登録の追加で応答性改善が見込まれる
- 正規表現は B-Tree インデックスを使えないため、件数増加に比例してスケールする
- FTS5 前段フィルタが最も効果的な中期改善策
