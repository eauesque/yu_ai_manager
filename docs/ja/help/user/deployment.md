# デプロイメント・運用ガイド

YU AI Manager を本番環境で運用するための手順をまとめています。

## 1. 概要

運用パターンは主に 3 つあります。

| パターン | 用途 | 構成 |
|---------|------|------|
| 直接実行 | 個人利用・開発 | Python + venv で起動 |
| Docker | サーバー運用 | docker-compose で Quart + Nginx |
| リバースプロキシ | 外部公開 | 既存 Web サーバーの背後に配置 |

いずれの場合も、データは `data/tags.db` (SQLite) に保存されます。外部の DB サーバーは不要です。

---

## 2. 直接実行 (開発・個人利用)

### セットアップ

```bash
# リポジトリ取得
git clone <repository-url> && cd yu_ai_manager

# Python 仮想環境の作成
python -m venv venv

# 仮想環境を有効化
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# 依存パッケージのインストール
uv pip install -r requirements.txt

# フロントエンドビルド
pnpm install && pnpm run build

# 起動
python web_ui.py --db data/tags.db
```

ブラウザで `http://localhost:5000` を開いてください。

### launch-args.txt による引数設定

`launch-args.txt.example` を `launch-args.txt` にコピーして編集すると、起動時の引数を固定できます。CLI 引数が優先されます。

```txt
# ポート変更
--port 5100
# LAN 公開 (0.0.0.0 バインド)
--lan
# PIN 認証
--pin 1234
```

### systemd サービス化 (Linux)

```ini
# /etc/systemd/system/yu-ai-manager.service
[Unit]
Description=YU AI Manager
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/yu_ai_manager
ExecStart=/opt/yu_ai_manager/venv/bin/python web_ui.py --db data/tags.db --lan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yu-ai-manager
```

### Windows サービス化

`start.bat` をタスクスケジューラに登録するのが最も簡単です。「ログオン時に実行」に設定してください。

---

## 3. Docker デプロイ

### クイックスタート

```bash
# 設定ファイルを準備
cp config.json.example config.json
# config.json を編集 (pin, scan_roots 等)

mkdir -p data

# ビルド & 起動
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

`http://localhost` でアクセスできます (Nginx 経由)。

### docker-compose.prod.yml の構成

- **app**: Quart アプリケーション (ポート 5000、内部のみ)
- **nginx**: リバースプロキシ (ポート 80 を外部公開)

### ボリュームマウント

| ホスト | コンテナ | 用途 |
|-------|---------|------|
| `data/` | `/app/data/` | DB ファイルの永続化 |
| `config.json` | `/app/config.json` | 設定ファイル (読み取り専用) |
| `static/` | `/app/static/` | Nginx が直接配信する静的ファイル |

画像フォルダは `config.json` の `scan_roots` で指定したパスを追加マウントしてください。

```yaml
# docker-compose.prod.yml に追記
volumes:
  - /path/to/images:/images:ro
```

### 環境変数

`deploy/.env.example` を `deploy/.env` にコピーして編集します。

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `NGINX_PORT` | `80` | Nginx の公開ポート |
| `UPSTREAM_HOST` | `app` | Quart コンテナ名 (変更不要) |
| `UPSTREAM_PORT` | `5000` | Quart ポート (変更不要) |

### Podman を使う場合

Docker の代わりに Podman でも動作します。`podman compose` または `podman-compose` をインストールし、同じコマンドを使ってください。詳細は `docs/ja/installation/podman.md` を参照。

---

## 4. リバースプロキシ設定

### Nginx 設定のポイント

`deploy/nginx.conf.template` に実用的な設定が含まれています。要点は以下の通りです。

- **静的ファイル**: `/static/` を Nginx から直接配信 (Quart をバイパス)
- **SSE**: `/api/events/` は `proxy_buffering off` でバッファリングを無効化
- **アップロード上限**: `client_max_body_size 100m` (Quart 側と合わせる)
- **Gzip**: JSON, CSS, JS を圧縮

### SSL/TLS (Let's Encrypt)

Docker 構成の Nginx は HTTP のみです。HTTPS が必要な場合は 2 つの方法があります。

**方法 1: 前段プロキシ (推奨)**

Cloudflare、Caddy、Traefik 等を前段に置き、HTTPS 終端させます。

```
クライアント --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**方法 2: Nginx に直接 SSL を追加**

`nginx.conf.template` に `listen 443 ssl;` と証明書パスを追加し、certbot で Let's Encrypt 証明書を取得します。

### Trusted Proxy の設定

リバースプロキシ経由の場合、`config.json` で信頼する IP を指定してください。

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

これにより `X-Forwarded-For` / `X-Forwarded-Proto` ヘッダが正しく処理されます。CIDR 表記に対応しています。

---

## 5. 認証設定

4 種類の認証が利用できます。用途に応じて組み合わせてください。

### PIN 認証 (ブラウザアクセス用)

```json
{ "pin": "your-secret-pin" }
```

LAN に公開する場合 (`--lan` または `0.0.0.0` バインド) は PIN の設定が必須です。PIN 未設定で `0.0.0.0` にバインドすると起動が拒否されます。

### API キー認証 (プログラムからのアクセス)

Settings 画面で API キーを発行し、リクエストヘッダに付与します。

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

API キー認証では CSRF ヘッダ (`X-Requested-With`) は不要です。

### Trusted Proxy 認証

リバースプロキシが `X-Remote-User` ヘッダを付与する構成で使えます。`trusted_proxy_ips` の設定が必須です。

### LAN 共有モード

`/s/` パスでゲスト用の共有リンクを発行できます。PIN をスキップし、トークンで個別認証します。

---

## 6. バックアップと復旧

定期的にバックアップすべきファイルは以下の 3 種類です。

| ファイル | 内容 |
|---------|------|
| `data/tags.db` | 全メタデータ・タグ・設定を含む SQLite DB |
| `config.json` | アプリケーション設定 |
| `data/secret.key`, `data/secret.salt` | 暗号化キー (設定の暗号化に使用) |

### バックアップ手順

```bash
# DB のコピー (運用中でも安全)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# 設定と暗号化キー
cp config.json data/secret.key data/secret.salt backup/
```

### 復旧手順

バックアップファイルを元の場所に配置してサーバーを再起動するだけです。DB マイグレーションは起動時に自動で適用されます。

暗号化キー (`secret.key`, `secret.salt`) を紛失すると、暗号化された設定値 (API 資格情報等) が復号できなくなります。必ずバックアップしてください。

---

## 7. アップグレード手順

```bash
# 1. サーバーを停止
# 2. コードを更新
git pull

# 3. 依存パッケージを更新
source venv/bin/activate  # または .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. フロントエンドを再ビルド
pnpm install && pnpm run build

# 5. サーバーを起動
python web_ui.py --db data/tags.db
```

DB スキーマのマイグレーションは起動時に自動で実行されます。手動作業は不要です。

Docker の場合は再ビルドするだけです。

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. 監視・ログ

### ログストリーミング

Settings > Logs タブでリアルタイムのログを確認できます。SSE (`/api/logs/stream`) でブラウザにストリーミングされます。

過去のログは `/api/logs/recent` で取得できます。

### ヘルスチェック

`/api/server-info` エンドポイントで稼働状況を確認できます。

```bash
curl http://localhost:5000/api/server-info
```

バージョン、DB スキーマバージョン、タイムゾーン等の情報が返されます。監視ツールのヘルスチェックにはこのエンドポイントを使ってください。

### MCP 経由の診断

MCP クライアント (Claude Desktop 等) から `debug_health_check` ツールを呼び出すと、DB 整合性チェック・検索動作確認・カウント検証を一括実行できます。
