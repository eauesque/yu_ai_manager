# Extensions

YU AI Manager 支援透過 Extension 系統新增功能。
目前包含 43 個內建 Extension，分為 6 個類別。

## 內建 Extension 清單

### 中繼資料擷取 (metadata)

| Extension | 說明 |
|-----------|------|
| builtin-a1111 | Automatic1111 / SD WebUI PNG/WebP/WebM 中繼資料擷取 |
| builtin-novelai-v3 | NovelAI V3 及更早版本中繼資料擷取 |
| builtin-novelai-v4 | NovelAI V4 中繼資料擷取（Character Prompts、Vibe Transfer） |
| builtin-comfyui | ComfyUI 工作流程 JSON 解析 |
| builtin-annotations | 檔案註解儲存、搜尋和批次操作 |
| builtin-ratings | 星級評分系統（1-5 星） |
| builtin-tag-dictionary | Danbooru 標籤字典搜尋、匯入和拆分 |

### Bridge 整合 (bridge)

| Extension | 說明 |
|-----------|------|
| builtin-sd-webui-bridge | SD WebUI / Forge 整合（圖片生成、模型管理） |
| builtin-nai-bridge | NovelAI API 整合（圖片生成） |
| builtin-comfyui-bridge | ComfyUI 整合（工作流程執行） |

### 提示詞 (prompt)

| Extension | 說明 |
|-----------|------|
| builtin-prompt-library | 提示詞庫和整理 |
| builtin-prompt-syntax | 提示詞語法標示和錯誤偵測（NAI/SD/DP） |
| builtin-prompt-simulator | Dynamic Prompts 模擬器、權重計算和轉換 |
| builtin-sd-nai-convert | SD <-> NovelAI 提示詞雙向轉換 |

### AI (ai)

| Extension | 說明 |
|-----------|------|
| builtin-analysis | AI 圖片分析（Claude、OpenAI、Ollama、Hailo VLM） |
| builtin-wd-tagger | WD-Tagger 自動標註（ONNX + VLM 引擎） |
| builtin-ocr | VLM OCR——文字擷取、結構化分析和翻譯 |
| builtin-clip-search | CLIP 語意圖片搜尋引擎 |
| builtin-clip-onnx | CLIP ONNX Runtime 編碼器後端 |
| builtin-clip-coreml | CLIP Core ML 編碼器（Apple Neural Engine） |
| builtin-hailo-semantic-search | Hailo-10H 語意搜尋 |
| builtin-hailo-yolo-detect | Hailo-10H YOLO 物件偵測 |
| builtin-hailo-genai | Hailo-10H GenAI（LLM/VLM/S2T） |
| builtin-speech-to-text | 語音辨識（Hailo NPU / CUDA / ROCm / CPU） |
| builtin-audio-analysis | 音訊分析（Whisper local / OpenAI API） |
| builtin-video-analysis | 影片 AI 分析（multi-keyframe + Gemini） |
| builtin-inference | ONNX Runtime 提供者偵測和 GPU 加速 |

### 媒體庫 (library)

| Extension | 說明 |
|-----------|------|
| builtin-favorites-manager | 我的最愛和收藏集管理 |
| builtin-freeze-pullback | Freeze & Pull-back 影片生成（Ken Burns 效果） |
| builtin-download | 選取圖片的批次 ZIP 下載 |
| builtin-chatlog | 聊天記錄匯入和檢視器（Claude / ChatGPT） |
| builtin-md-viewer | Markdown 檔案檢視器（FTS5 全文搜尋） |
| builtin-cross-search | 跨搜尋（MD、聊天記錄、提示詞、文字） |
| builtin-lan-share | LAN 收藏集分享（限時權杖驗證） |
| builtin-stats | 統計洞察（時間軸、里程碑） |
| builtin-trophy | 獎盃和成就系統 |
| builtin-export | 匯出鉤子（CSV 輸出的記錄轉換） |

### 系統 (system)

| Extension | 說明 |
|-----------|------|
| builtin-auto-scan-watcher | 檔案變更自動偵測和增量更新 |
| builtin-mcp-client | 外部 MCP 伺服器連線管理 |
| builtin-backup | DB 備份、還原和排程器 |
| builtin-sns-share | SNS 分享（Bluesky、X/Twitter） |
| builtin-webhook | Webhook 分發器（事件驅動 HTTP 投遞） |
| builtin-debug-check | 除錯診斷 CLI |
| builtin-github-integration | GitHub Issue 監控・分類・PR/Discussion/Release 追蹤 |

## 管理 Extension

在設定 > Extensions 標籤頁中可以執行以下操作：

- **啟用/停用**：透過開關即時切換
- **安裝新的**：指定 Git 儲存庫 URL 安裝
- **市集**：搜尋和一鍵安裝公開 Extension
- **更新**：將基於 Git 的 Extension 更新到最新版本
- **解除安裝**：移除第三方 Extension

### 透過 API 管理

```bash
# 列出 Extension
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# 啟用/停用切換
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# 從 Git 安裝
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension 沙箱

第三方 Extension 受沙箱保護。

### 信任層級

| 層級 | 目標 | 限制 |
|------|------|------|
| L0 (TRUSTED) | `builtin-*` | 無限制 |
| L2 (UNTRUSTED) | 其他 | DB/FS/網路限制適用 |

### 沙箱階段

1. **Capability Token**：透過 HMAC-SHA256 簽章權杖進行權限管理。24 小時過期
2. **SandboxedDB / SandboxedFS**：僅有 `db:read` 的 Extension 限制為 SELECT 查詢。基於路徑的規則控制檔案存取
3. **SandboxedHTTPClient / ImportGuard**：SSRF 防護、執行期 import 監控、SHA-256 竄改偵測
4. **處理程序隔離（Linux）**：L2 Extension 在獨立處理程序中執行。Unix 通訊端 JSON-RPC 2.0 IPC

### 作業系統層級隔離（選用）

- **Linux**：自動產生 AppArmor 設定檔
- **macOS**：sandbox-exec（實驗性）
- **Windows**：Restricted Token + Job Object

> **提示**：有關 Extension 開發的詳細資訊，請參閱「Extension Development」部分。

## 目錄結構

```
extensions/builtin_<name>/
  extension.json            # 清單（名稱、版本、權限等）
  <name>_ext.py             # 進入點（公開 get_blueprint()）
  templates/<name>/          # Jinja2 範本
  core_impl/                 # 商業邏輯（選用）
```

### extension.json 必要欄位

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

類別為 6 種之一：`metadata`、`bridge`、`prompt`、`ai`、`library`、`system`。

## Extension Module API v2（ES Module 支援）

自 v4.29.0 起，Extension 可以使用 `<script type="module">` 搭配 Import Maps 進行 ES Module 匯入。

### 啟用方法

在 `extension.json` 中加入 `"script_type": "module"`：

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

將範本中的 `<script>` 改為 `<script type="module">`，並從 `yu-api` 匯入：

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast 通知
showToast('儲存成功');

// SSE 事件訂閱
sseSubscribe('scan.progress', (data) => {
  console.log('進度:', data);
});

// i18n 翻譯
const label = tr('my_ext.title', 'My Extension');

// API 呼叫（自動加入 CSRF 標頭）
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### 公開 API 一覽

| 函式 | 說明 |
|---|---|
| `showToast(message, isError?)` | 顯示 Toast 通知 |
| `sseSubscribe(eventType, handler)` | 訂閱 SSE 事件 |
| `sseUnsubscribe(eventType, handler)` | 取消訂閱 SSE 事件 |
| `tr(path, a?, b?)` | 解析 i18n 翻譯鍵 |
| `apiFetch(path, opts?)` | 含 CSRF 的 fetch 包裝器 |
| `apiUrl(path)` | 建構 API URL |
| `escapeHtml(text)` | 轉義 HTML 特殊字元 |

### TypeScript 型別定義

將 `src/ts/extension-api/extension-api.d.ts` 複製到您的 Extension 專案中，即可啟用 IDE 自動補全和型別檢查。

### 向後相容

`"script_type": "classic"`（預設值）的 Extension 可繼續使用 `window.showToast()` 等全域函式。現有 Extension 無需任何修改。

## 開發文件

Extension 開發的開發洞見、內部設計決策、已知注意事項和除錯技巧可在 [MD Viewer](/ext/md-viewer/) 中檢視。`docs/development/development_docs/` 目錄已註冊，支援 FTS5 全文搜尋。
