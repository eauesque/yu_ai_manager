# 部署与运维指南

汇整在生产环境中运维 YU AI Manager 的步骤。

## 1. 概述

运维模式主要有 3 种。

| 模式 | 用途 | 架构 |
|---------|------|------|
| 直接执行 | 个人使用、开发 | 以 Python + venv 启动 |
| Docker | 服务器运维 | 以 docker-compose 运行 Quart + Nginx |
| 反向代理 | 对外公开 | 放置在现有 Web 服务器背后 |

无论哪种方式，数据均存储于 `data/tags.db` (SQLite)。不需要外部 DB 服务器。

---

## 2. 直接执行（开发、个人使用）

### 设置

```bash
# 获取仓库
git clone <repository-url> && cd yu_ai_manager

# 创建 Python 虚拟环境
python -m venv venv

# 激活虚拟环境
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# 安装依赖包
uv pip install -r requirements.txt

# 构建前端
pnpm install && pnpm run build

# 启动
python web_ui.py --db data/tags.db
```

请在浏览器中打开 `http://localhost:5000`。

### 通过 launch-args.txt 设置参数

将 `launch-args.txt.example` 复制为 `launch-args.txt` 并编辑，可固定启动时的参数。CLI 参数优先。

```txt
# 变更端口
--port 5100
# LAN 公开（绑定 0.0.0.0）
--lan
# PIN 认证
--pin 1234
```

### systemd 服务化 (Linux)

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

### Windows 服务化

将 `start.bat` 注册到任务计划程序是最简单的方式。请设为「登录时执行」。

---

## 3. Docker 部署

### 快速开始

```bash
# 准备配置文件
cp config.json.example config.json
# 编辑 config.json（pin、scan_roots 等）

mkdir -p data

# 构建及启动
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

可通过 `http://localhost` 访问（经由 Nginx）。

### docker-compose.prod.yml 的架构

- **app**：Quart 应用程序（端口 5000，仅限内部）
- **nginx**：反向代理（对外公开端口 80）

### 卷挂载

| 主机 | 容器 | 用途 |
|-------|---------|------|
| `data/` | `/app/data/` | DB 文件的持久化 |
| `config.json` | `/app/config.json` | 配置文件（只读） |
| `static/` | `/app/static/` | Nginx 直接分发的静态文件 |

图片文件夹请追加挂载 `config.json` 的 `scan_roots` 中指定的路径。

```yaml
# 在 docker-compose.prod.yml 中追加
volumes:
  - /path/to/images:/images:ro
```

### 环境变量

将 `deploy/.env.example` 复制为 `deploy/.env` 并编辑。

| 变量 | 默认值 | 说明 |
|------|----------|------|
| `NGINX_PORT` | `80` | Nginx 的公开端口 |
| `UPSTREAM_HOST` | `app` | Quart 容器名称（无需变更） |
| `UPSTREAM_PORT` | `5000` | Quart 端口（无需变更） |

### 使用 Podman 时

也可使用 Podman 代替 Docker。安装 `podman compose` 或 `podman-compose` 后使用相同命令。详情请参阅 `docs/en/installation/podman.md`。

---

## 4. 反向代理设置

### Nginx 设置要点

`deploy/nginx.conf.template` 包含实用的设置。要点如下。

- **静态文件**：`/static/` 由 Nginx 直接分发（绕过 Quart）
- **SSE**：`/api/events/` 以 `proxy_buffering off` 禁用缓冲
- **上传上限**：`client_max_body_size 100m`（与 Quart 端一致）
- **Gzip**：压缩 JSON、CSS、JS

### SSL/TLS (Let's Encrypt)

Docker 架构的 Nginx 仅支持 HTTP。需要 HTTPS 时有 2 种方法。

**方法 1：前端代理（推荐）**

将 Cloudflare、Caddy、Traefik 等放在前端，进行 HTTPS 终端处理。

```
客户端 --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**方法 2：直接在 Nginx 加入 SSL**

在 `nginx.conf.template` 中加入 `listen 443 ssl;` 和证书路径，以 certbot 获取 Let's Encrypt 证书。

### Trusted Proxy 设置

通过反向代理时，请在 `config.json` 中指定信任的 IP。

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

借此可正确处理 `X-Forwarded-For` / `X-Forwarded-Proto` 头。支持 CIDR 表示法。

---

## 5. 认证设置

可使用 4 种认证方式。请根据用途组合使用。

### PIN 认证（浏览器访问用）

```json
{ "pin": "your-secret-pin" }
```

在 LAN 上公开时（`--lan` 或绑定 `0.0.0.0`），PIN 设置为必需项。未设置 PIN 而绑定 `0.0.0.0` 时，启动将被拒绝。

### API 密钥认证（程序访问用）

在 Settings 界面发放 API 密钥，并附加到请求头。

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

使用 API 密钥认证时不需要 CSRF 头 (`X-Requested-With`)。

### Trusted Proxy 认证

适用于反向代理附加 `X-Remote-User` 头的架构。需要设置 `trusted_proxy_ips`。

### LAN 共享模式

可通过 `/s/` 路径发放访客用的共享链接。跳过 PIN，以令牌进行个别认证。

---

## 6. 备份与恢复

应定期备份的文件有以下 3 种。

| 文件 | 内容 |
|---------|------|
| `data/tags.db` | 包含所有元数据、标签、设置的 SQLite DB |
| `config.json` | 应用程序设置 |
| `data/secret.key`, `data/secret.salt` | 加密密钥（用于设置的加密） |

### 备份步骤

```bash
# 复制 DB（运行中也安全）
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# 设置和加密密钥
cp config.json data/secret.key data/secret.salt backup/
```

### 恢复步骤

只需将备份文件放回原始位置并重新启动服务器。DB 迁移会在启动时自动应用。

若丢失加密密钥 (`secret.key`, `secret.salt`)，已加密的设置值（API 凭据等）将无法解密。请务必备份。

---

## 7. 升级步骤

```bash
# 1. 停止服务器
# 2. 更新代码
git pull

# 3. 更新依赖包
source venv/bin/activate  # 或 .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. 重新构建前端
pnpm install && pnpm run build

# 5. 启动服务器
python web_ui.py --db data/tags.db
```

DB 模式的迁移会在启动时自动执行。无需手动操作。

使用 Docker 时只需重新构建即可。

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. 监控与日志

### 日志流

可在 Settings > Logs 选项卡确认实时日志。通过 SSE (`/api/logs/stream`) 流式传输至浏览器。

过往日志可通过 `/api/logs/recent` 获取。

### 健康检查

可通过 `/api/server-info` 端点确认运行状态。

```bash
curl http://localhost:5000/api/server-info
```

会返回版本、DB 模式版本、时区等信息。监控工具的健康检查请使用此端点。

### 通过 MCP 诊断

从 MCP 客户端（Claude Desktop 等）调用 `debug_health_check` 工具，可一次执行 DB 完整性检查、搜索动作确认、计数验证。
