# OS 级别隔离指南

此功能利用操作系统内置的安全机制，限制扩展（Extension）对系统的影响。

## 1. 什么是 OS 隔离？

在智能手机上安装应用时，您会看到"此应用请求访问您的相机"等提示。OS 隔离的原理完全相同。

根据 Extension 声明的权限（文件读写、网络通信、执行外部命令等），**操作系统内核会物理阻断未授权的操作**。无论 Python 代码中使用了什么技巧，内核级别的限制都无法绕过。

> **注意**：此功能主要用于安全地使用第三方 Extension。`builtin-*` Extension 被视为受信任（L0），不受任何限制。

---

## 2. 支持的平台

| 操作系统 | 隔离方式 | 成熟度 |
|---------|---------|--------|
| **Linux** | AppArmor（强制访问控制） | 推荐使用，生产环境可用 |
| **macOS** | sandbox-exec（Seatbelt） | 实验性（Apple 已标记为弃用） |
| **Windows** | Restricted Token + Job Object | 基本资源限制 |

Linux 的 AppArmor 完成度最高，是推荐的运行环境。

---

## 3. Linux 设置（AppArmor）

### 3.1 什么是 AppArmor？

AppArmor 是内置于 Linux 内核的安全模块。它为每个进程定义配置文件，指定哪些文件可以读写、是否允许网络通信，并由内核强制执行。

Ubuntu / Debian 通常默认启用 AppArmor，但 Raspberry Pi OS 等部分发行版需要手动启用。

### 3.2 自动化设置

使用随附的设置脚本进行一键配置。

```bash
sudo bash scripts/setup-apparmor.sh
```

此脚本执行以下操作：

1. **检查/安装 AppArmor 软件包** — 若未安装 `apparmor` 和 `apparmor-utils` 则自动安装
2. **添加内核参数** — 在 `/boot/firmware/cmdline.txt` 中添加 `lsm=apparmor`（含备份）
3. **配置 sudoers 规则** — 仅允许免密码执行 `apparmor_parser` 命令（最小权限）
4. **启用 AppArmor 服务** — 通过 systemd 配置开机自动启动

> **非 Raspberry Pi OS 环境**：使用 GRUB 的系统请手动在 `/etc/default/grub` 的 `GRUB_CMDLINE_LINUX` 中添加 `lsm=apparmor`，然后执行 `sudo update-grub`。

### 3.3 重启

添加内核参数后需要重启。

```bash
sudo reboot
```

### 3.4 验证

重启后，确认 AppArmor 是否已启用。

```bash
# 检查内核模块是否已启用
cat /sys/module/apparmor/parameters/enabled
# → 显示 "Y" 表示已启用

# 列出已加载的配置文件
sudo aa-status
```

### 3.5 在 config.json 中启用

确认 AppArmor 正常运行后，在 `config.json` 中添加以下配置。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

完成配置后，第三方 Extension 启动时会自动生成并加载 AppArmor 配置文件。

---

## 4. 配置项参考

通过 `config.json` 的 `os_isolation` 部分进行控制。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `enabled` | bool | `false` | 全局启用/禁用 OS 隔离 |
| `linux.apparmor` | bool | `true` | 使用 AppArmor 配置文件 |
| `macos.sandbox_exec` | bool | `false` | 使用 macOS sandbox-exec（实验性） |
| `windows.restricted_token` | bool | `true` | 以受限令牌启动进程 |
| `windows.job_object` | bool | `true` | 通过 Job Object 限制资源 |
| `windows.job_limits.memory_mb` | int | `512` | 每个 Extension 的最大内存 (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | 每个 Extension 的 CPU 使用率上限 (%) |
| `windows.job_limits.max_processes` | int | `10` | 每个 Extension 可生成的最大进程数 |

---

## 5. Extension 权限与 AppArmor 规则的对应

AppArmor 配置文件会根据 Extension 的 `extension.json` 中声明的权限自动生成。

| Extension 权限 | AppArmor 控制 |
|---------------|--------------|
| `db:read` | 仅允许读取 `data/` 目录 |
| `db:write` | 允许读写 `data/` 目录 |
| `fs:read:scan_roots` | 允许读取已配置的扫描根目录 |
| `fs:write:any` | 允许读写所有路径 |
| `network:local` | 允许 TCP/Unix socket（拒绝 UDP） |
| `network:internet` | 允许所有 TCP/UDP/Unix socket |
| `subprocess` | 允许执行 `/usr/bin/`、`/bin/` 等 |
| 无网络权限 | 明确拒绝 TCP/UDP，仅允许 IPC 用 Unix socket |
| 无 subprocess 权限 | 明确拒绝执行 `/usr/bin/`、`/bin/` 等 |

Extension 自身的目录（`extensions/<name>/`）始终可读写。

---

## 6. 通过 API 确认状态

OS 隔离的状态可通过 API 查询。

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

响应示例（Linux / AppArmor 已启用）：

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

当 `available` 为 `false` 时，响应中会包含 `setup` 字段，提供配置步骤。

---

## 7. 故障排除

### AppArmor 未启用

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" 或文件不存在
```

**原因**：内核参数尚未应用。

**解决方法**：
- Raspberry Pi OS：确认 `/boot/firmware/cmdline.txt` 中有 `lsm=apparmor`，然后重启
- GRUB 环境：确认 `/etc/default/grub` 中 `GRUB_CMDLINE_LINUX="... lsm=apparmor"`，然后执行 `sudo update-grub && sudo reboot`

### Extension 启动时出现「sudoers not configured」

**原因**：`apparmor_parser` 的 NOPASSWD sudoers 规则未配置。

**解决方法**：
```bash
sudo bash scripts/setup-apparmor.sh
```

脚本会在 `/etc/sudoers.d/yu-ai-apparmor` 配置必要的规则。

### Extension 因权限不足无法运行

**原因**：Extension 的 `extension.json` 中未声明必要的权限。

**解决方法**：在 Extension 的 `extension.json` 的 `permissions.required` 中添加必要的权限，或从"设置 > 扩展"手动授予权限。

### 手动检查 AppArmor 配置文件

生成的配置文件保存在 `/tmp/yu_ai_apparmor/`。

```bash
# 查看配置文件内容
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# 列出当前已加载的 YU AI Manager 配置文件
sudo aa-status | grep yu_ai_ext
```

---

## 8. 安全注意事项

OS 隔离是纵深防御策略的一部分。YU AI Manager 通过多重层级确保安全：

1. **静态分析**（Phase 1）— 安装时以 AST 分析 Extension 代码，检测危险的 import
2. **权限网关**（Phase 2-3）— 通过 ServiceRegistry 的权限检查代理控制访问
3. **OS 隔离**（Phase 4）— 内核级别强制限制文件、网络和进程执行

OS 隔离本身无法消除所有风险，但与其他防御层结合后，可为使用第三方 Extension 提供安全的环境。

对于不受信任的 Extension，建议在启用 OS 隔离的 Linux 环境中使用。
