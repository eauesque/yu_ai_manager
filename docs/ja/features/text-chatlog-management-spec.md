# YU AI Manager テキスト・チャットログ管理機能 仕様書

作成日: 2026-03-01
対象バージョン: 未定（実装タイミングは要検討）

## 概要

YU AI Managerに以下の3機能を追加する。

- **MDビューワー** — Markdownファイルのローカル閲覧
- **チャットログ管理** — Claude/ChatGPT/Open WebUIのログをインポート・閲覧・検索
- **テキスト全文検索** — FTS5による横断検索

設計思想は既存機能と同じく「ローカル完結・クラウド不使用」。

---

## 1. MDビューワー

### 目的

OSのファイルビューワーでは貧弱なMarkdownの閲覧を、YU AI Manager内で完結させる。開発メモ・設計ドキュメント・TODOリストなどの日常的な参照に使う。

### スキャン対象

- 拡張子: `.md`, `.markdown`
- 既存のスキャンルートをそのまま使用
- 除外: `.git/` 配下、`node_modules/` 配下

### DBスキーマ

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- 先頭の # 見出しから抽出
    content     TEXT,        -- 生のMarkdownテキスト
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### ビューワーUI

- 既存のモーダルまたはサイドパネルに統合
- レンダリング: marked.js（CDN不使用、ローカルに同梱）
- コードブロック: シンタックスハイライト（highlight.js）
- 生テキスト表示切り替えボタンを用意

### MCP対応

- `search_md_files(query, path_filter)` → ファイル一覧
- `get_md_content(file_id)` → 生テキスト

---

## 2. チャットログ管理

### 目的

「あのバグの議論どこだっけ」「あの設計判断の理由なんだったっけ」をうろ覚えのキーワードで検索して辿り着けるようにする。開発履歴の検索エンジンとして使う。

### 対応形式

| サービス | エクスポート形式 | 取得方法 |
|---|---|---|
| Claude | conversations.json | 設定 → データのエクスポート |
| ChatGPT | conversations.json | 設定 → データのエクスポート |
| Open WebUI | JSONエクスポート | チャット履歴 → エクスポート |

### DBスキーマ

```sql
-- 会話単位
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- 元サービスの会話ID
    title         TEXT,
    model         TEXT,           -- 使用モデル名
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- メッセージ単位
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- 会話内順序
);

-- FTS5全文検索
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### インポーター

各サービスのJSONを共通中間形式に変換してDBに投入する。

**Claude JSONの構造（主要フィールド）:**

```json
{
  "uuid": "...",
  "name": "会話タイトル",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSONの構造（主要フィールド）:**

```json
{
  "id": "...",
  "title": "会話タイトル",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Open WebUI JSONの構造:**

- OpenAI互換APIのフォーマットに準拠
- messages配列にrole/content

### インポートUI

- 設定ページにインポートセクションを追加
- JSONファイルをドラッグ＆ドロップまたはファイル選択
- インポート済みの会話は `external_id` で重複チェック（冪等）
- インポート結果サマリー（追加件数・スキップ件数）を表示

### ビューワーUI

- 会話一覧ページ（タイトル・日付・モデル・ソース表示）
- 会話詳細ページ（ターン形式で表示、role別に色分け）
- モデル名・ソース・日付範囲でフィルタ
- 添付画像はパス参照のみ保持（実体はコピーしない）

### MCP対応

- `search_chat_logs(query, source, model, date_from, date_to)` → 会話一覧
- `get_conversation(conversation_id)` → メッセージ一覧
- `import_chat_log(source, json_path)` → インポート実行

---

## 3. テキスト全文検索

### 対象

- MDファイル（`md_files_fts`）
- チャットログ（`chat_messages_fts`）
- 既存のプロンプトライブラリ（`prompt_library_fts`、実装済み）

### 検索UI

- 既存の検索バーを拡張、またはテキスト専用の検索ページを別途用意
- 検索対象をトグルで選択（MD / チャットログ / プロンプトライブラリ）
- bm25スコア順でランキング表示
- ヒット箇所のスニペット表示（前後50文字程度）

### 検索API

```
GET /api/text-search?q=キーワード&target=md,chat,prompt&limit=20
```

レスポンス:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "会話タイトル",
      "snippet": "...ヒット箇所のテキスト...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## 実装優先順位

1. MDビューワー（実装コスト低・即効性高）
2. チャットログインポーター（Claude/ChatGPT対応を先行）
3. チャットログビューワー
4. Open WebUI対応
5. 横断テキスト検索UI

---

## 将来拡張

- チャットログの定期自動インポート（エクスポートファイルを監視フォルダに置くだけで取り込む）
- 画像生成に使ったプロンプトと、その議論のチャットログをリンク
- ollamaによるチャットログの自動要約・タグ付け

---

## 備考

- FTS5は既存の `prompt_library_fts` で実装済みのためパターン流用可能
- marked.js はCDNを使わずローカル同梱（ローカル完結の設計思想に従う）
- チャットログの添付画像（DALL-E生成画像等）はURLが期限切れになるため実体保存は行わない
