# 設定

## 伺服器設定

| 項目 | 說明 |
|------|------|
| Host | 綁定位址（LAN OFF 時固定為 127.0.0.1） |
| Port | Web 伺服器連接埠號 |
| LAN Access | 開啟後可從 LAN 內的其他裝置存取 |
| PIN Auth | 存取時要求輸入 PIN |
| Boss Mode | 報紙風格的 PIN 登入畫面 |

## 掃描設定

新增、刪除、排序掃描資料夾，以及切換啟用/停用。

## 解析器設定

| 項目 | 說明 |
|------|------|
| Extract A1111 | 擷取 Stable Diffusion WebUI 格式的元資料 |
| Extract ComfyUI | 擷取 ComfyUI 工作流程元資料 |
| Normalize tags | 將標籤統一為小寫 |
| Compute hash | 計算檔案雜湊值（用於重複偵測） |
| FTS | 啟用全文搜尋索引 |

## API 金鑰

管理外部工具（MCP 伺服器、指令碼、代理程式）用的 API 金鑰。
以 Bearer 認證方式使用。

## 外觀

佈景主題、強調色、背景圖片、音效等自訂設定。

## 加密密鑰儲存區

PIN、Bluesky 密碼、Webhook 密鑰等機密值以 `cryptography` 套件的 Fernet 加密保護。

- **加密格式**：帶有 `enc:` 前綴的字串
- **相容性**：現有明文值可正常運作（僅在新儲存時加密）
- **安裝**：`uv pip install cryptography`（未安裝時加密功能將停用）

### 金鑰後端

加密金鑰按以下優先順序取得：

1. **密碼片語** — 設定環境變數 `YU_SECRET_PASSPHRASE`，以 PBKDF2-HMAC-SHA256 (600,000 iterations) 導出金鑰。鹽值自動儲存於 `data/secret.salt`
2. **OS 鑰匙圈** — 若已安裝 `keyring` 套件，金鑰將保管於 Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **檔案** — `data/secret.key`（傳統相容，首次自動產生）

```bash
# 設定密碼片語的範例
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# 使用鑰匙圈
uv pip install keyring
```

### 金鑰匯出/匯入

可以密碼保護的 JSON 格式匯出/匯入加密金鑰，用於遷移至其他機器或備份。

- `POST /api/settings/secrets/export` — 以密碼（8 字元以上）保護並匯出
- `POST /api/settings/secrets/import` — 以匯出資料和密碼還原金鑰
- `POST /api/settings/secrets/migrate-keychain` — 從檔案遷移至鑰匙圈
- `GET /api/settings/secrets/status` — 確認後端狀態

### 遷移至鑰匙圈

若要將儲存在檔案中的金鑰遷移至鑰匙圈，請呼叫 `/api/settings/secrets/migrate-keychain`。遷移後，`data/secret.key` 將自動刪除。

## 1Password CLI 整合

在已安裝 `op` CLI 的環境中，可從 1Password Vault 動態取得密鑰。

### 設定

1. 安裝 [1Password CLI](https://developer.1password.com/docs/cli/)
2. 執行 `op signin` 登入
3. 在 `config.json` 中新增 `op_secrets` 對應：

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. 透過 Settings API 或 MCP 工具指定 `op_uri` 進行設定：

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### 運作方式

- 若金鑰已註冊在 `op_secrets` 中，會透過 `op read` 取得密鑰
- 取得的值會在記憶體中快取 5 分鐘
- 在沒有 `op` CLI 的環境中會退回至本機加密儲存區
- 可透過 `GET /api/settings/op-status` 確認 1Password 的認證狀態

## Settings MCP 工具

可從 MCP 用戶端（Claude Desktop 等）管理設定。

| 工具 | 說明 |
|--------|------|
| `settings_get_schema` | 取得所有設定的結構描述（型別、說明、分類） |
| `settings_get_all` | 取得所有設定值（密鑰已遮蔽） |
| `settings_get` | 取得單一設定值 |
| `settings_set` | 更新設定值（密鑰會自動加密） |
| `secrets_status` | 取得加密金鑰後端的狀態 |
| `secrets_export` | 以密碼保護的 JSON 匯出金鑰 |
| `secrets_import` | 從匯出資料匯入金鑰 |
