# はじめに

YU AI Manager は AI 生成画像のメタデータを管理する WebUI アプリケーションです。

## インストール

### 必要環境

- Python 3.11 以上
- Node.js 18 以上（フロントエンドビルド用）

### セットアップ手順

```bash
# リポジトリをクローン
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# uv をインストール（初回のみ）
pip install uv

# Python 仮想環境の作成と依存パッケージのインストール
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# フロントエンドのビルド
pnpm install
pnpm run build

# オプション: セマンティック検索の高速化 (大規模ライブラリ向け)
uv pip install faiss-cpu
```

## 起動方法

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

ブラウザで `http://localhost:5000` にアクセスしてください。

## 初回設定

1. **スキャンフォルダの登録**: Settings > Scan タブでAI画像が保存されているフォルダを追加
2. **スキャンの実行**: フォルダ追加後、自動的にスキャンが開始されます
3. **画像の閲覧**: メインページで画像を検索・閲覧できます

## LAN 公開

他のデバイスからアクセスしたい場合:

1. Settings > **Server** タブで「LAN Access」を ON に設定
2. PIN 認証を設定（LAN 公開時は必須）  
   **Settings > Server タブ** の「PIN 認証コード」フィールドに数字（4〜8桁）を入力してください
3. サーバーを再起動

LAN 内の他のデバイスから `http://<サーバーのIP>:5000` でアクセスできます。
