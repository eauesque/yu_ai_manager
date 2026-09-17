# Podman 設定

YU AI Manager 的容器環境同時支援 Docker 和 Podman。管理指令碼（`scripts/yu-docker.sh`、`tools/docker-build.sh`）會自動偵測已安裝的執行環境。

---

## 先決條件

- Podman 4.0 或更高版本
- `podman compose` 外掛（Podman 4.7+）或 `podman-compose`（pip）

### 安裝 Podman

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

### 安裝 Compose 工具

要在 Podman 中使用 `docker-compose.yml`，需要以下工具之一：

```bash
# 方式 1：podman-compose（pip，輕量級）
uv pip install podman-compose

# 方式 2：podman compose 外掛（Podman 4.7+）
# 可能已隨 Podman 捆綁。檢查：
podman compose version
```

---

## 基本用法

### 透過管理指令碼（建議）

指令碼會自動偵測 Docker 或 Podman，因此命令與 Docker 用法相同：

```bash
# 初始設定
./scripts/yu-docker.sh init

# 建置
./scripts/yu-docker.sh build

# 啟動
./scripts/yu-docker.sh up

# 記錄檔
./scripts/yu-docker.sh logs

# 停止
./scripts/yu-docker.sh down
```

### 直接命令

```bash
# 建置
podman build -t yu-ai-manager .

# 啟動（compose）
podman compose up yu-ai-manager -d

# 啟動（獨立執行）
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo 變體建置
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## 與 Docker 的差異

### 無根模式

Podman 預設以無根模式（無 root 權限）執行。大多數情況下可直接使用，但請注意以下幾點：

| 項目 | 影響 | 解決方案 |
|------|------|----------|
| 1024 以下連接埠 | 無根模式下無法繫結 | 無影響——本專案使用連接埠 5000 |
| 裝置直通 | 存取 `/dev/hailort0` 等需要權限 | 使用 `podman run --device` 搭配群組權限，或 `sudo podman` |
| UID 對應 | 容器 `appuser` UID 與主機 UID 不同 | 使用 `podman unshare chown` 修復磁碟區權限 |

```bash
# 檢查 UID 對應
podman unshare cat /proc/self/uid_map

# 修復磁碟區權限（範例）
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo 裝置直通

```bash
# 無根模式可能無法存取 /dev/hailort0
# 方式 1：將使用者加入 hailort 群組
sudo usermod -aG hailort $USER

# 方式 2：以有根模式執行
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### 網路

Podman 的預設網路名為 `podman`，等同於 Docker 的 `bridge`。`docker-compose.debug.yml` 中定義的自訂網路（如 `debug-net`）無需修改即可使用。

```bash
# 列出網路
podman network ls
```

### 磁碟區

具名磁碟區和繫結掛載均受支援。`docker-compose.yml` 中的繫結掛載（如 `./data:/app/data`）可直接使用。

### systemd 整合（Linux 伺服器部署）

Podman 可輕鬆與 systemd 整合。設定自動啟動：

```bash
# 啟動容器後產生 systemd 單元
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# 啟用
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# 啟用開機自動啟動使用者服務（linger）
loginctl enable-linger $USER
```

---

## Docker CLI 相容性別名（選用）

要直接使用面向 Docker 的文件和指令碼：

```bash
# 加入 ~/.bashrc 或 ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

管理指令碼會自動偵測執行環境，因此這些別名不是必要的。

---

## 疑難排解

### `WARN[0000] "/" is not a shared mount` 警告

```bash
# 無根 Podman 可能出現此警告。無害，但要抑制它：
podman system migrate
```

### 找不到 `podman compose`

```bash
# 4.7 之前的 Podman 版本不捆綁 compose 外掛
# 透過 pip 安裝 podman-compose
uv pip install podman-compose
```

### 無法從容器內部存取 localhost

無根 Podman 使用 `host.containers.internal`（等同於 Docker 的 `host.docker.internal`）。

```bash
# 從除錯容器存取 Web 服務時，
# 使用 docker-compose.debug.yml 網路（http://web:5000）——無問題
```

### 映像清理

```bash
# 刪除未使用的映像
podman image prune -a

# 刪除所有資源
podman system prune -a
```

---

## 相容性總結

| 檔案 | Podman 相容 | 備註 |
|------|-------------|------|
| `Dockerfile` | OK | 標準 OCI 規格 |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | 裝置直通需要權限 |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | 自動偵測執行環境 |
| `scripts/yu-docker.sh` | OK | 自動偵測執行環境 |
| `.dockerignore` | OK | Podman 讀取相同檔案 |
