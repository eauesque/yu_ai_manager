# 扫描

## 注册扫描文件夹

前往 Settings > Scan 选项卡添加扫描对象文件夹。

- 可通过拖放重新排序
- 通过复选框切换启用/禁用
- 可注册多个文件夹

## 执行扫描

- 添加文件夹后会自动开始扫描
- 手动扫描可从 Tools 页面或 MCP 的 `trigger_scan` 执行
- 扫描中的进度会通过 SSE 实时通知

## 自动扫描（Watcher）

启用 Auto Scan Watcher 扩展功能后，可自动检测已注册文件夹内的文件变更并进行扫描。

## 远程文件系统

扫描 WSL / NAS / SMB 等远程路径时，请在 Settings > Remote FS 选项卡调整超时设置。

## 大规模图库的扫描

扫描数十万～100 万件以上文件时的注意事项：

- **扫描中仍可搜索图片**：搜索 API 使用只读 DB 连接，不受扫描中写入锁定的影响
- **WAL 自动管理**：扫描中每 2000 个文件会自动执行 WAL 检查点，防止 WAL 文件过度膨胀
- **scan.db_busy 事件**：扫描开始/完成时会发送 SSE 事件，前端可据此显示忙碌状态

## 扫描 Worker 进程

自 v3.27.0 起，扫描在独立于 web_ui.py 的另一个进程中执行。
因此**即使重新启动 web_ui，扫描也不会中断**。

### 运作机制

- 从 WebUI 开始扫描时，会在后台启动 Worker 进程
- Worker 会在 `/tmp/yu-scan/` 写入进度文件 (JSON) 和 PID 文件
- WebUI 会轮询此进度文件，并通过 SSE 转发给前端
- 重新启动 WebUI 时，会自动检测运行中的 Worker 并重新连接进度显示

### 从 CLI 操作

Worker 也可从 CLI 直接操作。即使 WebUI 停止时也可使用。

```bash
# 检查状态
python -m core.scan.scan_worker status

# 停止运行中的扫描（优雅关闭 — 将中断位置保存至 DB）
python -m core.scan.scan_worker stop

# 从 CLI 直接开始扫描
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# 选项
#   --recursive / --no-recursive  是否包含子目录（默认：recursive）
#   --scan-zips                   扫描 ZIP/7z 内的图片
#   --force                       重新扫描已存在的文件
#   --resume                      恢复中断的扫描
#   --config config.json          指定配置文件
```

### 安全机制

- **父进程监控**：从 WebUI 启动的 Worker 会每 60 秒监控 WebUI 进程的存活状态。若 WebUI 异常终止，Worker 会自动保存中断位置并停止
- **SIGTERM 处理**：收到 `stop` 命令或 `kill` 的 SIGTERM 时，会完成当前的处理后提交至 DB，保存中断位置后退出
- **防止重复**：不会同时启动多个 Worker

### 故障排除

若 Worker 无响应：

```bash
# 确认 PID
cat /tmp/yu-scan/worker.pid

# 强制终止进程
kill -9 $(cat /tmp/yu-scan/worker.pid)

# 清除残留文件
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## 扫描错误

扫描中发生错误时，可通过 MCP 的 `get_scan_errors` 确认。
