# ユースケース集

YU AI Manager の代表的な使い方を「こんなときはこう使う」形式でまとめています。

---

## 1. 大量の AI 画像を整理したい

NovelAI や Stable Diffusion で生成した画像が何千枚もフォルダに溜まっていて、見返すのが大変なとき。

### 手順

1. **Settings > Scan** タブでスキャンフォルダを登録する（複数可）
2. フォルダ追加後、自動でスキャンが開始される。ZIP/7z 内もスキャン可能
3. スキャン完了後、メインページでタグ検索（例: `1girl, blue_eyes`）やソートで画像を絞り込む
4. 気に入った画像を選択し、右クリック > **コレクションに追加** でグループ分け
5. コレクションサイドバーからいつでもグループ単位で閲覧可能

### ヒント

- スキャン中も検索・閲覧は可能です（読み取り専用 DB 接続で競合しません）
- Auto Scan Watcher 拡張を有効にすると、フォルダへの新規追加を自動検出します
- 100 万件規模でも Keyset Pagination で高速にページ送りできます

---

## 2. 特定のプロンプトで生成した画像を探したい

「あのときの構図のプロンプト、なんだったっけ」と思い出せないとき。

### 手順

1. 検索バーの検索対象を **in_prompt** に切り替える
2. 覚えているキーワード（例: `cherry blossom`）を入力して検索
3. 正規表現を使えばより柔軟に絞り込める（例: `masterpiece.*cherry`）

### ヒント

- FTS (全文検索) が有効な場合、大量のプロンプトでも高速に検索できます
- 日付範囲やファイル形式フィルタと組み合わせると効果的です
- ソートを `random` にすると、忘れていた画像の再発見にも使えます

---

## 3. 似た構図の画像を見つけたい

「この画像と似た雰囲気の画像がほかにもあったはず」と探したいとき。

### 手順 A: pHash 類似検索（構図・色合い）

1. 画像の詳細モーダルを開く
2. **類似画像を検索** ボタンをクリック
3. pHash (知覚ハッシュ) で構図が近い画像がサイドパネルに一覧表示される

### 手順 B: CLIP セマンティック検索（意味・概念）

1. 検索バー右の **セマンティック検索** ボタンをクリック
2. 自然言語で説明を入力（例:「海辺に立つ少女」「夕焼けの街並み」）
3. CLIP が画像の意味を理解して類似度順に表示

### ヒント

- セマンティック検索には CLIP モデル（ONNX または Hailo-10H）の事前設定が必要です
- 大規模ライブラリ（10 万件以上）では `faiss-cpu` をインストールすると検索速度が劇的に向上します
- pHash は構図の一致、CLIP は意味的な類似性と、得意分野が異なります。両方試すと発見が増えます

---

## 4. お気に入り画像を管理したい

大量の画像の中から傑作だけをすぐ見返せるようにしたいとき。

### 手順

1. 画像カードまたは詳細モーダルの **ハートボタン** でお気に入り登録
2. 詳細モーダルで **星レーティング**（1〜5 段階）を設定して品質を評価
3. **アノテーション** に自由なメモを残す（例:「リテイク候補」「SNS 投稿済み」）
4. 検索フィルタで「お気に入りのみ」「星 4 以上」などに絞り込む

### ヒント

- 評価順ソート（`rating_desc`）で高評価画像をまとめて閲覧できます
- コンテキストメニュー（右クリック）からもお気に入り・レーティング操作が可能です

---

## 5. 画像のプロンプトを別ツールに送りたい

過去に作った画像のプロンプトを再利用して、別のツールで再生成やバリエーションを作りたいとき。

### 手順

1. 画像の詳細モーダルを開き、プロンプト情報を確認
2. **SD WebUI に送る** / **ComfyUI に送る** / **NAI に送る** ボタンをクリック
3. Bridge ページが開き、プロンプトが自動入力される
4. 必要に応じてプロンプトを編集し、生成ツール側で実行

### ヒント

- SD ↔ NAI 間は `()` と `{}` のウェイト構文が自動変換されます
- Bridge ツールバーの **QP** ボタンで品質プリセットをワンクリック挿入できます
- Prompt Converter や Prompt Simulator からも各 Bridge に送信可能です

---

## 6. ZIP/7z アーカイブ内の画像を閲覧したい

ダウンロードした画像セットが ZIP にまとめられていて、展開せずに中身を確認したいとき。

### 手順

1. Settings > Scan で ZIP/7z ファイルが含まれるフォルダを登録
2. スキャンオプションで **ZIP/7z 内スキャン** を有効にする
3. スキャン完了後、アーカイブ内の画像もメインページで通常の画像と同様に検索・閲覧可能
4. 詳細モーダルではアーカイブ名とアーカイブ内パスが表示される

### ヒント

- アーカイブ内の動画はテンプキャッシュ（LRU 2GB）に展開されるため、繰り返し再生もスムーズです
- 入れ子 ZIP（ZIP-in-ZIP）にも対応しています
- バッチダウンロード機能でアーカイブ内画像を新しい ZIP にまとめ直すこともできます

---

## 7. チームや家族と画像を共有したい

同じ Wi-Fi 内の別デバイス（スマホ・タブレットなど）から画像を閲覧させたいとき。

### 手順

1. **Settings > Server** タブで「LAN Access」を ON にする
2. **PIN コード** を設定する（LAN 公開時は必須）
3. サーバーを再起動する
4. LAN 内の他デバイスから `http://<サーバーIP>:5000` にアクセス
5. PIN を入力してログイン

### ヒント

- **LAN Share トークン**（`/s/` パス）を発行すると、PIN なしのゲストアクセスリンクを共有できます
- サーバー画面に QR コードが表示されるので、スマホのカメラで読み取るだけでアクセスできます
- リバースプロキシ経由の Trusted Proxy 認証にも対応しています

---

## 8. 自動でタグを付けたい

手動でタグを付けるのが面倒なとき、AI に画像を分析させてタグを自動付与したいとき。

### 手順 A: WD-Tagger（高速・タグ特化）

1. **Settings** で WD-Tagger ONNX モデルをダウンロード
2. Tools ページまたは詳細モーダルから **WD-Tagger 実行** をクリック
3. Danbooru スタイルのタグが自動付与される

### 手順 B: AI Analysis（自然言語・高精度）

1. **Settings > AI Analysis** で Ollama または OpenAI 互換サーバーを追加
2. 画像の詳細モーダルの **AI Analysis タブ** から分析を実行
3. 自然言語による画像説明が生成される

### ヒント

- WD-Tagger は VLM エンジン（OpenAI API 互換）との複合モードにも対応しています
- NSFW フィルタやタグ正規化などの後処理が自動適用されます
- XMP メタデータへのタグ書き込みにも対応しており、他ツールとの連携が容易です

---

## 9. 統計・レポートを見たい

自分の画像ライブラリの傾向や成長を把握したいとき。

### 手順

1. ナビゲーションから **Stats** ページを開き、全体統計を確認
2. **Monthly Report** ページで月別の詳細レポートを閲覧
   - 月間ファイル数・前月比、TOP 20 タグ、新規タグ、ソース分布、日別カウント
3. **Trophies** セクションで実績トロフィーを確認

### ヒント

- トロフィーは 6 カテゴリ（milestone / streak / diversity / source / hidden）、4 ティア（bronze〜platinum）で段階的に解放されます
- タイムゾーン設定（Settings > Appearance）を正しく設定すると、日別統計が正確になります

---

## 10. MCP で AI エージェントと連携したい

Claude Desktop や他の MCP 対応 AI ツールから画像ライブラリを操作したいとき。

### 手順

1. MCP クライアント（Claude Desktop など）の設定に YU AI Manager の MCP サーバーを登録
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. AI に「画像を検索して」「お気に入りに追加して」など自然言語で指示
3. `search_images`、`add_favorite`、`trigger_scan` など 60 以上のツールが利用可能

### ヒント

- MCP クライアント拡張からは外部 MCP サーバー（stdio / SSE / Streamable HTTP）にも接続できます
- API Key 認証を設定すれば、CSRF ヘッダなしで外部ツールから REST API を直接呼び出すこともできます
- Hailo GenAI 拡張を使えば OpenAI SDK 互換エンドポイント経由でも連携可能です

---

## 11. Hailo-10H を OpenAI 互換サーバーとして使いたい

Hailo-10H NPU を搭載している環境で、OpenAI SDK 互換のローカル AI サーバーとして活用したいとき。Open WebUI、Continue.dev、自作スクリプトなどの外部ツールから Hailo の LLM / VLM / 音声認識 / CLIP エンベディングをそのまま利用できます。

### 対応エンドポイント

| エンドポイント | 機能 | 対応する OpenAI API |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | ダウンロード済みモデル一覧 | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | テキスト生成・画像理解 (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | 音声文字起こし | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | テキスト→ベクトル変換 (CLIP) | Embeddings |

### 手順

1. **Extensions > GenAI** ページで Hailo GenAI 拡張が有効になっていることを確認
2. 使いたいモデルをダウンロード（LLM: `qwen2.5-1.5b-chat` 等、VLM: `llava-v1.6-vicuna-7b` 等）
3. 外部ツールの接続設定で **Base URL** を以下に設定:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   （ポート番号は YU AI Manager の起動設定に合わせて変更）
4. API Key は不要（ローカルアクセスのため）。ツールが API Key を必須とする場合はダミー値（例: `dummy`）を入力

### 外部ツールとの接続例

#### Open WebUI

Settings > Connections > OpenAI API で追加:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (VS Code AI アシスタント)

`~/.continue/config.json` に追加:
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# テキスト生成
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# 画像理解 (VLM) — base64 画像を添付
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# 音声文字起こし
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# テキストエンベディング (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### 対応パラメータ

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (文字列または文字列配列)
- **モデルエイリアス**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### 注意事項

- **デバイス排他性**: Hailo-10H は同時に 1 つの GenAI モデル（LLM or VLM or S2T）しかロードできません。モードの切り替えは GenAI ページで行います
- **画像 URL の制限**: セキュリティ上、`http://` URL による画像指定はブロックされます。`data:image/...;base64,...` 形式または YU AI Manager の `file_id:` 形式を使用してください
- **CLIP エンベディング**: テキスト→ベクトル変換のみ対応。画像→ベクトルは `/api/semantic/` エンドポイント経由で利用可能です
- **音声フォーマット**: WAV 以外（MP3, M4A, OGG 等）は ffmpeg が必要です
- **`usage` フィールド**: トークンカウントは常に 0 が返されます（Hailo NPU の制約）
