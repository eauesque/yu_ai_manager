# 节点 PIN 认证与令牌配对

**实现版本**: 4.92.0
**相关文件**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## 概览

在 v4.92 之前，LAN 上的节点通信仅通过 `X-Peer-Id` 标头来识别对方。
由于此标头可由同一网络上的任何人伪造，安全性不足。

从 v4.92 起，系统已迁移至 **PIN 审批式令牌配对** 方式。

- 首次连接时发送"配对请求"
- 对方管理员在管理界面审批后，发出 6 位数 PIN（有效期 5 分钟）
- 输入 PIN 后颁发 Bearer 令牌（有效期 30 天）
- 后续通信使用 `Authorization: Bearer <token>` 进行认证

旧版 `X-Peer-Id` 标头方式可通过设置保留兼容性，但 DELETE 操作始终需要新认证方式。

---

## 配对流程

```
[节点 A（发起方）]                     [节点 B（目标方）]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                           管理员在 /lan-cowork/peers 确认并审批
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (6 位数 PIN，有效期 5 分钟)          |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer 令牌，有效期 30 天)           |
       |                                      |
       |--- 后续: Authorization: Bearer <token>
```

### 各步骤说明

| 步骤 | 端点 | 说明 |
|------|------|------|
| 1. 发送请求 | `POST /api/lan/pair/request` | 发送节点 ID、显示名称及公钥 |
| 2. 等待审批 | — | 管理员在 `/lan-cowork/peers` 确认请求 |
| 3. 发出 PIN | — | 管理员点击审批按钮，生成 6 位数 PIN（有效 5 分钟） |
| 4. PIN 验证 | `POST /api/lan/pair/verify` | 提交 PIN 并接收 Bearer 令牌 |
| 5. 已认证通信 | — | 附加 `Authorization: Bearer <token>` 标头 |

---

## 管理界面 (`/lan-cowork/peers`)

### 待审批请求

当新节点发送配对请求时，会显示在管理界面的"待审批"标签中。

- **审批**: 生成 PIN 并通过 SSE 通知请求方节点
- **拒绝**: 删除请求。请求方节点收到 403

### 已连接节点列表

显示所有已配对的节点及各令牌的到期日期。

| 列 | 内容 |
|----|------|
| 显示名称 | 节点名称 |
| IP 地址 | 最后观察到的来源 IP |
| 到期日期 | Bearer 令牌到期日期（30 天） |
| 最后连接 | 最后心跳的时间戳 |
| 操作 | 撤销令牌按钮 |

### 令牌撤销

点击"撤销"可立即使目标节点的 Bearer 令牌失效。
下次通信时，节点收到 401 并自动尝试重新配对。

---

## 配置项

配置位于 `config.json` 的 `lan_cowork` 部分，或通过设置界面的"LAN 协作"标签修改。

### `ip_check_mode`

指定来源 IP 地址的验证方式。

| 值 | 行为 |
|----|------|
| `strict` | 仅允许与颁发令牌时完全相符的 IP（默认） |
| `cidr` | 允许 `allowed_cidr` 指定的 CIDR 范围内的 IP |
| `rfc1918` | 允许所有私有 IP 地址（192.168.x.x / 10.x.x.x / 172.16-31.x.x） |

### `allow_legacy_auth`

是否保留与旧版 `X-Peer-Id` 标头认证的兼容性。

- `true`: 仅使用 `X-Peer-Id` 标头也允许部分操作（默认: `true`）
- `false`: 拒绝所有不含 Bearer 令牌的连接

> **注意**: 使用 `DELETE` 方法的操作（停止扫描、强制删除等）无论 `allow_legacy_auth` 设置如何，始终需要 Bearer 令牌。

### `protect_heartbeat`

是否对心跳端点 (`/api/lan/heartbeat`) 也要求认证。

- `true`: 心跳也需要 Bearer 令牌
- `false`: 心跳无需认证即可通过（默认: `false`）

由于心跳频繁发送，设为 `false` 可防止令牌到期检测的延迟。

### `protect_events`

是否对 SSE 事件流 (`/api/events/`) 也要求认证。

- `true`: SSE 连接也需要 Bearer 令牌
- `false`: SSE 无需认证即可通过（默认: `false`）

---

## 安全说明

### 令牌哈希

颁发的 Bearer 令牌**不会以明文存储**在数据库中。
使用 scrypt（N=16384, r=8, p=1）哈希后才存储。
即使数据库泄露，也无法还原原始令牌。

### 日志脱敏

- `Authorization: Bearer <token>` 标头在日志输出时自动替换为 `Bearer [REDACTED]`
- PIN 代码也不会留在日志中

### 速率限制

为防止 DoS 攻击和暴力破解，适用以下速率限制：

| 端点 | 限制 |
|------|------|
| `POST /api/lan/pair/request` | 10 次/分钟/IP |
| `POST /api/lan/pair/verify` | 30 次/分钟/IP |

PIN 在 5 分钟后自动到期，每个请求只能验证一次。

---

## 故障排查

### 配对请求未收到

- 确认远端节点的 URL 配置是否正确
- 确认端口是否被防火墙封锁
- 查看远端节点的日志，确认 `pair/request` 的接收情况

### PIN 已过期

PIN 有效期为 5 分钟。如已过期，请在管理界面再次点击"审批"按钮，即可发出新的 PIN。

### 令牌突然无法使用

可能原因：

1. 管理员在管理界面撤销了令牌
2. 30 天有效期已到期
3. 使用 `ip_check_mode: strict` 时 IP 地址已变更

请重新执行配对流程。

### 将 `allow_legacy_auth` 设为 `false` 后无法连接

若现有节点仍在使用旧版认证方式，所有节点都将收到 401。
请先在每个节点完成重新配对，再将 `allow_legacy_auth` 设为 `false`。
