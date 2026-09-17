# YU AI Manager -- 部署指南

> **[English](README.md) | [日本語](README.ja.md) | [繁體中文](README.zh-tw.md) | [한국어](README.ko.md)**

## 前提条件

- Docker Engine 20.10 或更高版本
- Docker Compose V2（`docker compose` 命令）
- 项目根目录下的 `config.json` 文件

## 快速开始

```bash
# 1. 在项目根目录准备 config.json
cp config.json.example config.json
# 编辑 config.json（设置 pin、scan_roots 等）

# 2. 创建 data 目录（仅首次需要）
mkdir -p data

# 3. 构建并启动
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. 在浏览器中打开
# http://localhost（当 NGINX_PORT=80 时）
```

## 停止 / 重启

```bash
# 停止
docker compose -f deploy/docker-compose.prod.yml down

# 重启（代码变更后）
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## 环境变量

将 `deploy/.env.example` 复制为 `deploy/.env`，根据需要进行编辑。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NGINX_PORT` | `80` | Nginx 在宿主机上暴露的端口 |
| `UPSTREAM_HOST` | `app` | Flask 容器的主机名（通常无需修改） |
| `UPSTREAM_PORT` | `5000` | Flask 容器的端口（通常无需修改） |

## 卷挂载

| 宿主机 | 容器 | 说明 |
|--------|------|------|
| `data/` | `/app/data/` | 持久化 SQLite 数据库（`tags.db`） |
| `config.json` | `/app/config.json` | 应用配置文件（只读） |
| `static/` | `/app/static/` | 由 Nginx 直接提供的静态文件 |

### 服务器启动前数据目录必须存在

由部署人员创建；服务器不会创建。在独立模式下，yu-server 在缺少 `tags.db` 时会自动创建，但**故意不会**创建保存它的目录：因为如果 `--db` 路径输入错误，会生成一个空的新库，看起来和丢失的库完全一样。如果目录不存在，服务器将在启动时拒绝启动，并显示已解析的绝对路径。

Docker 用户可从快速开始中的 `mkdir -p data` 获得此操作。对于 `deploy/yu-server.service`，包含 `${YU_DB}` 的目录必须已经存在。`deploy/systemd/yu-server.service` 从 `WorkingDirectory` 以相对默认值 `data/tags.db` 运行，因此在该目录下创建 `data/`。桌面版本会自动处理此事项 (`src-tauri/src/app_dirs.rs::ensure_data_dir`)。

独立模式还需要 `--db-key`（或 `YU_DB_KEY`）：服务器没有默认密钥，并且拒绝创建未加密的数据库，因为 Python 版本无条件地通过 SQLCipher 打开 `tags.db`，但永远无法打开纯文本文件。

### 比二进制文件更旧的数据库

当数据库的架构版本低于二进制文件所期望的版本，且没有任何地方声明能够执行迁移的 Python 后端时，yu-server 以 **78** 退出。重试无济于事，因此 `RestartPreventExitStatus=78` 会阻止 systemd 重试。

### 执行迁移

针对该服务所使用的数据库运行迁移工具：

```sh
cd /path/to/yu_ai_manager
YU_DB_KEY='<the key from server.env>' \
  uv run python scripts/migrate_db_cli.py --db /path/to/data/tags.db
```

它只做迁移：不会创建数据库（报告架构版本为 0 的文件会被拒绝），不读取 `config.json`，并且在无法取得迁移前备份时默认拒绝迁移。退出码为 `0` 已是最新或迁移成功、`1` 迁移失败、`3` 无法备份、`4` 无法打开数据库（密钥错误、损坏、权限）、`5` 版本为 0、`6` 另一个进程持有写锁。

**密钥是关键。** 在 v4.730.3 之前，Python 侧只能打开用其内置密钥加密的数据库。也就是说，凡是自行生成 `YU_DB_KEY` 的服务——而 `ExecStartPre` 正要求你这么做——根本无法从 Python 迁移。传入 `--db-key` 或设置 `YU_DB_KEY` 即可迁移。

**78 的前提是版本号读得出来。** 一个根本打不开的数据库是另一种结局——用真实二进制对落后一个版本的加密数据库实测:

| 数据库 | 是否给密钥 | 退出码 | 提示 |
|---|---|---|---|
| 加密、落后 | 给 | **78** | "schema v88，而本构建需要 v89" |
| 明文、落后 | — | **78** | 同上 |
| 加密、落后 | **不给** | **1** | "读不出版本号 … 未提供密钥（--db-key / YU_DB_KEY）" |
| 加密、最新 | **不给** | **1** | 同上——"最新"它根本看不见 |

也就是说，没有密钥的机器不会停在 78，也不受 `RestartPreventExitStatus` 约束：systemd 会重试到 `StartLimitBurst`（300 秒内 5 次）才放弃。这个结局是对的——打不开的数据库并不等于已证实落后的数据库——但"停在 78"只适用于传入密钥的机器。两种情况下提示都会指出密钥缺失。以上各例均不会 panic。

**让 oneshot 指向服务器实际打开的那个数据库。** 迁移了服务器并不打开的数据库，看起来并不像失败——迁移以 0 结束，而服务器仍以 78 停止，真正的数据库分毫未动。`--lan` 的 unit 不传 `--db`，因此 config 的 `db` 胜过 `YU_DB`（见 `crates/yu-server/src/main.rs` 的 `resolve_db_path`）。不要猜，直接问二进制：

```sh
cd "$(systemctl --user show -p WorkingDirectory --value yu-server.service)"
~/.local/bin/yu-server --print-db-path
```

要在服务器运行的位置执行：答案取决于工作目录（config.json 从那里读取）与环境，换个地方问就是另一个问题。它不打开也不创建任何东西。把结果交给 oneshot 的 `--db`。当两个 unit 都在 argv 上指定数据库时，`scripts/pre_push_check.py` 要求两者完全一致。

**密钥可以包含什么。** 不能包含空白字符，也不能包含 `' " ; \ & , } ]` 中的任何一个。迁移工具一直在拒绝它们，而服务器此前不拒绝，因此含有这些字符的密钥会造出一个能正常启动却永远无法迁移的数据库（`server.env.example` 指定的 `openssl rand -hex 32` 的输出始终合规）。自 v4.732.22 起，服务器在**创建**数据库时会拒绝这样的密钥；若数据库已存在，则只发出警告而不停止——该数据库必须先更换密钥才能迁移。

自行生成的密钥同样无法与 Python 后端共存。Python **服务器**不从环境读取密钥——它始终以内置密钥打开连接——因此设置了 `YU_PYTHON_URL` 的部署，其后端根本打不开这个数据库。yu-server 会在启动时说明这一点，并不再把 Python 计为迁移器：于是"提供陈旧的数据库"变回常规的 exit 78 并附上迁移命令。只有 `scripts/migrate_db_cli.py` 接受 `YU_DB_KEY`。

### 自动执行

`deploy/yu-db-migrate.service` 会在服务器启动前执行该命令一次，使无人值守的机器无需等人即可恢复：

```sh
install -m644 deploy/yu-db-migrate.service ~/.config/systemd/user/
sed -i "s|__SOURCE_DIR__|$PWD|; s|__UV__|$(command -v uv)|" \
  ~/.config/systemd/user/yu-db-migrate.service
systemctl --user daemon-reload
systemctl --user enable yu-db-migrate.service
```

两个占位符都必须替换为绝对路径。systemd 不会展开 `WorkingDirectory` 中的环境变量；而且虽然它接受 `ExecStart` 中的裸程序名，却是针对**不包含** `~/.local/bin` 的固定 PATH 解析的——该 unit 会通过校验，然后以 `203/EXEC` 失败。

保留任一未替换的占位符都是安全的：此时 `ConditionPathExists` 不匹配，systemd 会将该 unit 记为跳过而非失败，服务器的行为与此前完全相同——以 78 拒绝。日后删除或移动 `uv` 亦然。该 unit 把解释器本身也列为条件——仅列出脚本时，它会通过条件而后以 `203/EXEC` 死掉（实测）。在没有 Python 树的机器上也会如此，这是刻意为之：服务器 unit 以 `Wants=` 而绝非 `Requires=` 关联此 unit，以免迁移的失败或跳过把"数据库需要迁移"替换成"依赖失败"。

`TimeoutStartSec=1800` 有意留得宽裕。迁移链本身很快——在仅有架构、没有数据的数据库上实测，v1 到 v89 约需 2.4 秒——但这是下限而非估计值：大部分开销来自转换数据的 28 个步骤，而那与你的藏书量成正比。下调之前请测量你自己的情况（`time uv run python scripts/migrate_db_cli.py …`）。中途被终止的迁移会把台账停留在它到达的那一步。

如果你确实同时运行 Python 后端，请在 `server.env` 中设置 `YU_PYTHON_URL`。这声明了迁移主体，过旧的数据库便会警告一次并继续提供服务，而非拒绝启动——仅当 Python 确实在场时这才正确。

其他启动失败会获得五分钟内五次尝试（`StartLimitBurst`/`StartLimitIntervalSec`）。迁移进行中会持有写锁，因此期间的启动会失败，但重试即可恢复。若迁移超过五次尝试的时长，systemd 会将该 unit 标记为 failed——请先用 `systemctl --user reset-failed yu-server` 清除，再重新启动。

## PIN 认证（生产环境）

在局域网中暴露服务时，请在 `config.json` 中设置 PIN。如果绑定到 `0.0.0.0` 但未设置 PIN，服务器将拒绝启动。

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

在 Docker 环境中，Nginx 作为前端代理，因此 Flask 始终监听 `0.0.0.0:5000`。通过 Nginx 的端口绑定来控制外部访问。

## SSL/TLS 终止（反向代理模式）

此 Nginx 配置仅提供 HTTP 服务（端口 80）。如需 SSL/TLS，请使用以下方式之一。

### 方式 1：在前端放置反向代理

```
[客户端] --HTTPS--> [Cloudflare / Caddy / Traefik]
                              |
                          --HTTP--> [本 Nginx :80]
                                        |
                                    --> [Flask :5000]
```

### 方式 2：直接在本 Nginx 中添加 SSL

编辑 `nginx.conf.template`，添加 `listen 443 ssl;` 及证书路径。常见做法是集成 Let's Encrypt（certbot）。

## 反向代理设置（ProxyFix）

通过 Nginx 等反向代理访问时，需要配置 `config.json` 以使应用正确识别客户端 IP、协议和主机名。

### 方式 1：指定 trusted_proxy_ips（推荐）

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

支持 CIDR 表示法。来自受信任 IP 的 `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Forwarded-Host` 头将被自动处理。

### 方式 2：behind_proxy 标志（简单）

```json
{
  "deploy": {
    "behind_proxy": true
  }
}
```

如果未设置 `trusted_proxy_ips`，则仅信任回环地址（`127.0.0.1`、`::1`）。当代理运行在独立容器中时（例如 Docker Compose），请使用方式 1。

## 故障排除

### 容器无法启动

```bash
# 查看日志
docker compose -f deploy/docker-compose.prod.yml logs app
docker compose -f deploy/docker-compose.prod.yml logs nginx
```

### 数据库文件权限错误

请检查 `data/` 目录的权限。容器内的进程需要写入权限。

```bash
chmod 777 data/
```

### 静态文件返回 404

请确认构建后的 `static/dist/` 目录存在。

```bash
# 在宿主机上构建
pnpm run build

# 或在 Docker 构建中包含
```

---

## WD-Tagger 远程服务器

这是一个独立的推理服务器，用于在局域网内多台机器间进行分布式标签处理。此脚本独立运行，不依赖 YU AI Manager 主应用。

### 支持的后端

| 后端 | 运行环境 | 所需文件 | 适用场景 |
|------|----------|----------|----------|
| `onnx` | CPU / CUDA / ROCm | `model.onnx` | 通用（可在任何机器上运行） |
| `hailo` | Hailo-10H NPU | `model.hef` | Pi 5 + Hailo-10H 高速推理 |
| `auto` | 优先 Hailo，回退到 ONNX | 两者皆有或任一 | 推荐 |

### 安装

```bash
# 1. 安装所需的包
pip install numpy Pillow

# ONNX 后端：
pip install onnxruntime          # CPU
pip install onnxruntime-gpu      # NVIDIA CUDA

# Hailo 后端：
# 从 Hailo Developer Zone 或源码安装 hailo_platform wheel

# 2. 准备模型目录
mkdir -p models/wd-swinv2-tagger-v3
# 从 HuggingFace 下载 model.onnx 和 selected_tags.csv：
#   https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
# 如果使用 Hailo，还需放置 model.hef（使用 Dataflow Compiler 从 ONNX 转换）

# 3. 启动服务器
python hailo_tagger_server.py --model-dir ./models/wd-swinv2-tagger-v3

# 显式指定后端：
python hailo_tagger_server.py --backend onnx --model-dir ./models/wd-swinv2-tagger-v3
python hailo_tagger_server.py --backend hailo --model-dir ./models/wd-swinv2-tagger-v3

# 使用认证令牌：
python hailo_tagger_server.py --token "my-secret" --model-dir ./models/wd-swinv2-tagger-v3

# 使用 JSON 配置文件：
python hailo_tagger_server.py --config tagger_config_example.json
```

### 配置文件示例（`tagger_config_example.json`）

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

### YU AI Manager 配置

在 YU AI Manager 主 WebUI 的 **Settings > Tagger** 标签页中注册服务器。

1. "Add Server" > Type: `hailo_remote`
2. Endpoint URL: `http://<worker-ip>:8080`
3. Bearer Token:（仅在配置了令牌时需要）
4. Distribution mode: `parallel`（用于多机并行处理）

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 服务器状态（后端、设备、模型） |
| `/tag` | POST | 图像标签处理（multipart/form-data，字段：`image`） |

### 健康检查示例

```bash
curl http://192.168.1.101:8080/health
# {"status": "idle", "backend": "onnx", "device": "onnx-cpu", "model": "wd-swinv2-tagger-v3", ...}
```

### 标签处理示例

```bash
curl -X POST http://192.168.1.101:8080/tag \
  -F "image=@test.png"
# {"tags": [{"tag": "1girl", "confidence": 0.97, "category": "general"}, ...], "elapsed_ms": 150}
```
