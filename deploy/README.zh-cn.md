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
