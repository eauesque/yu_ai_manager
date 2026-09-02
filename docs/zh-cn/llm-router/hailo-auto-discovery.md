# Hailo LLM 自动发现

**适用版本**: v4.66.0 及以上

## 概述

yu_ai_manager 可以自动发现在 Pi5 的 Hailo NPU 上运行的 LLM 端点，无需编辑 `config.json`。只需将 Pi5 接入局域网，其他 yu_ai_manager 节点即可调用 Hailo LLM。

## 检测对象的两个系统

| 端点 | 说明 | 默认 URL 模式 |
|---|---|---|
| **yu extension Hailo LLM** | yu_ai_manager 内置的 `builtin-hailo-genai` extension 提供的 OpenAI 兼容 LLM | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | 外部二进制文件 `/usr/bin/hailo-ollama` 提供的 OpenAI 兼容 LLM（默认 `:8000`） | `http://<host>:8000/v1/` |

两者可同时运行并都会被自动注册。在 HailoRT 5.3.0+ 中设置 `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED`，HailoRT 调度器会以 round-robin 方式共享物理设备，同时使用也不会冲突。

## 本地自动注册（Phase A）

yu_ai_manager 启动时独立检测以下两项：

1. **yu extension**: `hailo_platform.genai.LLM` 可导入，且 `/dev/hailo0` 或 `/dev/h1x-0` 存在 → 作为 `hailo-local` 后端自动注册到 catalog
   （v4.66.1 中已适配 Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 实机将设备公开为 `/dev/h1x-0` 的情况）
2. **hailo-ollama**: 对 `localhost:8000/v1/models` 发起 HTTP 探测（2 秒超时） → 收到 200 响应则作为 `hailo-ollama-local` 后端自动注册

如果 `config.json` 的 `llm_router.backends` 中已有同名 alias，则优先使用该配置（不会覆盖）。

## mDNS 自动广播（Phase B）

根据 Phase A 的检测结果，yu_ai_manager 通过 mDNS TXT 记录向其他节点广播 Hailo 能力：

- `capabilities=llm,hailo` — 表示 yu extension 可用
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` — 仅在 hailo-ollama 运行时添加（会替换为局域网可达的 IP）

其他 yu_ai_manager 节点通过 mDNS 接收到该信息后，先通过 `/api/mdns/identity` 端点进行身份验证，然后以以下 alias 自动注册额外后端：

- `mdns-<node_id[:8]>-hailo` — yu extension Hailo LLM（当 `capabilities` 包含 `hailo` 时，从 peer 的 `web_port` + addresses 导出 URL）
- `mdns-<node_id[:8]>-hailo-ollama` — 外部 hailo-ollama（当 `hailo_ollama_url` 被广播时，直接使用 TXT 中的 URL）

## 设置

默认启用。可通过 `config.json` 禁用：

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: 设为 `false` 可完全禁用 hailo-ollama 的自动检测。yu extension 端的检测由 extension 是否加载来自动判断，独立控制
- **`port`**: hailo-ollama 的端口号（默认 8000）。超出 1-65535 范围时回退到默认值并输出 warning 日志

## 安全注意事项

**hailo-ollama 没有认证功能**。通过 mDNS 广播后，**局域网上的任意节点都可以自由消耗 hailo-ollama 的推理资源**。

| 端点 | 认证 | 实际局域网公开范围 |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | yu 的 web auth chain（PIN/session/api-key） | 仅通过 yu 认证的客户端 |
| hailo-ollama (`hailo_ollama_url`) | **无** | **局域网上的所有节点** |

在家庭局域网或可信 VLAN 以外的环境（公共 Wi-Fi 等）中，请通过 `hailo_ollama.enabled: false` 禁用自动广播。

## 在 LLM Router WebUI 中的显示

v4.65.0 的 `/llm-router` 仪表盘会显示自动注册的后端：

- `hailo-local` / `hailo-ollama-local` — 本地检测（source: `static` 标记）
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` — 通过 mDNS 发现（source: `mdns` 标记）

均可通过 Disable 开关临时禁用。禁用状态持久化到 `data/llm_router_state.json`，重启后也会保留（v4.65.0 实现）。

## 误检测的安全保障

Phase A 检测有两道安全机制：

1. **自我探测回避**: 当 `hailo_ollama.port` 与 yu 自身的 web port 相同时，完全跳过探测（防止 yu 将自己误认为 hailo-ollama）
2. **现有后端优先**: 当 `config.json` 中已注册了相同 `localhost:<port>/v1` 的后端时，跳过探测以尊重用户意图

## TODO 遗留项

- (P3) 其他语言翻译（`en`, `zh-tw`, `zh-cn`, `ko`）— 计划与 v4.65.0 LLM Router WebUI 的翻译遗留一并处理
- (P3) Pi5 实机集成测试 — 2 节点配置下 Playwright 16 项同等测试
- (P3) IPv6 支持 — 目前 `_pick_lan_ip` 仅返回 IPv4
- (P3) 多 Hailo 设备支持 — 基于固定 alias `hailo-local`。多个 USB dongle 等情况需考虑 index suffix 设计
- (P3) `BackendCatalog.remove_backend()` — 目前 `_mark_unreachable` 仅更新状态，不从 catalog 中删除

## 相关文档

- [LLM Router 设置](./setup.md)
- 设计规范: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- 实施计划: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 — Trusted peer auth（实机认证漏洞修复）

v4.66.0 的 Hailo 自动发现中，由于 yu 的 `/ext/hailo-genai/*` extension 位于 web auth chain 之下，LLM Router driver（没有 Bearer 或 session）在尝试探测/分发时会收到认证中间件的 honeypot HTML，导致 JSON 解析失败并一直停留在 `unreachable` 状态。

### 工作原理

- 新增 `TrustedPeerRegistry`，初始化时 seed `127.0.0.1` / `::1`
- `LlmRouterMdnsBridge` 在对 peer 验证（HTTP GET `/api/mdns/identity` + node_id 一致性确认）成功后，将该 peer 的所有 advertised addresses 添加到 registry
- `auth_chain.check_trusted_peer` 在收到 `/ext/<name>/v1/*` 路径的请求时，如果 remote_addr 在 registry 中则跳过 PIN auth
- 现有的 API key / session / cookie 认证路径不受影响

### 与 Quick lock 的关系

- **loopback**（yu 自身的 self-probe）：quick_lock 期间始终放行
- **peer IP**：quick_lock 期间拒绝请求（`check_quick_lock` 返回 503）。尊重"用户主动锁定"的状态

这使得以下场景正常工作：

- pi2 的 `hailo-local` self-probe（`http://localhost:5000/ext/hailo-genai/v1/models`）
- Windows 访问 pi2 的 `mdns-<id>-hailo` 跨节点分发（`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`）

### 设置

无需更改配置文件。即使 mDNS 被禁用，loopback seed 仍然生效，因此 self-probe 修复是无条件获得的。

### 调试

设置环境变量 `TAGDB_DEBUG_TRUSTED_PEERS=1` 启动 yu，`/api/mdns/peers` 响应中会包含 `trusted_ips` 字段。生产环境中请勿设置（trust 列表可能成为"攻击目标列表"，应避免在未认证端点上暴露）。

### 安全边界

与 v4.64.0 mDNS Phase B 相同的"可信局域网前提"运行规则。不保护来自局域网内有物理访问权限的恶意节点 — 此类情况请使用 `/llm-router` WebUI 的 disable 开关或 quick_lock 处理。

详情参见 `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md`。
