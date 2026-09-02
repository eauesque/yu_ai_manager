# YU AI Manager -- 部署指南

> **[English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-cn.md) | [한국어](README.ko.md)**

## 前置條件

- Docker Engine 20.10 或更新版本
- Docker Compose V2（`docker compose` 指令）
- 專案根目錄下的 `config.json` 檔案

## 快速開始

```bash
# 1. 在專案根目錄準備 config.json
cp config.json.example config.json
# 編輯 config.json（設定 pin、scan_roots 等）

# 2. 建立 data 目錄（僅首次需要）
mkdir -p data

# 3. 建置並啟動
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. 在瀏覽器中開啟
# http://localhost（當 NGINX_PORT=80 時）
```

## 停止 / 重新啟動

```bash
# 停止
docker compose -f deploy/docker-compose.prod.yml down

# 重新啟動（程式碼變更後）
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## 環境變數

將 `deploy/.env.example` 複製為 `deploy/.env`，並依需求進行編輯。

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `NGINX_PORT` | `80` | Nginx 在主機上公開的連接埠 |
| `UPSTREAM_HOST` | `app` | Flask 容器的主機名稱（通常無需更改） |
| `UPSTREAM_PORT` | `5000` | Flask 容器的連接埠（通常無需更改） |

## 磁碟區掛載

| 主機 | 容器 | 說明 |
|------|------|------|
| `data/` | `/app/data/` | 持久化 SQLite 資料庫（`tags.db`） |
| `config.json` | `/app/config.json` | 應用程式設定檔（唯讀） |
| `static/` | `/app/static/` | 由 Nginx 直接提供的靜態檔案 |

## PIN 認證（正式環境）

在區域網路中公開時，請在 `config.json` 中設定 PIN。若綁定至 `0.0.0.0` 但未設定 PIN，伺服器將拒絕啟動。

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

在 Docker 環境中，Nginx 作為前端，因此 Flask 始終監聽 `0.0.0.0:5000`。請透過 Nginx 的連接埠綁定來控制外部存取。

## SSL/TLS 終止（反向代理模式）

此 Nginx 設定僅提供 HTTP（連接埠 80）服務。若需 SSL/TLS，請使用以下其中一種方式。

### 方案一：在前方放置反向代理

```
[客戶端] --HTTPS--> [Cloudflare / Caddy / Traefik]
                              |
                          --HTTP--> [本 Nginx :80]
                                        |
                                    --> [Flask :5000]
```

### 方案二：直接在本 Nginx 中加入 SSL

編輯 `nginx.conf.template`，加入 `listen 443 ssl;` 及憑證路徑。通常會搭配 Let's Encrypt（certbot）使用。

## 反向代理設定（ProxyFix）

透過 Nginx 等反向代理存取時，請設定 `config.json`，以便應用程式正確識別客戶端 IP、協定及主機。

### 方案一：指定 trusted_proxy_ips（建議）

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

支援 CIDR 表示法。來自受信任 IP 的 `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Forwarded-Host` 標頭會自動處理。

### 方案二：behind_proxy 旗標（簡易）

```json
{
  "deploy": {
    "behind_proxy": true
  }
}
```

若未設定 `trusted_proxy_ips`，則僅信任回送位址（`127.0.0.1`、`::1`）。當代理在獨立容器中執行時（例如 Docker Compose），請使用方案一。

## 疑難排解

### 容器無法啟動

```bash
# 檢查日誌
docker compose -f deploy/docker-compose.prod.yml logs app
docker compose -f deploy/docker-compose.prod.yml logs nginx
```

### 資料庫檔案權限錯誤

請檢查 `data/` 目錄的權限。容器內的程序需要寫入權限。

```bash
chmod 777 data/
```

### 靜態檔案回傳 404

請確認已建置的 `static/dist/` 目錄存在。

```bash
# 在主機上建置
pnpm run build

# 或包含在 Docker 建置中
```

---

## WD-Tagger 遠端伺服器

用於在區域網路中多台機器上進行分散式標記的獨立推論伺服器。此腳本可獨立執行，不需要 YU AI Manager 主應用程式。

### 支援的後端

| 後端 | 執行環境 | 所需檔案 | 使用情境 |
|------|----------|----------|----------|
| `onnx` | CPU / CUDA / ROCm | `model.onnx` | 通用（可在任何機器上執行） |
| `hailo` | Hailo-10H NPU | `model.hef` | 在 Pi 5 + Hailo-10H 上進行高速推論 |
| `auto` | 優先 Hailo，回退至 ONNX | 兩者皆可或擇一 | 建議使用 |

### 設定方式

```bash
# 1. 安裝所需套件
pip install numpy Pillow

# ONNX 後端：
pip install onnxruntime          # CPU
pip install onnxruntime-gpu      # NVIDIA CUDA

# Hailo 後端：
# 從 Hailo Developer Zone 或原始碼安裝 hailo_platform wheel

# 2. 準備模型目錄
mkdir -p models/wd-swinv2-tagger-v3
# 從 HuggingFace 下載 model.onnx 及 selected_tags.csv：
#   https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
# 若使用 Hailo，另需放置 model.hef（使用 Dataflow Compiler 從 ONNX 轉換）

# 3. 啟動伺服器
python hailo_tagger_server.py --model-dir ./models/wd-swinv2-tagger-v3

# 明確指定後端：
python hailo_tagger_server.py --backend onnx --model-dir ./models/wd-swinv2-tagger-v3
python hailo_tagger_server.py --backend hailo --model-dir ./models/wd-swinv2-tagger-v3

# 使用認證權杖：
python hailo_tagger_server.py --token "my-secret" --model-dir ./models/wd-swinv2-tagger-v3

# 使用 JSON 設定檔：
python hailo_tagger_server.py --config tagger_config_example.json
```

### 設定檔範例（`tagger_config_example.json`）

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

### YU AI Manager 設定

在 YU AI Manager 主 WebUI 的 **Settings > Tagger** 分頁中註冊伺服器。

1. 「Add Server」> Type: `hailo_remote`
2. Endpoint URL: `http://<worker-ip>:8080`
3. Bearer Token:（僅在有設定時填寫）
4. Distribution mode: `parallel`（用於多機並行處理）

### API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/health` | GET | 伺服器狀態（後端、裝置、模型） |
| `/tag` | POST | 圖片標記（multipart/form-data，欄位：`image`） |

### 健康檢查範例

```bash
curl http://192.168.1.101:8080/health
# {"status": "idle", "backend": "onnx", "device": "onnx-cpu", "model": "wd-swinv2-tagger-v3", ...}
```

### 標記範例

```bash
curl -X POST http://192.168.1.101:8080/tag \
  -F "image=@test.png"
# {"tags": [{"tag": "1girl", "confidence": 0.97, "category": "general"}, ...], "elapsed_ms": 150}
```
