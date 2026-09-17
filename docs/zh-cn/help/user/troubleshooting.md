# 故障排除

## 常见问题

### 服务器无法启动

- 确认 Python 虚拟环境是否已激活：`source venv/bin/activate`
- 确认依赖包是否已安装：`uv pip install -r requirements.txt`
- 确认端口是否被占用：`ss -tlnp | grep 5000`

### 图片无法显示

- 缩略图 API 需要图片文件的实体存在
- 确认 `files` 数据表的路径是否与实际文件路径一致
- 确认扫描根目录的路径是否正确

### 无法从 LAN 访问

- 确认 Settings > Server 中「LAN Access」是否已开启
- 确认是否已设置 PIN 认证（LAN 公开时为必需项）
- 确认防火墙是否已开放该端口
- 确认服务器的 IP 地址是否正确

### MCP 连接错误

- 确认 `YU_BASE_URL` 是否正确
- 确认服务器是否正在运行
- 确认 API 密钥是否有效
- 若通过 LAN 连接，确认 HTTP/SSE 端点 (`/mcp`) 是否可用

### 扫描速度缓慢

- 将 `compute_hash` 设为 OFF 可加快速度
- 若为远程路径，请调整 Remote FS 的超时设置
- 大量文件的初次扫描需要较长时间

### 缩略图生成缓慢

- 扫描中磁盘 I/O 会达到饱和，因此缩略图生成会变慢。扫描完成后会自动执行预热
- **pyvips（可选）**：若有大量大型 JPEG 图片，可通过 libvips 的 shrink-on-load 加速
  - Linux：`sudo apt install libvips-dev && uv pip install pyvips`
  - macOS：`brew install vips && uv pip install pyvips`
  - Windows：从 [libvips 发布页面](https://github.com/libvips/libvips/releases) 下载 DLL 并加入 PATH 后执行 `uv pip install pyvips`
  - 若已安装会自动检测。未安装时仍可使用 Pillow 运行
- **Pillow-SIMD（可选）**：通过 ARM NEON / x86 AVX2 将图片缩放加速 2-4 倍
  - `uv pip install pillow-simd`（替代 Pillow 的直接替换包）
  - ARM NEON 优化构建：`CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - 在没有预构建 wheel 的环境中需要构建工具（gcc 等）

## 调试

- 在 Settings > Logs 选项卡确认服务器日志
- MCP 调试模式：设置 `YU_DEBUG_MODE=1` 可使用额外工具
- DB 完整性检查：`python db_health.py`
