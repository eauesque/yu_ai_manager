# ffmpeg 安装指南

Tag Database 使用 ffmpeg 为视频文件（WebM、MP4 等）生成缩略图。

## Windows

### 方式 1：Scoop（推荐）
```powershell
# 安装 Scoop（如未安装）
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# 安装 ffmpeg
scoop install ffmpeg
```

### 方式 2：Chocolatey
```powershell
# 安装 Chocolatey（如未安装）
# 以管理员身份运行
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 安装 ffmpeg
choco install ffmpeg
```

### 方式 3：手动下载
1. 下载：https://www.gyan.dev/ffmpeg/builds/
2. 解压到 `C:\ffmpeg`
3. 添加到 PATH：
   - 打开"环境变量"
   - 编辑"Path"
   - 添加 `C:\ffmpeg\bin`
4. 重启终端

---

## macOS

### Homebrew（推荐）
```bash
# 安装 Homebrew（如未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 ffmpeg
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## 验证安装

```bash
ffmpeg -version
```

应输出版本信息。

---

## 测试视频缩略图

```bash
# 启动 WebUI
python web_ui.py --db tags.db

# 导航到一个 WebM 文件
# 缩略图应自动生成
```

---

## 故障排除

### "ffmpeg not installed" 错误

**症状**：视频缩略图显示错误信息

**解决方案**：
1. 验证 ffmpeg 已安装：`ffmpeg -version`
2. 重启终端/PowerShell
3. 重启 WebUI
4. 检查 PATH 设置

### 缩略图未生成

**症状**：缩略图显示"Failed to extract video frame"

**可能原因**：
- 视频文件已损坏
- 不支持的视频编解码器
- ffmpeg 超时（>10 秒）

**调试**：
```bash
# 手动测试
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# 检查日志
# 查找 "[ERROR] ffmpeg" 消息
```

---

## 可选：GPU 加速

用于更快的视频处理（高级）：

### Windows (NVIDIA)
```bash
# 下载 NVIDIA 构建：
# https://www.gyan.dev/ffmpeg/builds/
# 选择 "ffmpeg-release-full.7z"
```

### macOS (VideoToolbox)
```bash
# Homebrew 构建中已包含
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## 性能说明

- 首次缩略图生成：约 1-3 秒
- 缓存缩略图：<100ms
- ZIP 文件：解压到临时目录后处理
- 超时：每个视频 10 秒

---

## 不安装 ffmpeg

如果 ffmpeg 不可用：
- 视频文件的缩略图将显示错误
- 仍可通过元数据搜索视频
- 建议安装 ffmpeg 以获得完整功能
