# YU AI Manager -- デプロイガイド

> **[English](README.md) | [繁體中文](README.zh-tw.md) | [简体中文](README.zh-cn.md) | [한국어](README.ko.md)**

## 前提条件

- Docker Engine 20.10 以降
- Docker Compose V2 (`docker compose` コマンド)
- プロジェクトルートに `config.json` が存在すること

## クイックスタート

```bash
# 1. プロジェクトルートで config.json を準備
cp config.json.example config.json
# config.json を編集 (pin, scan_roots 等を設定)

# 2. データディレクトリを作成 (初回のみ)
mkdir -p data

# 3. ビルド & 起動
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. ブラウザでアクセス
# http://localhost (NGINX_PORT=80 の場合)
```

## 停止 / 再起動

```bash
# 停止
docker compose -f deploy/docker-compose.prod.yml down

# 再起動 (コード変更後)
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## 環境変数

`deploy/.env.example` を `deploy/.env` にコピーして編集してください。

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `NGINX_PORT` | `80` | Nginx がホスト側で公開するポート |
| `UPSTREAM_HOST` | `app` | Flask コンテナのホスト名 (通常変更不要) |
| `UPSTREAM_PORT` | `5000` | Flask コンテナのポート (通常変更不要) |

## ボリュームマウント

| ホスト側 | コンテナ側 | 説明 |
|---------|-----------|------|
| `data/` | `/app/data/` | SQLite DB (`tags.db`) の永続化 |
| `config.json` | `/app/config.json` | アプリ設定 (読み取り専用) |
| `static/` | `/app/static/` | Nginx が直接配信する静的ファイル |

## PIN 認証の設定 (本番環境)

LAN に公開する場合は `config.json` に PIN を設定してください。PIN がない状態で `0.0.0.0` にバインドすると起動が拒否されます。

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000,
    "lan": true
  },
  "pin": "your-secret-pin"
}
```

Docker 環境では Nginx がフロントエンドになるため、Flask 自体は常に `0.0.0.0:5000` でリッスンします。外部公開の制御は Nginx 側のポートバインディングで行ってください。

## SSL/TLS 終端 (リバースプロキシパターン)

本構成の Nginx は HTTP (ポート 80) のみを提供します。SSL/TLS が必要な場合は、以下のいずれかの方法を推奨します。

### 方法 1: 前段にリバースプロキシを配置

```
[クライアント] --HTTPS--> [Cloudflare / Caddy / Traefik]
                                |
                            --HTTP--> [この Nginx :80]
                                          |
                                      --> [Flask :5000]
```

### 方法 2: この Nginx に直接 SSL を追加

`nginx.conf.template` を編集し、`listen 443 ssl;` と証明書パスを追加してください。Let's Encrypt (certbot) との連携が一般的です。

## リバースプロキシ設定 (ProxyFix)

Nginx 等のリバースプロキシ経由でアクセスする場合、正しいクライアント IP・プロトコル・ホストを認識させるために `config.json` を設定してください。

### 方法 1: trusted_proxy_ips を明示指定 (推奨)

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

CIDR 表記にも対応しています。信頼済み IP からの `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Forwarded-Host` ヘッダが自動的に処理されます。

### 方法 2: behind_proxy フラグ (簡易)

```json
{
  "deploy": {
    "behind_proxy": true
  }
}
```

`trusted_proxy_ips` が未設定の場合、ループバック (`127.0.0.1`, `::1`) のみを信頼します。Docker Compose 等でプロキシが別コンテナの場合は方法 1 を使ってください。

## トラブルシューティング

### コンテナが起動しない

```bash
# ログを確認
docker compose -f deploy/docker-compose.prod.yml logs app
docker compose -f deploy/docker-compose.prod.yml logs nginx
```

### DB ファイルの権限エラー

`data/` ディレクトリの権限を確認してください。コンテナ内のプロセスが書き込みできる必要があります。

```bash
chmod 777 data/
```

### 静的ファイルが 404

TypeScript ビルド済みの `static/dist/` が存在することを確認してください。

```bash
# ホスト側でビルド
pnpm run build

# または Docker ビルド時に含める
```

---

## WD-Tagger リモートサーバー

LAN 内の複数マシンで分散タグ付けを行うためのスタンドアロン推論サーバーです。
YU AI Manager 本体は不要で、このスクリプト単体で動作します。

### 対応バックエンド

| バックエンド | 実行先 | 必要ファイル | 用途 |
|-------------|--------|-------------|------|
| `onnx` | CPU / CUDA / ROCm | `model.onnx` | 汎用（どのマシンでも動く） |
| `hailo` | Hailo-10H NPU | `model.hef` | Pi 5 + Hailo-10H で高速推論 |
| `auto` | Hailo 優先 → ONNX フォールバック | 両方 or どちらか | 推奨 |

### セットアップ

```bash
# 1. 必要パッケージをインストール
pip install numpy Pillow

# ONNX バックエンド:
pip install onnxruntime          # CPU
pip install onnxruntime-gpu      # NVIDIA CUDA

# Hailo バックエンド:
# hailo_platform wheel を Hailo Developer Zone またはソースからインストール

# 2. モデルディレクトリを準備
mkdir -p models/wd-swinv2-tagger-v3
# HuggingFace から model.onnx と selected_tags.csv をダウンロード:
#   https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
# Hailo 版は model.hef も配置 (Dataflow Compiler で ONNX から変換)

# 3. サーバー起動
python hailo_tagger_server.py --model-dir ./models/wd-swinv2-tagger-v3

# バックエンドを明示:
python hailo_tagger_server.py --backend onnx --model-dir ./models/wd-swinv2-tagger-v3
python hailo_tagger_server.py --backend hailo --model-dir ./models/wd-swinv2-tagger-v3

# 認証トークン付き:
python hailo_tagger_server.py --token "my-secret" --model-dir ./models/wd-swinv2-tagger-v3

# JSON 設定ファイルを使う場合:
python hailo_tagger_server.py --config tagger_config_example.json
```

### 設定ファイル例 (`tagger_config_example.json`)

```json
{
  "port": 8080,
  "host": "0.0.0.0",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": ""
}
```

### YU AI Manager 側の設定

メインの YU AI Manager WebUI の **設定 → Tagger タブ** でサーバーを登録します。

1. 「Add Server」→ タイプ: `hailo_remote`
2. Endpoint URL: `http://<worker-ip>:8080`
3. Bearer Token: (設定した場合のみ)
4. 分配モード: `parallel`（複数台で並列処理）

### API エンドポイント

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/health` | GET | サーバーステータス (backend, device, model) |
| `/tag` | POST | 画像タグ付け (multipart/form-data, field: `image`) |

### ヘルスチェック例

```bash
curl http://192.168.1.101:8080/health
# {"status": "idle", "backend": "onnx", "device": "onnx-cpu", "model": "wd-swinv2-tagger-v3", ...}
```

### タグ付け例

```bash
curl -X POST http://192.168.1.101:8080/tag \
  -F "image=@test.png"
# {"tags": [{"tag": "1girl", "confidence": 0.97, "category": "general"}, ...], "elapsed_ms": 150}
```
