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

### サーバー起動前にデータディレクトリが存在していることが必須

デプロイ担当者が作成します。サーバーは作成しません。スタンドアロンモードでは yu-server は `tags.db` が存在しない場合に自ら作成しますが、それを保持するディレクトリについては**意図的に作成しません**：`--db` パスを誤入力した場合、空の新規ライブラリが作成され、失った状態と区別がつかなくなってしまうからです。ディレクトリが存在しない場合は起動時に拒否され、解決された絶対パスが表示されます。

Docker ユーザーはクイックスタートの `mkdir -p data` からこれを得ます。`deploy/yu-server.service` の場合、`${YU_DB}` を含むディレクトリが既に存在している必要があります。`deploy/systemd/yu-server.service` は `WorkingDirectory` から相対デフォルト値 `data/tags.db` で実行されるため、そのディレクトリの下に `data/` を作成してください。デスクトップビルドはこれを自動的に処理します (`src-tauri/src/app_dirs.rs::ensure_data_dir`)。

スタンドアロンはまた `--db-key` (または `YU_DB_KEY`) が必須です：サーバーにはデフォルトキーがなく、暗号化されていないデータベースの作成を拒否します。これは Python バージョンが無条件に SQLCipher を通じて `tags.db` を開くが、プレーンテキストなものは決して開けないためです。

### バイナリより古いデータベース

データベースのスキーマ版数がバイナリの期待する版数より古く、かつ移行を担える Python バックエンドがどこにも宣言されていない場合、yu-server は **78** で終了します。再試行しても解決しないため、`RestartPreventExitStatus=78` が systemd の再試行を止めます。

### 移行する

サービスが使っているデータベースに対して移行ツールを実行してください:

```sh
cd /path/to/yu_ai_manager
YU_DB_KEY='<the key from server.env>' \
  uv run python scripts/migrate_db_cli.py --db /path/to/data/tags.db
```

これは移行だけを行います。データベースを作成することはなく (スキーマ版数 0 を報告するファイルは拒否されます)、`config.json` を読まず、既定では移行前バックアップを取れない場合に移行を拒否します。終了コードは `0` 最新または移行成功、`1` 移行失敗、`3` バックアップ不可、`4` データベースを開けない (鍵違い・破損・権限)、`5` 版数 0、`6` 他プロセスが書き込みロックを保持、です。

**鍵が肝心です。** v4.730.3 までの Python 側は組み込みの鍵で暗号化されたデータベースしか開けませんでした。つまり、`ExecStartPre` が生成を要求している `YU_DB_KEY` を自分で生成したサービスは、Python からまったく移行できませんでした。`--db-key` を渡すか `YU_DB_KEY` を設定すれば移行できます。

**78 は「版数が読めた」場合の話。** 開くことすらできないデータベースは別の結末になります——実バイナリで、一つ古い暗号化データベースに対して実測:

| データベース | 鍵 | exit | 文言 |
|---|---|---|---|
| 暗号化・古い | 渡す | **78** | 「schema v88 だが、このビルドは v89 を要する」 |
| 平文・古い | — | **78** | 同上 |
| 暗号化・古い | **渡さない** | **1** | 「版数を読めない … 鍵が渡されていない（--db-key / YU_DB_KEY）」 |
| 暗号化・最新 | **渡さない** | **1** | 同上——最新であることは見えないので変わらない |

つまり鍵の無い機械は 78 で止まらず、`RestartPreventExitStatus` にも掛かりません。systemd は `StartLimitBurst`（300 秒で 5 回）まで再試行して諦めます。これは正しい結末です——開けないデータベースは「古いと判明したデータベース」ではありません——が、「78 で止まる」は鍵を渡す機械だけの話だ、ということです。文言はどちらの場合も鍵の不在を名指します。いずれの場合も panic は起きません。

**oneshot にサーバーと同じデータベースを指させる。** 移行 unit がサーバーの開かないデータベースを移行しても、失敗には見えません——移行は 0 で終わり、サーバーは本物のデータベースに手を触れないまま 78 で止まります。`--lan` の unit は `--db` を渡さないため config の `db` が `YU_DB` に勝ちます（`crates/yu-server/src/main.rs` の `resolve_db_path`）。推測せずバイナリに訊いてください:

```sh
cd "$(systemctl --user show -p WorkingDirectory --value yu-server.service)"
~/.local/bin/yu-server --print-db-path
```

サーバーが動く場所で実行すること。答えは作業ディレクトリ（config.json をそこから読む）と環境に依存するので、別の場所で訊けば別の問いに答えます。何も開かず、何も作りません。得た値を oneshot の `--db` に渡します。両方の unit が argv でデータベースを名指す場合、その二値が一致することを `scripts/pre_push_check.py` が要求します。

**鍵に使える文字。** 空白と `' " ; \ & , } ]` は使えません。移行ツールは以前からこれを拒んでいましたが、サーバー側は拒んでいませんでした。そのため、これらを含む鍵は、起動はするのに二度と移行できないデータベースを作ってしまいました（`server.env.example` が指示している `openssl rand -hex 32` の出力は常に通ります）。v4.732.22 以降、サーバーはデータベースを**作成する**場面ではそうした鍵を拒み、既存のデータベースに対しては（停止せずに）警告します。そのデータベースは、移行の前に鍵を付け替える必要があります。

生成した鍵は Python バックエンドとも両立しません。Python の**サーバー**は環境から鍵を読まず、常に組み込みの鍵で接続を開くため、`YU_PYTHON_URL` を設定した配備は、そのデータベースをまったく開けないバックエンドを持つことになります。yu-server は起動時にそれを述べ、Python を移行器として数えるのをやめます——「古いデータベースを給仕する」が、いつもの exit 78（移行コマンド付き）に変わります。`YU_DB_KEY` を受け取るのは `scripts/migrate_db_cli.py` だけです。

### 自動化する

`deploy/yu-db-migrate.service` は、サーバーの起動前にそのコマンドを一度だけ実行します。無人の機械が人を待たずに復帰できるようにするためです:

```sh
install -m644 deploy/yu-db-migrate.service ~/.config/systemd/user/
sed -i "s|__SOURCE_DIR__|$PWD|; s|__UV__|$(command -v uv)|" \
  ~/.config/systemd/user/yu-db-migrate.service
systemctl --user daemon-reload
systemctl --user enable yu-db-migrate.service
```

いずれのプレースホルダも絶対パスに置換しなければなりません。systemd は `WorkingDirectory` 内の環境変数を展開しません。また `ExecStart` に裸のプログラム名を書くことは受け付けますが、`~/.local/bin` を**含まない**固定の PATH に対して解決するため、unit は検証をすり抜けたうえで `203/EXEC` で失敗します。

いずれのプレースホルダも未置換のまま残して安全です。その場合 `ConditionPathExists` が一致せず、systemd はこの unit を失敗ではなくスキップとして記録し、サーバーは従来どおり 78 で拒否します。`uv` を後から削除・移動した場合も同じです。この unit は インタプリタ自身も条件に挙げています——スクリプトだけを挙げていた時は条件を通過したうえで `203/EXEC` で死んでいました（実測）。Python ツリーの無い機械でも同じことが起こりますが、これは意図したものです。サーバー側の unit はこの unit を `Wants=` で束ねており、決して `Requires=` ではありません。移行の失敗やスキップが「データベースの移行が必要」を「依存関係が失敗」に置き換えてしまわないためです。

`TimeoutStartSec=1800` は意図的に余裕をもたせてあります。移行の鎖そのものは速く、スキーマだけ揃えた空のデータベースでの実測では v1 から v89 までおよそ 2.4 秒です。ただしこれは下限であって見積りではありません。所要時間の大半はデータを変換する 28 段が占めており、それは蔵書の量に比例します。下げる前に自分の環境で計測してください (`time uv run python scripts/migrate_db_cli.py …`)。途中で打ち切られた移行は、到達した段のまま台帳に残ります。

Python バックエンドを実際に併走させている場合は `server.env` に `YU_PYTHON_URL` を設定してください。これが移行主体の宣言となり、古いデータベースは拒否ではなく一度警告して配信を続けます。これが正しいのは、Python が本当にそこに居て移行を担える場合だけです。

その他の起動失敗には 5 分間で 5 回の試行が与えられます (`StartLimitBurst`/`StartLimitIntervalSec`)。移行中は書き込みロックが保持されるため、その最中の起動は失敗しますが、再試行で回復します。移行が 5 回の試行より長引いた場合 systemd は unit を failed と記録するので、`systemctl --user reset-failed yu-server` で解除してから起動し直してください。

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
