# Fleet 管理

LAN Cowork 的 Fleet Admin 功能可让您从中央位置管理网络上的多个 yu-ai-manager 节点。

## 概述

- **机器信息收集**：从所有节点汇总 CPU / RAM / GPU / 磁盘 / 版本 / 运行时间
- **远程日志查看**：从中央 UI 通过 SSE 实时串流任意节点的日志
- **版本更新分发**：指示节点执行 `git pull --ff-only` + graceful restart

## 前提条件

- LAN Cowork 扩展已启用（`extensions["builtin-lan-cowork"].enabled = true`）
- 节点之间已完成配对
- 已以 git 仓库形式 clone（使用更新功能时需要）
- Python 虚拟环境中已安装 `psutil>=5.9`

## 设置

### 主节点配置

在 `config.json` 中添加：

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<已配对的 peer_id>"
        ],
        "allow_log_stream_from": [
          "<已配对的 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### 普通节点配置

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<主节点的 peer_id>"
        ],
        "allow_log_stream_from": [
          "<主节点的 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## 访问 Fleet UI

在主节点的浏览器中访问 `/ext/lan_cowork/fleet/ui`。

普通节点上此 URL 会返回 404。

## 标签页功能

### 概览

- 显示各节点卡片（含 CPU / RAM / GPU / 磁盘使用率进度条）
- 在线 / 离线 / 无法获取信息 状态显示
- 主节点显示 `[CHIEF]` 徽章
- 每 30 秒自动刷新 + 手动刷新按钮
- 检测到多个主节点时显示警告横幅

### 日志

- 通过 SSE 实时串流任意节点的日志（tail -f 风格）
- 级别过滤（DEBUG / INFO / WARNING / ERROR）
- 搜索框（客户端过滤）
- 自动滚动 ON/OFF
- 暂停 / 恢复

### 更新

- 版本 / git commit / 分支对比表
- 单个节点的「Pull & Restart」按钮
- 多节点批量更新（dispatch）
- 进度显示（precheck → fetching → pulling → restarting → online）
- 主节点本身从批量更新中排除（仅限单独按钮）

## 安全性

授权采用两层架构：

1. **配对（身份确认）**：Bearer token 用于识别调用者身份
2. **Allowlist（权限）**：每项操作都需要明确授权 peer_id

已配对并不代表拥有所有权限。

### Allowlist 配置示例

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- 字符串和 `{peer_id: ...}` 格式均可使用
- 自身 peer_id 会自动添加（无需配置）

## 主节点自动降级

若同一网络上有多个 `chief = true` 的节点启动，后启动的节点会在 `chief_observation_sec` 秒观察后自动降级。

降级后需通过修改配置并重新启动才能恢复主节点身份（不会自动升级）。

## git 更新限制

- 仅使用 `git pull --ff-only`（不使用 merge/rebase）
- 无法 fast-forward 时立即返回 `failed`（工作目录不会被修改）
- 工作目录有未提交变更时拒绝更新

## 故障排除

| 症状 | 原因 | 解决方法 |
|---|---|---|
| `/fleet/ui` 返回 404 | 未设置 `chief = true` | 确认 config.json 后重新启动 |
| `/fleet/info` 返回 500 | 未安装 psutil | `uv pip install psutil>=5.9` |
| `git_not_available` 错误 | 找不到 git 或 PATH 不正确 | 确认 git 安装状态 |
| 更新后 `postcheck_online` 超时 | 重新启动超过 3 分钟 | 延长 `postcheck_timeout_sec` |
| 多主节点警告横幅持续显示 | 旧主节点进程仍在运行 | 重新启动旧主节点 |

## API 参考

### 所有节点

| 端点 | 说明 |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | 机器信息（需要 Bearer 认证） |
| `GET /ext/lan_cowork/fleet/logs/stream` | 自身日志 SSE（需要 allowlist 授权） |
| `POST /ext/lan_cowork/fleet/update` | git pull + 重新启动（需要 allowlist 授权） |
| `GET /ext/lan_cowork/fleet/update/status` | 更新任务状态查询 |

### 仅主节点

| 端点 | 说明 |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | 所有节点信息汇总 |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | 指定节点日志 SSE 转发 |
| `POST /ext/lan_cowork/fleet/update/dispatch` | 多节点批量更新 |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | dispatch 进度查询 |
| `GET /ext/lan_cowork/fleet/ui` | Fleet 管理 UI |
