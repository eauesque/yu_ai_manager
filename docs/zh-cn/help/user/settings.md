# 设置

## 服务器设置

| 项目 | 说明 |
|------|------|
| Host | 绑定地址（LAN OFF 时固定为 127.0.0.1） |
| Port | Web 服务器端口号 |
| LAN Access | 开启后可从 LAN 内的其他设备访问 |
| PIN Auth | 访问时要求输入 PIN |
| Boss Mode | 报纸风格的 PIN 登录界面 |

## 扫描设置

添加、删除、排序扫描文件夹，以及切换启用/禁用。

## 解析器设置

| 项目 | 说明 |
|------|------|
| Extract A1111 | 提取 Stable Diffusion WebUI 格式的元数据 |
| Extract ComfyUI | 提取 ComfyUI 工作流元数据 |
| Normalize tags | 将标签统一为小写 |
| Compute hash | 计算文件哈希值（用于重复检测） |
| FTS | 启用全文搜索索引 |

## API 密钥

管理外部工具（MCP 服务器、脚本、代理）用的 API 密钥。
以 Bearer 认证方式使用。

## 外观

主题、强调色、背景图片、音效等自定义设置。

## 加密密钥存储

PIN、Bluesky 密码、Webhook 密钥等机密值以 `cryptography` 包的 Fernet 加密保护。

- **加密格式**：带有 `enc:` 前缀的字符串
- **兼容性**：现有明文值可正常工作（仅在新保存时加密）
- **安装**：`uv pip install cryptography`（未安装时加密功能将禁用）

### 密钥后端

加密密钥按以下优先顺序获取：

1. **密码短语** — 设置环境变量 `YU_SECRET_PASSPHRASE`，以 PBKDF2-HMAC-SHA256 (600,000 iterations) 导出密钥。盐值自动保存于 `data/secret.salt`
2. **OS 密钥链** — 若已安装 `keyring` 包，密钥将保管于 Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **文件** — `data/secret.key`（传统兼容，首次自动生成）

```bash
# 设置密码短语的示例
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# 使用密钥链
uv pip install keyring
```

### 密钥导出/导入

可以密码保护的 JSON 格式导出/导入加密密钥，用于迁移至其他机器或备份。

- `POST /api/settings/secrets/export` — 以密码（8 字符以上）保护并导出
- `POST /api/settings/secrets/import` — 以导出数据和密码还原密钥
- `POST /api/settings/secrets/migrate-keychain` — 从文件迁移至密钥链
- `GET /api/settings/secrets/status` — 确认后端状态

### 迁移至密钥链

若要将存储在文件中的密钥迁移至密钥链，请调用 `/api/settings/secrets/migrate-keychain`。迁移后，`data/secret.key` 将自动删除。

## 1Password CLI 集成

在已安装 `op` CLI 的环境中，可从 1Password Vault 动态获取密钥。

### 设置

1. 安装 [1Password CLI](https://developer.1password.com/docs/cli/)
2. 执行 `op signin` 登录
3. 在 `config.json` 中添加 `op_secrets` 映射：

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. 通过 Settings API 或 MCP 工具指定 `op_uri` 进行设置：

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### 运作方式

- 若密钥已注册在 `op_secrets` 中，会通过 `op read` 获取密钥
- 获取的值会在内存中缓存 5 分钟
- 在没有 `op` CLI 的环境中会回退至本地加密存储
- 可通过 `GET /api/settings/op-status` 确认 1Password 的认证状态

## Settings MCP 工具

可从 MCP 客户端（Claude Desktop 等）管理设置。

| 工具 | 说明 |
|--------|------|
| `settings_get_schema` | 获取所有设置的结构描述（类型、说明、分类） |
| `settings_get_all` | 获取所有设置值（密钥已遮蔽） |
| `settings_get` | 获取单一设置值 |
| `settings_set` | 更新设置值（密钥会自动加密） |
| `secrets_status` | 获取加密密钥后端的状态 |
| `secrets_export` | 以密码保护的 JSON 导出密钥 |
| `secrets_import` | 从导出数据导入密钥 |
