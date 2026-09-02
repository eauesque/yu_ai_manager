# LLM Router 设置

## 添加到 config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## 与 Claude Code 联动

LLM Router 已实现 Anthropic 兼容的 `/v1/messages` 端点，因此 Claude Code
（Anthropic 官方 CLI）可以**直接**对接本地 LLM，无需额外代理
（claude-code-router 等）。

### 1. yu_ai_manager 端的 alias 设置

Claude Code 内部会发送 `claude-opus-4-*` / `claude-sonnet-4-*` /
`claude-haiku-4-*` 等模型名称。在 `config.json` 的 `aliases` 中将其映射到
本地分类（`large` / `fast` / `vision`）或物理模型：

```json
{
  "llm_router": {
    "enabled": true,
    "aliases": {
      "claude-opus-4-7":           "large",
      "claude-sonnet-4-6":         "fast",
      "claude-haiku-4-5":          "fast",
      "claude-3-5-haiku-20241022": "fast"
    }
  }
}
```

| Claude Code 发送的模型名 | 建议映射目标 | 用途 |
|---|---|---|
| `claude-opus-*` | `large`（如 qwen2.5:72b / llama3.3:70b） | 主推理 |
| `claude-sonnet-*` | `fast` 或 `large` | 平衡 |
| `claude-haiku-*` | `fast`（如 qwen2.5:7b） | 后台任务（摘要、标题生成等） |

`large` / `fast` / `vision` 是 `core/llm_core` 分类注册表的虚拟后端，会从已注册
的模型中自动挑选（可在 `/llm-router` WebUI 查看）。

### 2. Claude Code 端的配置

在 `~/.claude/settings.json`（Windows：`%USERPROFILE%\.claude\settings.json`）
中添加：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy"
  }
}
```

- loopback 访问时 `ANTHROPIC_AUTH_TOKEN` 不会被校验，但 Claude Code 要求变量
  必须存在，填任意字符串即可
- 从 LAN 中的其他主机连接时改为 `http://<host>.local:5000/v1`，并将
  `config.json` 的 `auth.mode` 设为 `api_key` 并提供实际 token

仅做一次性测试时可用环境变量：

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 ANTHROPIC_AUTH_TOKEN=dummy claude
```

### 3. 将后台任务（haiku 等价）导向另一模型

Claude Code 的后台任务可通过 `ANTHROPIC_SMALL_FAST_MODEL` 覆盖：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_SMALL_FAST_MODEL": "fast"
  }
}
```

主流量走 alias（opus → large），后台流量明确命中 `fast` 分类。

### 4. 工作确认

```bash
# /v1/messages 是否响应
curl -s http://localhost:5000/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}'

# 从 Claude Code
claude
> /model          # 查看当前模型
> hello           # 有响应即说明本地路由已生效
```

### 5. 常见问题

| 症状 | 原因 / 对策 |
|---|---|
| `model_not_found` 错误 | Claude Code 发送的模型名既不在 alias 中也不在分类中。请在 `/llm-router` WebUI 查看请求日志并添加 alias |
| 响应极慢 | `large` 对应到 70B 级模型。请在 alias 中直接指定更轻量的模型 |
| `401 unauthorized` | `auth.mode` 为 `api_key` 但 Claude Code 端 `ANTHROPIC_AUTH_TOKEN` 不匹配 |
| 流式中途中断 | 后端（如 Ollama）超时太短。请将 `config.json` 的 `backends[].timeout` 设为 120 以上 |

### 6. 直接指定物理名 / 自定义 alias

`aliases` 区段可添加任意名称，不限于 Claude 模型名：

```json
"aliases": {
  "local-fast":  "ollama-local/qwen2.5:7b",
  "local-coder": "ollama-mac/qwen2.5-coder:32b"
}
```

在 Claude Code 端执行 `/model local-coder` 即会直接路由到该模型。

### 7. 混合运行 (opus = 真实 Anthropic、sonnet/haiku = 本地) 的现状

"协调器走 Anthropic 的 opus，仅子代理走本地" 这种拆分运行模式，
**当前的 Claude Code + LLM Router 不推荐采用**。原因：

- `ANTHROPIC_BASE_URL` 对整个 session 生效，因此 "只让 opus 请求直通 Anthropic 本家"
  的设定无法在 Claude Code 端组合
- 在 LLM Router 中添加 upstream passthrough 后端在技术上可行，但**经济性不成立**：
  - **Max/Pro 订阅用户**：设置 `ANTHROPIC_BASE_URL` 后立即脱离订阅认证路径，
    passthrough 的 opus 请求按 API 单价计费（反而更贵）
  - **API key 计费用户**：passthrough 不会改变 opus 的 token 单价，
    且协调器消耗的 opus token 占主导，将子代理改为本地化的节省效果有限

**推荐方针**：若以节省成本为目的，**请将协调器也全部导向本地**
（例：将 `claude-opus-*` 也 alias 到 `large` 分类），通过本地模型选型
（Qwen2.5-72B / Llama 3.3-70B / DeepSeek 等）确保质量。
若采用协调器与实现代理职责分离的设计，70B 级模型通常足够胜任。

将来如果 Claude Code 支持 `ANTHROPIC_OPUS_BASE_URL` 之类的按模型端点分割，
本节将更新。

## 与 Continue (VSCode) 联动

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## 节点自动发现 — `.local` 主机名支持（家庭局域网）

在家庭局域网中运行多台设备（mac mini + Pi5 + Windows GPU 主机等）时，在 `base_url` 中使用 `.local` 主机名而非 IP 地址，即使 **DHCP 导致 IP 变更也能正常工作**。yu_ai_manager 端无需额外实现，`httpx` 会通过操作系统的解析器（Bonjour / Avahi / mDNSResponder）自动完成名称解析。

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

示例：[`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### 运行要求

| 操作系统 | 所需组件 |
|---|---|
| macOS | Bonjour（系统自带，无需额外安装） |
| Linux | `avahi-daemon`（`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`） |
| Windows 10/11 | mDNSResponder（Win10 1803 及以上版本系统自带 `.local` 解析。如不工作请安装 Bonjour Print Services） |

### 验证

```bash
# 测试能否解析
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → 返回 192.168.x.x 即为成功
```

### 跨子网 / 企业局域网 / VPN 穿透

mDNS 基于 L2 组播工作，因此**无法穿越路由器、VPN 和企业网络的隔离 VLAN**。在这些环境中请继续直接指定 IP 地址：

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

在需要 mDNS reflector 的 VLAN 分割环境中，请咨询局域网管理员。yu_ai_manager 不提供 mDNS reflector / 代理功能。

### 已知限制

- **Windows 的 mDNS 解析偶尔较慢**（约 1 秒）：建议将后端 `timeout` 设为 3 秒以上
- **必须以 `.local` 结尾**：单独使用 `mac-mini` 会回退到 NetBIOS / DNS，务必写成 `mac-mini.local`
- **Ollama 本身不进行 mDNS 广播**：仅做主机名解析，端口（11434）需手动指定。待 Ollama 支持广播后可实现完全自动化（参见 TODO.md mDNS Phase B/C）

## 环境变量

| 变量名 | 功能 |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | 设为 `1` 可禁用整个 Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | 设为 `1` 可禁用 5 分钟刷新循环 |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | 覆盖为 `none`/`loopback`/`api_key` |

## 其他语言文档

按照 CLAUDE.md 的 `docs/ 读取规则`，以 `ja/` 为基础同步 `en/zh-tw/zh-cn/ko` 版本（实现后的独立任务；参见 TODO.md）。

## 节点自动发现（Phase B — v4.64.0 及以上）

同一局域网内的 yu_ai_manager 节点通过 mDNS（`_yu-ai._tcp.local.`）相互自动发现。无需在 `config.json` 中手动添加后端，发现的节点会以 `mdns-<prefix>` alias 自动注册到 `BackendCatalog`。

### 工作原理

1. 启动时 `core/mdns/` 广播 `_yu-ai._tcp.local.`
2. 订阅其他节点的 TXT 记录，确认必要的键（version/node_id/llm_base_url）齐全
3. 对主版本号匹配的节点发送 HTTP GET 到 `http://<addr>:<web_port>/api/mdns/identity`，确认 product/node_id/version 一致
4. 验证通过的节点以 `BackendInfo(alias="mdns-<node_id[:8]>")` 注册到 LLM Router
5. 之后由现有的 probe 循环进行定期刷新

### 前提条件

- 操作系统的 mDNS 响应器正在运行（macOS: Bonjour、Linux: Avahi、Windows: mDNSResponder）
- 节点位于同一 L2 子网内（跨路由器/VPN 环境请使用 Phase A 的手动配置）
- 本地防火墙允许 UDP 5353
- **Ollama 需要对局域网公开** — Ollama 默认绑定到 `127.0.0.1:11434`，局域网内其他节点无法访问。请在启动 Ollama 前设置环境变量 `OLLAMA_HOST=0.0.0.0:11434`（macOS 使用 `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`、Linux 使用 systemd unit / `.bashrc`、Windows 使用系统环境变量）。未设置时 yu_ai_manager 会判定为仅本地访问，不广播 `llm_base_url`（启动日志中会输出警告）

### Ollama 自动检测

如果 `config.json` 的 `llm_router.backends` 中没有 localhost 条目，yu_ai_manager 会在启动时按以下顺序查找 Ollama：

1. `http://<LAN_IP>:11434/api/tags` — 从局域网可达的 Ollama
2. `http://localhost:11434/api/tags` — 即使检测到也不会进行局域网广播（输出上述警告）

如果局域网 IP 返回 200，则自动将其作为 `llm_base_url` 写入 TXT 记录。适用于零配置让 Ollama 共存节点加入 mDNS 的场景。非默认端口（11435 等）或 lmstudio / llamacpp 仍需在 `config.json` 中明确指定。

### 未与 `yu` 共存的 pure bare Ollama 节点的处理方针

未运行 `yu_ai_manager` 的 pure bare Ollama 节点（例如家人 mac 上只装了 Ollama、
NAS 上的 Ollama 容器等）**不在自动发现的对象范围内**。由于 `Ollama` 本身没有
官方 advertise `_ollama._tcp.local.` 的功能，结构上没有检测手段。

如需从 LLM Router 使用此类节点，请使用以下方式 **手动配置**：

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- 若环境支持 `.local` 主机名（见上文"节点自动发现 — `.local` 主机名支持"），建议优先使用
- 否则请直接写入固定 IP

#### 不采用自动发现的理由

在设计评审（2026-04-11）时比较了以下 3 种方案，最终选择 (c) 手动配置引导：

| 方案 | 内容 | 采否 |
|---|---|---|
| (a) 启动时扫描整个局域网 `:11434` | 启动时对子网内主机进行全数 probe | **不采用** — 网络负载大，对企业 / 多主机局域网造成困扰，可能被误认为端口扫描，违反 edge-first 哲学 |
| (b) 常驻外部 Ollama 广告 daemon | 在每个 Ollama 主机上额外常驻 yu 提供的轻量 advertiser | **不采用** — 要求额外的常驻进程，等同于直接安装 `yu_ai_manager` 本身，失去 pure bare 的意义 |
| (c) 引导使用固定 IP / `.local` / 手动 backend 配置 | 在 `config.json` 中手写 | **采用** — 零额外实现、行为明确、不会将用户卷入非预期的扫描 |

未来若 Ollama 本体官方 advertise `_ollama._tcp.local.`，或新增官方 service
discovery 机制，届时再以 Phase D 重新评估自动发现层。

### 禁用

在不需要的网络环境（Docker 隔离、企业局域网、CI 等）中可禁用：

- 在 `config.json` 中添加 `"mdns": {"enabled": false}`
- 或设置环境变量 `YU_AI_MDNS_DISABLED=1`

### 已知行为

- **多宿主环境（Wi-Fi + 有线）**：默认（`bind_address: null`）会在两个网络接口上广播，`PeerInfo.addresses` 中包含多个 IP。如需限制为单一接口，请指定 `"bind_address": "192.168.x.y"`。
- **alias 冲突**：如果 `config.json` 的后端中使用了 `mdns-xxxxxxxx` 格式的 alias，手动配置优先，mDNS 发现的条目将被跳过。
- **跨子网**：mDNS 默认仅在 L2 广播域内工作。跨域运行请使用 Phase A 的 `.local` 主机名指定。
- **安全性**：mDNS 本身没有认证机制。适用于家庭局域网等可信环境。在公共 Wi-Fi 或多人局域网中建议禁用。`/api/mdns/identity` 的验证可防止误认节点或不兼容旧版本的混入。
