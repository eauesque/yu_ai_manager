# mDNS 后端持续显示「无法连接」

LLM Router 的 mDNS 自动发现中新增的后端持续显示「无法连接 (unreachable)」
而无法恢复时的原因、诊断、处理方式汇总。

---

## 结构概览

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← 通过 HTTP 确认 /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← 向 BackendCatalog 注册
            ├─ _enter_cooldown() / _in_cooldown()  ← 失败后的重试限制
            └─ retry_pending_peers()  ← 60 秒周期扫描（v4.91.15〜）
```

**重要流程**:

1. zeroconf 检测到节点 → 调用 `on_peer_added`
2. `_verify()` 调用 `/api/mdns/identity`，验证 `node_id` 与 `product`
3. 成功 → 通过 `_apply_peer_to_catalog()` 将后端添加至 catalog
4. 失败 → 进入 60 秒 cooldown，忽略相同 `node_id` 的事件
5. **v4.91.15〜**: 每 60 秒的扫描任务在 cooldown 过期后重试未到达的节点

---

## 显示「无法连接」的主要模式

### 模式 A — 初次 verify 失败 → cooldown 静默

**症状**: LLM Router 中显示后端但 status=unreachable。  
**原因**:
- 对方节点刚启动时 HTTP 服务器尚未就绪
- 自己的端口已改变而节点仍参照旧的 TXT（v4.91.14 以前的
  `--port` override 错误：已在 35a3679a 修正）

**行为 (v4.91.14 以前)**: cooldown（60 秒）结束后等待下一个 `on_peer_updated`
事件，但若该事件未触发则永远无法恢复。

**行为 (v4.91.15〜)**: cooldown 过期后，下一个扫描 tick（最多 60 秒后）
自动重试 → 成功则反映至 catalog。

---

### 模式 B — zeroconf 不触发 `ServiceStateChange.Updated`

**症状**: 节点重启后 LLM Router 仍维持旧状态。  
**原因**: 依 zeroconf 的缓存状态，TXT 变更时 `Updated` 事件
有时不会触发（zeroconf 库的已知行为）。  
**处理**: v4.91.15 的扫描任务在 60 秒内捕获。

---

### 模式 C — 对方节点的端口与广播值不符

**症状**: curl 可到达但 verify timeout 持续。  
**原因**: 使用 `--port` CLI 标志但 config.json 的 `server.port` 仍为
旧值 → mDNS TXT 广播了错误的端口。  
**修正**: v4.91.14 (35a3679a) 已修正为以实际端口覆盖 `config["server"]["port"]`。
若旧的启动脚本直接覆盖 config.json，请同时确认配置文件。

---

### 模式 D — 未在 trusted_peer_registry 中注册

**症状**: LLM Router 显示「ready」但对 `/ext/<name>/v1/*` 的代理返回 403。  
**原因**: verify 成功已进入 catalog，但 `_apply_peer_to_catalog()` 调用前
进程重启，或因 `service_kind != "yu"` 跳过了 registry 的注册
（bare Ollama 节点不注册的规格）。  
**确认**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## 诊断步骤

### 1. 确认节点当前状态

```bash
# 已知的节点列表
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM Router 后端列表（mDNS 来源的 alias 以 "mdns-" 开头）
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. 确认对方节点能否到达自己的 identity 端点

在对方节点上：
```bash
curl -v http://<自己的LAN-IP>:<PORT>/api/mdns/identity
```

预期响应：
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

失败时：
- 防火墙/路由问题
- 端口实际值与广播值不符（确认是否以 `--port` 启动）

### 3. 确认自己广播的端口

```bash
# 启动日志中会显示 "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# 或通过 settings API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. 确认 cooldown 状态

GUI: **LLM Router** > 后端卡片 > 详细中显示 `last_error` 与
`last_seen_at`。错误为 "identity verification failed" 时表示 verify 可到达
但内容不符（node_id / product 不一致）。
错误为 "timeout" 时表示 HTTP 本身无法到达。

### 5. 确认扫描日志

```bash
grep "\[mdns\] sweep" logs/app.log
```

出现 `sweep re-verified peer <8字符>` 表示已通过扫描恢复。

---

## 强制恢复（手动）

不等扫描、立即恢复的方法：

### 方法 1: 重启对方节点

重启后 zeroconf 触发 `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` 清除 cooldown → `on_peer_added` 立即重新验证。

### 方法 2: mDNS 服务重启 API（从设置画面）

**设置** > **LLM Router** > **mDNS 重启** 按钮（若存在）。

### 方法 3: 重启应用程序

cooldown 仅存在于内存中。重启后所有 cooldown 重置，
启动后立即重新验证所有节点。

---

## 防止再发的要点

| 检查项目 | 确认方法 |
|---|---|
| 使用 `--port` 时 config.json 的 `server.port` 是否为相同值 | 参照 config.json |
| 防火墙是否允许 `PORT` 的 inbound | `sudo ufw status` / macOS 设置 |
| 多 NIC 环境中是否 bind 到正确的 LAN 接口 | `config.json` 的 `mdns.bind_address` |
| 是否使用 v4.91.15 以后的版本（内置扫描任务） | `curl .../api/server/info` |

---

## 相关文件

| 文件 | 作用 |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`·cooldown·retry_pending_peers |
| `core/web/runtime_mdns.py` | 扫描任务启动·停止 |
| `core/mdns/service.py` | zeroconf 包装器·`list_peers()` |
| `core/web/trusted_peer_registry.py` | 跨节点 `/ext/*` 认证 |
