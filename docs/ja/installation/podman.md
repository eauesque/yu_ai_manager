# Podman でのセットアップ

YU AI Manager のコンテナ環境は Docker と Podman の両方に対応している。
管理スクリプト (`scripts/yu-docker.sh`, `tools/docker-build.sh`) はインストール済みのランタイムを自動検出する。

---

## 前提条件

- Podman 4.0 以上
- `podman compose` プラグイン（Podman 4.7+）または `podman-compose`（pip）

### Podman のインストール

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install podman

# Fedora
sudo dnf install podman

# macOS (Homebrew)
brew install podman
podman machine init
podman machine start
```

### Compose ツールのインストール

Podman で `docker-compose.yml` を使うには、以下のいずれかが必要。

```bash
# 方法 1: podman-compose (pip, 軽量)
uv pip install podman-compose

# 方法 2: podman compose プラグイン (Podman 4.7+)
# podman 本体に同梱されている場合あり。以下で確認:
podman compose version
```

---

## 基本的な使い方

### 管理スクリプト経由（推奨）

スクリプトが Docker / Podman を自動検出するため、コマンドは Docker の場合と同じ。

```bash
# 初回セットアップ
./scripts/yu-docker.sh init

# ビルド
./scripts/yu-docker.sh build

# 起動
./scripts/yu-docker.sh up

# ログ
./scripts/yu-docker.sh logs

# 停止
./scripts/yu-docker.sh down
```

### 直接コマンド

```bash
# ビルド
podman build -t yu-ai-manager .

# 起動 (compose)
podman compose up yu-ai-manager -d

# 起動 (単体)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo variant ビルド
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Docker との違いと注意点

### Rootless モード

Podman はデフォルトで rootless（root 権限なし）で動作する。
ほとんどのケースでそのまま動くが、以下の点に注意。

| 項目 | 影響 | 対処 |
|---|---|---|
| ポート 1024 未満 | rootless では bind 不可 | 5000 番を使うので問題なし |
| デバイスパススルー | `/dev/hailort0` 等のアクセスに権限が必要 | `podman run --device` + グループ権限、または `sudo podman` |
| UID マッピング | コンテナ内の `appuser` とホスト UID が異なる | ボリュームの権限問題が出たら `podman unshare chown` で修正 |

```bash
# UID マッピングの確認
podman unshare cat /proc/self/uid_map

# ボリュームの権限修正例
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo デバイスパススルー

```bash
# rootless では /dev/hailort0 にアクセスできない場合がある
# 方法 1: ユーザーを hailort グループに追加
sudo usermod -aG hailort $USER

# 方法 2: rootful で実行
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### ネットワーク

Podman のデフォルトネットワークは `podman` で、Docker の `bridge` と同等。
`docker-compose.debug.yml` のカスタムネットワーク (`debug-net`) もそのまま動作する。

```bash
# ネットワーク確認
podman network ls
```

### ボリューム

名前付きボリュームとバインドマウントの両方をサポート。
`docker-compose.yml` のバインドマウント (`./data:/app/data`) はそのまま使える。

### systemd 連携（Linux サーバー運用）

Podman は systemd との連携が容易。自動起動を設定するには:

```bash
# コンテナ起動後に systemd ユニットを生成
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# 有効化
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# マシン起動時にユーザーサービスも自動起動（linger）
loginctl enable-linger $USER
```

---

## Docker CLI 互換エイリアス（任意）

Docker 向けのドキュメントやスクリプトをそのまま使いたい場合:

```bash
# ~/.bashrc または ~/.zshrc に追加
alias docker=podman
alias docker-compose=podman-compose
```

管理スクリプトは自動検出するため、このエイリアスは必須ではない。

---

## トラブルシューティング

### `WARN[0000] "/" is not a shared mount` 警告

```bash
# rootless Podman で発生する場合がある。無害だが消したい場合:
podman system migrate
```

### `podman compose` が見つからない

```bash
# Podman 4.7 未満の場合、プラグインが同梱されていない
# podman-compose を pip でインストールする
uv pip install podman-compose
```

### コンテナ内から localhost にアクセスできない

Podman rootless では `host.containers.internal` を使う（Docker の `host.docker.internal` に相当）。

```bash
# debug コンテナから web サービスにアクセスする場合は
# docker-compose.debug.yml のネットワーク経由 (http://web:5000) を使うので問題なし
```

### イメージのクリーンアップ

```bash
# 未使用イメージの削除
podman image prune -a

# 全リソースの削除
podman system prune -a
```

---

## 対応状況まとめ

| ファイル | Podman 互換 | 備考 |
|---|---|---|
| `Dockerfile` | OK | 標準 OCI 仕様 |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | デバイスパススルーは権限注意 |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | ランタイム自動検出 |
| `scripts/yu-docker.sh` | OK | ランタイム自動検出 |
| `.dockerignore` | OK | Podman も同じファイルを参照 |
