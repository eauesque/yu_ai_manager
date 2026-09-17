# Extensions

YU AI Manager 支持通过 Extension 系统添加功能。
目前包含 43 个内置 Extension，分为 6 个类别。

## 内置 Extension 列表

### 元数据提取 (metadata)

| Extension | 说明 |
|-----------|------|
| builtin-a1111 | Automatic1111 / SD WebUI PNG/WebP/WebM 元数据提取 |
| builtin-novelai-v3 | NovelAI V3 及更早版本元数据提取 |
| builtin-novelai-v4 | NovelAI V4 元数据提取（Character Prompts、Vibe Transfer） |
| builtin-comfyui | ComfyUI 工作流 JSON 解析 |
| builtin-annotations | 文件注释存储、搜索和批量操作 |
| builtin-ratings | 星级评分系统（1-5 星） |
| builtin-tag-dictionary | Danbooru 标签字典搜索、导入和拆分 |

### Bridge 集成 (bridge)

| Extension | 说明 |
|-----------|------|
| builtin-sd-webui-bridge | SD WebUI / Forge 集成（图片生成、模型管理） |
| builtin-nai-bridge | NovelAI API 集成（图片生成） |
| builtin-comfyui-bridge | ComfyUI 集成（工作流执行） |

### 提示词 (prompt)

| Extension | 说明 |
|-----------|------|
| builtin-prompt-library | 提示词库和整理 |
| builtin-prompt-syntax | 提示词语法高亮和错误检测（NAI/SD/DP） |
| builtin-prompt-simulator | Dynamic Prompts 模拟器、权重计算和转换 |
| builtin-sd-nai-convert | SD <-> NovelAI 提示词双向转换 |

### AI (ai)

| Extension | 说明 |
|-----------|------|
| builtin-analysis | AI 图片分析（Claude、OpenAI、Ollama、Hailo VLM） |
| builtin-wd-tagger | WD-Tagger 自动标注（ONNX + VLM 引擎） |
| builtin-ocr | VLM OCR——文本提取、结构化分析和翻译 |
| builtin-clip-search | CLIP 语义图片搜索引擎 |
| builtin-clip-onnx | CLIP ONNX Runtime 编码器后端 |
| builtin-clip-coreml | CLIP Core ML 编码器（Apple Neural Engine） |
| builtin-hailo-semantic-search | Hailo-10H 语义搜索 |
| builtin-hailo-yolo-detect | Hailo-10H YOLO 目标检测 |
| builtin-hailo-genai | Hailo-10H GenAI（LLM/VLM/S2T） |
| builtin-speech-to-text | 语音识别（Hailo NPU / CUDA / ROCm / CPU） |
| builtin-audio-analysis | 音频分析（Whisper local / OpenAI API） |
| builtin-video-analysis | 视频 AI 分析（multi-keyframe + Gemini） |
| builtin-inference | ONNX Runtime 提供程序检测和 GPU 加速 |

### 库 (library)

| Extension | 说明 |
|-----------|------|
| builtin-favorites-manager | 收藏和收藏集管理 |
| builtin-freeze-pullback | Freeze & Pull-back 视频生成（Ken Burns 效果） |
| builtin-download | 选中图片的批量 ZIP 下载 |
| builtin-chatlog | 聊天记录导入和查看器（Claude / ChatGPT） |
| builtin-md-viewer | Markdown 文件查看器（FTS5 全文搜索） |
| builtin-cross-search | 跨搜索（MD、聊天记录、提示词、文本） |
| builtin-lan-share | LAN 收藏集共享（限时令牌认证） |
| builtin-stats | 统计洞察（时间线、里程碑） |
| builtin-trophy | 奖杯和成就系统 |
| builtin-export | 导出钩子（CSV 输出的记录转换） |

### 系统 (system)

| Extension | 说明 |
|-----------|------|
| builtin-auto-scan-watcher | 文件变更自动检测和增量更新 |
| builtin-mcp-client | 外部 MCP 服务器连接管理 |
| builtin-backup | DB 备份、恢复和调度器 |
| builtin-sns-share | SNS 分享（Bluesky、X/Twitter） |
| builtin-webhook | Webhook 分发器（事件驱动 HTTP 投递） |
| builtin-debug-check | 调试诊断 CLI |
| builtin-github-integration | GitHub Issue 监控・分类・PR/Discussion/Release 追踪 |

## 管理 Extension

在设置 > Extensions 标签页中可以执行以下操作：

- **启用/禁用**：通过开关即时切换
- **安装新的**：指定 Git 仓库 URL 安装
- **市场**：搜索和一键安装公开 Extension
- **更新**：将基于 Git 的 Extension 更新到最新版本
- **卸载**：移除第三方 Extension

### 通过 API 管理

```bash
# 列出 Extension
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# 启用/禁用切换
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# 从 Git 安装
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension 沙箱

第三方 Extension 受沙箱保护。

### 信任级别

| 级别 | 目标 | 限制 |
|------|------|------|
| L0 (TRUSTED) | `builtin-*` | 无限制 |
| L2 (UNTRUSTED) | 其他 | DB/FS/网络限制适用 |

### 沙箱阶段

1. **Capability Token**：通过 HMAC-SHA256 签名令牌进行权限管理。24 小时过期
2. **SandboxedDB / SandboxedFS**：仅有 `db:read` 的 Extension 限制为 SELECT 查询。基于路径的规则控制文件访问
3. **SandboxedHTTPClient / ImportGuard**：SSRF 防护、运行时 import 监控、SHA-256 篡改检测
4. **进程隔离（Linux）**：L2 Extension 在独立进程中运行。Unix 套接字 JSON-RPC 2.0 IPC

### 操作系统级隔离（可选）

- **Linux**：自动生成 AppArmor 配置文件
- **macOS**：sandbox-exec（实验性）
- **Windows**：Restricted Token + Job Object

> **提示**：有关 Extension 开发的详细信息，请参阅"Extension Development"部分。

## 目录结构

```
extensions/builtin_<name>/
  extension.json            # 清单（名称、版本、权限等）
  <name>_ext.py             # 入口点（暴露 get_blueprint()）
  templates/<name>/          # Jinja2 模板
  core_impl/                 # 业务逻辑（可选）
```

### extension.json 必需字段

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

类别为 6 种之一：`metadata`、`bridge`、`prompt`、`ai`、`library`、`system`。

## Extension Module API v2（ES Module 支持）

自 v4.29.0 起，Extension 可以使用 `<script type="module">` 配合 Import Maps 进行 ES Module 导入。

### 启用方法

在 `extension.json` 中添加 `"script_type": "module"`：

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### 使用方式

将模板中的 `<script>` 改为 `<script type="module">`，并从 `yu-api` 导入：

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast 通知
showToast('保存成功');

// SSE 事件订阅
sseSubscribe('scan.progress', (data) => {
  console.log('进度:', data);
});

// i18n 翻译
const label = tr('my_ext.title', 'My Extension');

// API 调用（自动注入 CSRF 头）
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### 公开 API 一览

| 函数 | 说明 |
|---|---|
| `showToast(message, isError?)` | 显示 Toast 通知 |
| `sseSubscribe(eventType, handler)` | 订阅 SSE 事件 |
| `sseUnsubscribe(eventType, handler)` | 取消订阅 SSE 事件 |
| `tr(path, a?, b?)` | 解析 i18n 翻译键 |
| `apiFetch(path, opts?)` | 含 CSRF 的 fetch 包装器 |
| `apiUrl(path)` | 构建 API URL |
| `escapeHtml(text)` | 转义 HTML 特殊字符 |

### TypeScript 类型定义

将 `src/ts/extension-api/extension-api.d.ts` 复制到您的 Extension 项目中，即可启用 IDE 自动补全和类型检查。

### 向后兼容

`"script_type": "classic"`（默认值）的 Extension 可继续使用 `window.showToast()` 等全局函数。现有 Extension 无需任何修改。

## 开发文档

Extension 开发的开发洞察、内部设计决策、已知注意事项和调试技巧可在 [MD Viewer](/ext/md-viewer/) 中查看。`docs/development/development_docs/` 目录已注册，支持 FTS5 全文搜索。
