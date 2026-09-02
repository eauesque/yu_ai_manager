# LAN Cowork

> 目标版本: v4.55.0 及更高版本（PIN 认证从 v4.92.0 开始可用）

## 什么是 LAN Cowork

LAN Cowork 是一项扩展功能，可在网络上协调多个 yu_ai_manager 节点。  
每台机器独立运行，同时允许将繁重的处理分散或作为 Fleet 进行集中管理。

```
┌──────────────┐    mDNS 发现      ┌──────────────┐
│  Windows PC  │◄──────────────────►│   Mac Mini   │
│  (配备 GPU)  │   PIN 配对        │  (控制)      │
│              │◄──────────────────►│              │
│  分布式推理  │                   │  Fleet 管理  │
│  (tagger等) │                   │              │
└──────────────┘                   └──────────────┘
        ▲                                  ▲
        └──────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## 功能概览

| 功能 | 说明 |
|---|---|
| **mDNS 自动发现** | 无需配置自动发现同一 LAN 上的节点 |
| **PIN 配对** | 管理员批准的 PIN 认证以发放节点间令牌 |
| **分布式推理** | 在多个节点上并行处理 tagger、CLIP、YOLO 和 Whisper |
| **生成分散** | 将 SD WebUI / ComfyUI 任务委派到 LAN 节点 |
| **Fleet 管理** | 集中管理所有节点的日志和版本更新 |
| **节点事件中继** | 将其他节点的事件流传输到您自己的 SSE |
| **LLM 路由** | 自动在 LLM Router 中注册发现的节点 |

---

## 设置步骤

### 1. 启用

添加到 `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **注意**：本页此前将启用键说明为顶层的 `{"lan_cowork": {...}}`，但没有任何实现会读取该位置的键。上面的 `extensions` 部分才是正确位置。

> **默认值取决于后端：**Python 后端（混合模式）会将缺失的键视为**已启用**，而 Rust 独立服务器除非明确启用，否则为**已禁用**。启用后网络上实际发生的情况，请参阅[网络行为](network-behavior.md)。

重启后:
- 开始在 UDP 19850 上侦听其他节点
- 开始通过 mDNS 广告 _yu-ai._tcp.local.

### 2. 配对节点

要从节点 A 连接到节点 B:

1. **节点 A WebUI** → `设置` → `LAN Cowork` → 添加节点 B URL
2. 节点 A 发送 `POST /api/lan/pair/request`
3. **节点 B WebUI** → `/lan-cowork/peers` → 在"待批准"选项卡中批准
4. 6 位 PIN 发送到节点 A（通过 SSE）
5. 节点 A 输入 PIN → 获得 Bearer 令牌（有效期 30 天）

> **注意**: 配对是单向的。请同时执行 A→B 和 B→A。

详见 [节点间 PIN 认证和令牌配对](peer-auth.md)。

### 3. 验证操作

```bash
# 发现的节点列表（从节点 A）
curl http://localhost:5000/api/mdns/peers

# LAN Cowork 识别的节点
curl http://localhost:5000/api/lan/peers
```

---

## 功能特定设置

### 分布式推理

配对完成后，分布式推理自动可用。

- `设置` → `LAN Cowork` → 为每个节点启用推理类型（tagger/CLIP/YOLO/Whisper）
- 或通过 `/mesh-inference` 页面上的矩阵进行单个配置

详情: [分布式推理设置](../mesh-inference/setup.md)

### Fleet 管理

配置"首席"节点以管理其他节点:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

详情: [Fleet 管理](../features/fleet-admin.md)

### 生成分散（SD / ComfyUI 任务委派）

自动将生成任务分散到配备 GPU 的节点。可通过配置文件后端注册或 mDNS 自动发现获得。  
如果节点 B 运行 SD WebUI / ComfyUI，配置后立即可用。

---

## 网络要求

| 端口 / 协议 | 用途 | 必需 |
|---|---|---|
| UDP 5353 | mDNS（节点发现） | 仅同一 L2 LAN |
| UDP 19850 | LAN Cowork 发现 | 仅同一 L2 LAN |
| TCP 5000 (默认) | API、配对、推理 | 节点之间 |

- mDNS 无法跨越路由器或 VPN（使用固定 IP 或 `.local` 主机名）
- 确保防火墙中 UDP 5353 和 TCP 5000 在 LAN 上开放

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [节点间 PIN 认证](peer-auth.md) | 配对流程、令牌管理、安全配置 |
| [分布式推理设置](../mesh-inference/setup.md) | 在多个节点上并行化推理的步骤 |
| [分布式推理矩阵](../mesh-inference/toggle.md) | 通过 WebUI 按节点和类型启用/禁用 |
| [分布式推理架构](../mesh-inference/overview.md) | 内部设计、工作窃取、持久化 |
| [Fleet 管理](../features/fleet-admin.md) | 远程日志和版本更新的集中管理 |
| [mDNS 节点 API](../api/mdns-peers.md) | `/api/mdns/*` 端点详情 |

---

## 安全性

- mDNS 没有认证。**仅在家庭 LAN 或可信网络上使用**
- 在公共 Wi-Fi 或共享 LAN 上，使用 `"mdns": {"enabled": false}` 禁用
- 节点间通信受 PIN 配对产生的 Bearer 令牌保护（存储为 scrypt 哈希）
- `ip_check_mode: strict` 仅允许发放令牌的 IP（默认）
