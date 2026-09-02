# Podman 设置

YU AI Manager 的容器环境同时支持 Docker 和 Podman。管理脚本（`scripts/yu-docker.sh`、`tools/docker-build.sh`）会自动检测已安装的运行时。

---

## 前提条件

- Podman 4.0 或更高版本
- `podman compose` 插件（Podman 4.7+）或 `podman-compose`（pip）

### 安装 Podman

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

### 安装 Compose 工具

要在 Podman 中使用 `docker-compose.yml`，需要以下工具之一：

```bash
# 方式 1：podman-compose（pip，轻量级）
uv pip install podman-compose

# 方式 2：podman compose 插件（Podman 4.7+）
# 可能已随 Podman 捆绑。检查：
podman compose version
```

---

## 基本用法

### 通过管理脚本（推荐）

脚本会自动检测 Docker 或 Podman，因此命令与 Docker 用法相同：

```bash
# 初始设置
./scripts/yu-docker.sh init

# 构建
./scripts/yu-docker.sh build

# 启动
./scripts/yu-docker.sh up

# 日志
./scripts/yu-docker.sh logs

# 停止
./scripts/yu-docker.sh down
```

### 直接命令

```bash
# 构建
podman build -t yu-ai-manager .

# 启动（compose）
podman compose up yu-ai-manager -d

# 启动（独立运行）
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo 变体构建
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## 与 Docker 的差异

### 无根模式

Podman 默认以无根模式（无 root 权限）运行。大多数情况下可直接使用，但请注意以下几点：

| 项目 | 影响 | 解决方案 |
|------|------|----------|
| 1024 以下端口 | 无根模式下无法绑定 | 无影响——本项目使用端口 5000 |
| 设备直通 | 访问 `/dev/hailort0` 等需要权限 | 使用 `podman run --device` 配合组权限，或 `sudo podman` |
| UID 映射 | 容器 `appuser` UID 与主机 UID 不同 | 使用 `podman unshare chown` 修复卷权限 |

```bash
# 检查 UID 映射
podman unshare cat /proc/self/uid_map

# 修复卷权限（示例）
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo 设备直通

```bash
# 无根模式可能无法访问 /dev/hailort0
# 方式 1：将用户添加到 hailort 组
sudo usermod -aG hailort $USER

# 方式 2：以有根模式运行
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### 网络

Podman 的默认网络名为 `podman`，等同于 Docker 的 `bridge`。`docker-compose.debug.yml` 中定义的自定义网络（如 `debug-net`）无需修改即可使用。

```bash
# 列出网络
podman network ls
```

### 卷

命名卷和绑定挂载均受支持。`docker-compose.yml` 中的绑定挂载（如 `./data:/app/data`）可直接使用。

### systemd 集成（Linux 服务器部署）

Podman 可轻松与 systemd 集成。配置自动启动：

```bash
# 启动容器后生成 systemd 单元
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# 启用
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# 启用开机自动启动用户服务（linger）
loginctl enable-linger $USER
```

---

## Docker CLI 兼容性别名（可选）

要直接使用面向 Docker 的文档和脚本：

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

管理脚本会自动检测运行时，因此这些别名不是必需的。

---

## 故障排除

### `WARN[0000] "/" is not a shared mount` 警告

```bash
# 无根 Podman 可能出现此警告。无害，但要抑制它：
podman system migrate
```

### 找不到 `podman compose`

```bash
# 4.7 之前的 Podman 版本不捆绑 compose 插件
# 通过 pip 安装 podman-compose
uv pip install podman-compose
```

### 无法从容器内部访问 localhost

无根 Podman 使用 `host.containers.internal`（等同于 Docker 的 `host.docker.internal`）。

```bash
# 从调试容器访问 Web 服务时，
# 使用 docker-compose.debug.yml 网络（http://web:5000）——无问题
```

### 镜像清理

```bash
# 删除未使用的镜像
podman image prune -a

# 删除所有资源
podman system prune -a
```

---

## 兼容性总结

| 文件 | Podman 兼容 | 备注 |
|------|-------------|------|
| `Dockerfile` | OK | 标准 OCI 规范 |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | 设备直通需要权限 |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | 自动检测运行时 |
| `scripts/yu-docker.sh` | OK | 自动检测运行时 |
| `.dockerignore` | OK | Podman 读取相同文件 |
