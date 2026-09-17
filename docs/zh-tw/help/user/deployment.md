# 部署與運維指南

彙整在正式環境中運維 YU AI Manager 的步驟。

## 1. 概述

運維模式主要有 3 種。

| 模式 | 用途 | 架構 |
|---------|------|------|
| 直接執行 | 個人使用、開發 | 以 Python + venv 啟動 |
| Docker | 伺服器運維 | 以 docker-compose 執行 Quart + Nginx |
| 反向代理 | 對外公開 | 放置在現有 Web 伺服器背後 |

無論哪種方式，資料均儲存於 `data/tags.db` (SQLite)。不需要外部 DB 伺服器。

---

## 2. 直接執行（開發、個人使用）

### 設定

```bash
# 取得儲存庫
git clone <repository-url> && cd yu_ai_manager

# 建立 Python 虛擬環境
python -m venv venv

# 啟用虛擬環境
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# 安裝相依套件
uv pip install -r requirements.txt

# 建置前端
pnpm install && pnpm run build

# 啟動
python web_ui.py --db data/tags.db
```

請在瀏覽器中開啟 `http://localhost:5000`。

### 透過 launch-args.txt 設定引數

將 `launch-args.txt.example` 複製為 `launch-args.txt` 並編輯，可固定啟動時的引數。CLI 引數優先。

```txt
# 變更連接埠
--port 5100
# LAN 公開（綁定 0.0.0.0）
--lan
# PIN 認證
--pin 1234
```

### systemd 服務化 (Linux)

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

### Windows 服務化

將 `start.bat` 註冊到工作排程器是最簡單的方式。請設為「登入時執行」。

---

## 3. Docker 部署

### 快速開始

```bash
# 準備設定檔
cp config.json.example config.json
# 編輯 config.json（pin、scan_roots 等）

mkdir -p data

# 建置及啟動
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

可透過 `http://localhost` 存取（經由 Nginx）。

### docker-compose.prod.yml 的架構

- **app**：Quart 應用程式（連接埠 5000，僅限內部）
- **nginx**：反向代理（對外公開連接埠 80）

### 磁碟區掛載

| 主機 | 容器 | 用途 |
|-------|---------|------|
| `data/` | `/app/data/` | DB 檔案的持久化 |
| `config.json` | `/app/config.json` | 設定檔（唯讀） |
| `static/` | `/app/static/` | Nginx 直接配送的靜態檔案 |

圖片資料夾請追加掛載 `config.json` 的 `scan_roots` 中指定的路徑。

```yaml
# 在 docker-compose.prod.yml 中追加
volumes:
  - /path/to/images:/images:ro
```

### 環境變數

將 `deploy/.env.example` 複製為 `deploy/.env` 並編輯。

| 變數 | 預設值 | 說明 |
|------|----------|------|
| `NGINX_PORT` | `80` | Nginx 的公開連接埠 |
| `UPSTREAM_HOST` | `app` | Quart 容器名稱（無需變更） |
| `UPSTREAM_PORT` | `5000` | Quart 連接埠（無需變更） |

### 使用 Podman 時

也可使用 Podman 代替 Docker。安裝 `podman compose` 或 `podman-compose` 後使用相同指令。詳情請參閱 `docs/en/installation/podman.md`。

---

## 4. 反向代理設定

### Nginx 設定要點

`deploy/nginx.conf.template` 包含實用的設定。要點如下。

- **靜態檔案**：`/static/` 由 Nginx 直接配送（繞過 Quart）
- **SSE**：`/api/events/` 以 `proxy_buffering off` 停用緩衝
- **上傳上限**：`client_max_body_size 100m`（與 Quart 端一致）
- **Gzip**：壓縮 JSON、CSS、JS

### SSL/TLS (Let's Encrypt)

Docker 架構的 Nginx 僅支援 HTTP。需要 HTTPS 時有 2 種方法。

**方法 1：前端代理（建議）**

將 Cloudflare、Caddy、Traefik 等放在前端，進行 HTTPS 終端處理。

```
用戶端 --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**方法 2：直接在 Nginx 加入 SSL**

在 `nginx.conf.template` 中加入 `listen 443 ssl;` 和憑證路徑，以 certbot 取得 Let's Encrypt 憑證。

### Trusted Proxy 設定

透過反向代理時，請在 `config.json` 中指定信任的 IP。

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

藉此可正確處理 `X-Forwarded-For` / `X-Forwarded-Proto` 標頭。支援 CIDR 表示法。

---

## 5. 認證設定

可使用 4 種認證方式。請根據用途組合使用。

### PIN 認證（瀏覽器存取用）

```json
{ "pin": "your-secret-pin" }
```

在 LAN 上公開時（`--lan` 或綁定 `0.0.0.0`），PIN 設定為必要項目。未設定 PIN 而綁定 `0.0.0.0` 時，啟動將被拒絕。

### API 金鑰認證（程式存取用）

在 Settings 畫面發行 API 金鑰，並附加到請求標頭。

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

使用 API 金鑰認證時不需要 CSRF 標頭 (`X-Requested-With`)。

### Trusted Proxy 認證

適用於反向代理附加 `X-Remote-User` 標頭的架構。需要設定 `trusted_proxy_ips`。

### LAN 共享模式

可透過 `/s/` 路徑發行訪客用的共享連結。跳過 PIN，以權杖進行個別認證。

---

## 6. 備份與復原

應定期備份的檔案有以下 3 種。

| 檔案 | 內容 |
|---------|------|
| `data/tags.db` | 包含所有元資料、標籤、設定的 SQLite DB |
| `config.json` | 應用程式設定 |
| `data/secret.key`, `data/secret.salt` | 加密金鑰（用於設定的加密） |

### 備份步驟

```bash
# 複製 DB（運行中也安全）
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# 設定和加密金鑰
cp config.json data/secret.key data/secret.salt backup/
```

### 復原步驟

只需將備份檔案放回原始位置並重新啟動伺服器。DB 遷移會在啟動時自動套用。

若遺失加密金鑰 (`secret.key`, `secret.salt`)，已加密的設定值（API 憑證等）將無法解密。請務必備份。

---

## 7. 升級步驟

```bash
# 1. 停止伺服器
# 2. 更新程式碼
git pull

# 3. 更新相依套件
source venv/bin/activate  # 或 .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. 重新建置前端
pnpm install && pnpm run build

# 5. 啟動伺服器
python web_ui.py --db data/tags.db
```

DB 結構描述的遷移會在啟動時自動執行。無需手動操作。

使用 Docker 時只需重新建置即可。

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. 監控與日誌

### 日誌串流

可在 Settings > Logs 分頁確認即時日誌。透過 SSE (`/api/logs/stream`) 串流至瀏覽器。

過往日誌可透過 `/api/logs/recent` 取得。

### 健康檢查

可透過 `/api/server-info` 端點確認運行狀態。

```bash
curl http://localhost:5000/api/server-info
```

會回傳版本、DB 結構描述版本、時區等資訊。監控工具的健康檢查請使用此端點。

### 透過 MCP 診斷

從 MCP 用戶端（Claude Desktop 等）呼叫 `debug_health_check` 工具，可一次執行 DB 完整性檢查、搜尋動作確認、計數驗證。
