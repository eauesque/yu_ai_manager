# OS-Level Isolation Guide

This feature limits the impact that Extensions can have on your system using built-in OS security mechanisms.

## 1. What Is OS Isolation?

When you install an app on your smartphone, you see a prompt like "This app is requesting access to your camera." OS isolation works on the same principle.

Based on the permissions an Extension declares (file read/write, network access, external command execution, etc.), **the OS kernel physically blocks unauthorized operations**. No matter what techniques are used in the Python code, kernel-level restrictions cannot be bypassed.

> **Note**: This feature is primarily designed for safely running third-party Extensions. `builtin-*` Extensions are treated as trusted (L0) and operate without restrictions.

---

## 2. Supported Platforms

| OS | Isolation Method | Maturity |
|----|-----------------|----------|
| **Linux** | AppArmor (Mandatory Access Control) | Recommended, production-ready |
| **macOS** | sandbox-exec (Seatbelt) | Experimental (deprecated by Apple) |
| **Windows** | Restricted Token + Job Object | Basic resource limiting |

Linux with AppArmor provides the most complete isolation and is the recommended environment.

---

## 3. Linux Setup (AppArmor)

### 3.1 What Is AppArmor?

AppArmor is a security module built into the Linux kernel. It defines per-process profiles specifying which files can be read/written and whether network communication is allowed, with enforcement handled by the kernel.

AppArmor is often enabled by default on Ubuntu / Debian, but some distributions like Raspberry Pi OS require manual activation.

### 3.2 Automated Setup

Use the included setup script for one-step configuration.

```bash
sudo bash scripts/setup-apparmor.sh
```

This script performs the following:

1. **Checks/installs AppArmor packages** — Automatically installs `apparmor` and `apparmor-utils` if missing
2. **Adds kernel parameters** — Appends `lsm=apparmor` to `/boot/firmware/cmdline.txt` (with backup)
3. **Configures sudoers rules** — Allows passwordless execution of `apparmor_parser` only (least privilege)
4. **Enables the AppArmor service** — Configures automatic startup via systemd

> **Non-Raspberry Pi OS environments**: For GRUB-based systems, manually add `lsm=apparmor` to `GRUB_CMDLINE_LINUX` in `/etc/default/grub`, then run `sudo update-grub`.

### 3.3 Reboot

A reboot is required after adding kernel parameters.

```bash
sudo reboot
```

### 3.4 Verification

After reboot, verify that AppArmor is active.

```bash
# Check if the kernel module is enabled
cat /sys/module/apparmor/parameters/enabled
# → "Y" indicates it is enabled

# List loaded profiles
sudo aa-status
```

### 3.5 Enable in config.json

Once AppArmor is confirmed working, add the following to `config.json`.

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

With this configuration, AppArmor profiles will be automatically generated and loaded when third-party Extensions start.

---

## 4. Configuration Reference

OS isolation is controlled via the `os_isolation` section in `config.json`.

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

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable/disable OS isolation globally |
| `linux.apparmor` | bool | `true` | Use AppArmor profiles |
| `macos.sandbox_exec` | bool | `false` | Use macOS sandbox-exec (experimental) |
| `windows.restricted_token` | bool | `true` | Launch processes with restricted tokens |
| `windows.job_object` | bool | `true` | Apply resource limits via Job Objects |
| `windows.job_limits.memory_mb` | int | `512` | Max memory per Extension (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | CPU usage cap per Extension (%) |
| `windows.job_limits.max_processes` | int | `10` | Max processes an Extension can spawn |

---

## 5. Extension Permissions and AppArmor Rules

AppArmor profiles are automatically generated based on permissions declared in the Extension's `extension.json`.

| Extension Permission | AppArmor Enforcement |
|---------------------|---------------------|
| `db:read` | Read-only access to `data/` directory |
| `db:write` | Read/write access to `data/` directory |
| `fs:read:scan_roots` | Read access to configured scan roots |
| `fs:write:any` | Read/write access to all paths |
| `network:local` | TCP/Unix sockets allowed (UDP denied) |
| `network:internet` | TCP/UDP/Unix sockets all allowed |
| `subprocess` | Execution of `/usr/bin/`, `/bin/`, etc. allowed |
| No network permission | TCP/UDP explicitly denied; only Unix sockets for IPC |
| No subprocess permission | Execution under `/usr/bin/`, `/bin/`, etc. explicitly denied |

The Extension's own directory (`extensions/<name>/`) is always readable and writable.

---

## 6. Checking Status via API

OS isolation status can be queried through the API.

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Example response (Linux / AppArmor enabled):

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

When `available` is `false`, the response includes a `setup` field with setup instructions.

---

## 7. Troubleshooting

### AppArmor Is Not Enabled

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" or file does not exist
```

**Cause**: Kernel parameters have not been applied.

**Solution**:
- Raspberry Pi OS: Verify `lsm=apparmor` is in `/boot/firmware/cmdline.txt`, then reboot
- GRUB-based: Check `GRUB_CMDLINE_LINUX="... lsm=apparmor"` in `/etc/default/grub`, then run `sudo update-grub && sudo reboot`

### "sudoers not configured" on Extension Startup

**Cause**: The NOPASSWD sudoers rule for `apparmor_parser` is not set up.

**Solution**:
```bash
sudo bash scripts/setup-apparmor.sh
```

The script installs the necessary rule at `/etc/sudoers.d/yu-ai-apparmor`.

### Extension Fails Due to Insufficient Permissions

**Cause**: Required permissions are not declared in the Extension's `extension.json`.

**Solution**: Add the necessary permissions to `permissions.required` in the Extension's `extension.json`, or grant permissions manually from Settings > Extensions.

### Manually Inspecting AppArmor Profiles

Generated profiles are saved in `/tmp/yu_ai_apparmor/`.

```bash
# View a profile's contents
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# List currently loaded YU AI Manager profiles
sudo aa-status | grep yu_ai_ext
```

---

## 8. Security Considerations

OS isolation is part of a defense-in-depth strategy. YU AI Manager provides security through multiple layers:

1. **Static analysis** (Phase 1) — AST analysis of Extension code at install time to detect dangerous imports
2. **Permission gatekeeper** (Phase 2-3) — Access through ServiceRegistry controlled by permission-checking Proxies
3. **OS isolation** (Phase 4) — Kernel-level enforcement of file, network, and process execution restrictions

OS isolation alone does not eliminate all risks, but combined with other defense layers, it provides a safe environment for using third-party Extensions.

For untrusted Extensions, we recommend using a Linux environment with OS isolation enabled.
