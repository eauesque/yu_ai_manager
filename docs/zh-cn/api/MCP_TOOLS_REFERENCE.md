# MCP 工具参考

YU AI Manager MCP (Model Context Protocol) 服务器提供的完整工具列表。
Claude Desktop 及其他 MCP 客户端可以调用这些工具来自动化图库管理、分析和生成。

**工具总数：521**

## 目录

- [搜索与浏览 (10)](#搜索与浏览-10)
- [合集 (7)](#合集-7)
- [评分与标签 (5)](#评分与标签-5)
- [收藏夹 (8)](#收藏夹-8)
- [注解 (4)](#注解-4)
- [扫描 (14)](#扫描-14)
- [扫描根目录 (9)](#扫描根目录-9)
- [哈希与去重 (7)](#哈希与去重-7)
- [等待/进度 (2)](#等待进度-2)
- [AI 分析 (25)](#ai-分析-25)
- [WD-Tagger (15)](#wd-tagger-14)
- [语义搜索 / CLIP (12)](#语义搜索--clip-12)
- [YOLO 目标检测 (17)](#yolo-目标检测-17)
- [OCR (19)](#ocr-19)
- [SD WebUI Bridge (14)](#sd-webui-bridge-14)
- [ComfyUI Bridge (13)](#comfyui-bridge-13)
- [NovelAI Bridge (8)](#novelai-bridge-8)
- [Hailo GenAI (10)](#hailo-genai-10)
- [Hailo Chat (7)](#hailo-chat-7)
- [Hailo Remote Tagger (7)](#hailo-remote-tagger-7)
- [Tagger Server Registry (13)](#tagger-server-registry-13)
- [提示词库 (21)](#提示词库-21)
- [提示词模拟器 (6)](#提示词模拟器-6)
- [提示词语法 (1)](#提示词语法-1)
- [SD/NAI 转换 (3)](#sdnai-转换-3)
- [聊天日志 (16)](#聊天日志-16)
- [Markdown 查看器 (8)](#markdown-查看器-8)
- [Freeze & Pull-back (6)](#freeze--pull-back-6)
- [语音转文字 (8)](#语音转文字-8)
- [统计 (6)](#统计-6)
- [配置文件 (11)](#配置文件-11)
- [文件操作 (4)](#文件操作-4)
- [SVG 光栅化 (2)](#svg-光栅化-2)
- [下载 (1)](#下载-1)
- [视频分析 (3)](#视频分析-3)
- [备份 (5)](#备份-5)
- [归档清理 (7)](#归档清理-7)
- [自动扫描监视 (3)](#自动扫描监视-3)
- [调度器 (6)](#调度器-6)
- [Webhooks (9)](#webhooks-9)
- [扩展 (25)](#扩展-25)
- [UI 管理 (4)](#ui-管理-4)
- [设置 (18)](#设置-18)
- [SNS 分享 (15)](#sns-分享-15)
- [LAN 共享 (2)](#lan-共享-2)
- [MCP 客户端 (8)](#mcp-客户端-8)
- [Cross Search (9)](#cross-search-9)
- [标签字典 (6)](#标签字典-6)
- [奖杯 (1)](#奖杯-1)
- [源代码浏览 (3)](#源代码浏览-3)
- [帮助 (3)](#帮助-3)
- [系统信息 (3)](#系统信息-3)
- [系统更新 (5)](#系统更新-5)
- [建议 (4)](#建议-4)
- [日志与调试 (9)](#日志与调试-9)
- [代理安全网关 (25)](#代理安全网关-25)
- [GitHub Integration (12)](#github-integration-12)
- [调试工具 (9)](#调试工具-9)
- [LoRA Dataset Manager (15)](#lora-dataset-manager-14)
- [LLM 端点 (5)](#llm-端点-5)
- [LLM 聊天 (1)](#llm-聊天-1)
- [服务器模式 (1)](#服务器模式-1)

---

## 设置

### 环境变量

| 变量 | 说明 | 默认值 |
|----------|-------------|---------|
| `YU_BASE_URL` | YU AI Manager 服务器 URL | `http://localhost:5000` |
| `YU_API_KEY` | API Key（Bearer 认证） | （无） |
| `YU_DEBUG_MODE` | 设为 `1` 启用调试工具 | `0` |

### Claude Desktop 配置示例（`claude_desktop_config.json`）

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### 进度通知

`wait_for_scan` / `wait_for_batch` 工具支持 MCP Notifications：
- **支持 progressToken 的客户端**：通过 `notifications/progress` 接收实时进度。
- **不支持的客户端**：调用阻塞直到完成，然后返回最终结果。

---

## 搜索与浏览 (10)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `search_images` | 使用多种过滤条件搜索图片 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | 按目录分组搜索图片 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | 多查询联合搜索 | `queries`: list |
| `get_image_detail` | 获取图片的全部元数据 | `file_id`: int |
| `get_library_stats` | 图库统计 | -- |
| `get_file_info` | 文件路径和元数据信息 | `file_id`: int |
| `get_groups_index` | 目录组索引 | -- |
| `get_group_members` | 列出组内成员 | `group`: str |
| `get_container_members` | 列出 ZIP/RAR 容器内成员 | `file_id`: int |
| `file_search` | 按路径/名称搜索数据库中的文件 | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## 合集 (7)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_collections` | 列出所有合集 | -- |
| `create_collection` | 创建合集 | `name`: str |
| `rename_collection` | 重命名合集 | `collection_id`: int, `name`: str |
| `delete_collection` | 删除合集 | `collection_id`: int |
| `reorder_collections` | 更改合集顺序 | `order`: list |
| `add_to_collection` | 添加图片到合集 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | 从合集移除图片 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## 评分与标签 (5)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `rate_images` | 批量设置多张图片的评分 | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | 获取文件评分 | `file_ids`: str |
| `get_ratings_stats` | 评分统计 | -- |
| `set_tags` | 批量添加/移除多张图片的用户标签 | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | 规范化数据库中的标签 | -- |

## 收藏夹 (8)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `toggle_favorite` | 切换收藏状态 | `file_id`: int |
| `check_favorite` | 检查收藏状态 | `file_id`: int |
| `check_favorite_collections` | 检查已收藏文件的合集归属 | `file_id`: int |
| `list_favorites` | 列出收藏 | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | 批量添加多个文件到收藏夹 | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | 批量从收藏夹移除多个文件 | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | 将收藏夹导出到服务器文件夹 | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | 列出收藏夹集合中的图片 | `collection_id`: int = 0 |

## 注解 (4)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `set_annotations` | 保存注解（upsert） | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | 获取图片的注解 | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | 跨文件搜索注解 | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | 删除注解 | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## 扫描 (14)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `trigger_scan` | 启动所有扫描根目录的扫描 | -- |
| `start_scan` | 启动指定路径或所有根目录的扫描 | `path`: str = '' |
| `get_scan_status` | 获取扫描进度 | -- |
| `cancel_scan` | 取消扫描 | -- |
| `resume_scan` | 恢复中断的扫描 | -- |
| `dismiss_interrupted_scan` | 丢弃中断状态 | -- |
| `get_scan_interrupted` | 获取中断的扫描信息 | -- |
| `get_scan_errors` | 列出扫描错误 | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | 将错误标记为已解决 | `error_id`: int |
| `clear_scan_errors` | 清除已解决的错误 | -- |
| `get_scanned_roots` | 列出已扫描的根目录 | -- |
| `scan_queue_list` | 列出扫描队列中的待处理项 | -- |
| `scan_queue_remove` | 从扫描队列中移除项目 | `queue_id`: str |
| `scan_queue_clear` | 清空扫描队列 | -- |

## 扫描根目录 (9)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_scan_roots` | 列出扫描根目录 | -- |
| `add_scan_root` | 添加扫描根目录 | `path`: str |
| `edit_scan_root` | 编辑扫描根目录路径 | `index`: int, `path`: str |
| `remove_scan_root` | 移除扫描根目录 | `index`: int |
| `toggle_scan_root` | 切换扫描根目录启用/禁用 | `index`: int |
| `reorder_scan_roots` | 更改扫描根目录顺序 | `order`: list |
| `scan_directory` | 扫描特定目录 | `path`: str |
| `get_checkpoints` | 列出可用的模型检查点 | -- |
| `purge_scanned_roots` | 清除已扫描根目录记录 | -- |

## 哈希与去重 (7)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `find_duplicates` | 检测重复文件 | `method`: str = 'hash' |
| `find_similar` | 通过感知哈希搜索相似图片 | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | 启动文件哈希计算任务 | `hash_type`: str = 'both' |
| `delete_duplicates` | 删除重复文件 | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | 启动未计算哈希的批量计算 | -- |
| `cancel_hash_backfill` | 取消哈希计算 | -- |
| `get_hash_backfill_status` | 获取哈希计算进度 | -- |

## 等待/进度 (2)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `wait_for_scan` | 等待扫描完成（支持进度通知） | `timeout`: int = 600 |
| `wait_for_batch` | 等待批处理完成（支持进度通知） | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI 分析 (25)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `analyze_image` | 单张图片 AI 分析 | `file_id`: int |
| `analyze_batch` | 多张图片批量 AI 分析 | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | 取消正在运行的AI分析批处理任务 | -- |
| `get_analysis_result` | 获取分析结果 | `file_id`: int |
| `get_analysis_stats` | 分析统计 | -- |
| `get_analysis_config` | 获取分析配置 | -- |
| `save_analysis_config` | 保存分析配置 | `config`: dict |
| `get_available_engines` | 列出可用引擎 | -- |
| `get_ollama_models` | 列出 Ollama 模型 | -- |
| `test_ollama_connection` | 测试 Ollama 连接 | -- |
| `get_openai_compat_models` | 列出 OpenAI 兼容 API 模型 | -- |
| `test_openai_compat_connection` | 测试 OpenAI 兼容 API 连接 | -- |
| `list_ai_servers` | 列出已注册的 AI 服务器 | -- |
| `add_ai_server` | 注册 AI 服务器 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | 更新 AI 服务器设置 | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | 移除 AI 服务器 | `server_id`: str |
| `set_active_ai_server` | 切换活动服务器 | `server_id`: str |
| `test_ai_server` | 测试 AI 服务器连接 | `server_id`: str |
| `reorder_ai_servers` | 更改服务器优先级顺序 | `order`: list |
| `migrate_ai_servers` | 从旧版设置迁移 | -- |
| `analyze_prompt_trends` | 分析提示词趋势 | `limit`: int = 100 |
| `get_trend_history` | 获取趋势分析历史 | `limit`: int = 20 |
| `delete_trend_history` | 删除趋势历史 | `history_id`: int |
| `analyze_video` | 多关键帧视频分析 (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | 使用 Whisper 转录音频/视频文件 | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | 检查音频分析可用状态 (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `wd_tagger_tag_file` | 对单个文件运行标签推理 | `file_id`: int |
| `wd_tagger_batch` | 对多个文件运行批量标签推理 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | 取消正在运行的WD-Tagger批处理任务 | -- |
| `wd_tagger_get_tags` | 获取文件的 WD-Tagger 标签 | `file_id`: int |
| `wd_tagger_delete_tags` | 删除文件的 WD-Tagger 标签 | `file_id`: int |
| `wd_tagger_delete_tags_batch` | 批量删除多个文件的 WD-Tagger 标签 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | 获取 XMP 元数据 | `file_id`: int |
| `wd_tagger_stats` | 标签统计 | -- |
| `wd_tagger_untagged` | 列出未标签文件 | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | 获取配置 | -- |
| `wd_tagger_save_config` | 保存配置 | `config`: dict |
| `wd_tagger_model_status` | 模型下载状态 | -- |
| `wd_tagger_download_model` | 下载模型 | -- |
| `wd_tagger_vlm_test` | 测试 VLM 服务器连接 | `url`: str |
| `wd_tagger_vlm_models` | 列出 VLM 服务器模型 | `url`: str |

## 语义搜索 / CLIP (12)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `semantic_search` | 使用自然语言文本搜索图片 | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | 扩展状态 | -- |
| `semantic_backend_info` | CLIP 后端信息 | -- |
| `semantic_model_status` | 模型状态 | -- |
| `semantic_model_download` | 下载 CLIP 模型 | -- |
| `semantic_index_start` | 开始构建索引 | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | 索引进度 | -- |
| `semantic_index_stop` | 停止构建索引 | -- |
| `semantic_index_clear` | 清除索引 | -- |
| `semantic_caption_start` | 开始批量生成字幕 | `batch_size`: int = 50 |
| `semantic_caption_status` | 字幕进度 | -- |
| `semantic_caption_stop` | 停止字幕生成 | -- |

## YOLO 目标检测 (17)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `yolo_status` | 扩展状态 | -- |
| `yolo_detect_start` | 开始目标检测 | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | 检测任务进度 | -- |
| `yolo_detect_stop` | 停止检测 | -- |
| `yolo_get_results` | 获取文件的检测结果 | `file_id`: int |
| `yolo_search` | 按检测标签搜索图片 | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | 清除检测结果 | `file_ids`: list = None |
| `yolo_model_status` | 模型状态 | -- |
| `yolo_model_download` | 下载 YOLO HEF 模型 | -- |
| `yolo_list_labels` | 列出已检测的标签 | -- |
| `yolo_stream_sources` | 串流源列表与状态 | -- |
| `yolo_stream_start` | 启动串流源 | `source_id`: str |
| `yolo_stream_stop` | 停止串流源 | `source_id`: str |
| `yolo_stream_add_source` | 添加串流源 | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | 检测规则列表 | -- |
| `yolo_stream_add_rule` | 添加检测规则 | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | 串流整体状态（管线、源、规则、录制） | -- |

## OCR (19)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `ocr_extract` | 对图像执行 OCR 文本提取 | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | 对多个文件执行 OCR | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | 获取文件的 OCR 结果 | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | 删除文件的 OCR 结果 | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | 以指定格式导出 OCR 结果 | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | 翻译 OCR 结果 | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | 获取文件的翻译结果 | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | 对视频关键帧执行 OCR | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | 对 OCR 结果执行边界框检测 | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | 生成 OCR 叠加图像 | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | 批量导出 OCR 结果 | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | 对 PDF 文档执行 OCR | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | 列出可用 OCR 引擎及能力评分 | -- |
| `ocr_profiles` | 列出所有模型能力配置文件 | -- |
| `ocr_profiles_fetch` | 从 URL 获取并合并社区模型配置 | `url`: str |
| `ocr_profile_update` | 手动更新模型能力评分 | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | 运行 OCR 基准测试以测量准确度 | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | 列出可用基准测试用例 | `benchmark_dir`: str = "" |
| `ocr_npu_status` | 检查 NPU 可用状态和优化建议 | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `sd_test_connection` | 测试连接 | -- |
| `sd_generate` | txt2img 图片生成 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | 生成进度 | -- |
| `sd_cancel` | 取消生成 | -- |
| `sd_list_models` | 列出检查点模型 | -- |
| `sd_list_samplers` | 列出采样器 | -- |
| `sd_list_loras` | 列出 LoRA | `q`: str = '' |
| `sd_list_embeddings` | 列出嵌入 | `q`: str = '' |
| `sd_list_scripts` | 列出脚本 | -- |
| `sd_get_script_info` | 脚本详情 | -- |
| `sd_list_extensions` | 列出扩展 | -- |
| `sd_list_upscalers` | 列出放大器 | -- |
| `sd_get_config` | 获取配置 | -- |
| `sd_save_config` | 保存配置 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `comfyui_test_connection` | 测试连接 | -- |
| `comfyui_generate` | txt2img 图片生成 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | 从 JSON 工作流生成 | `workflow`: str |
| `comfyui_get_progress` | 生成进度 | -- |
| `comfyui_cancel` | 取消生成 | -- |
| `comfyui_list_models` | 列出检查点模型 | -- |
| `comfyui_list_samplers` | 列出采样器 | -- |
| `comfyui_list_schedulers` | 列出调度器 | -- |
| `comfyui_list_loras` | 列出 LoRA | `q`: str = '' |
| `comfyui_list_embeddings` | 列出嵌入 | `q`: str = '' |
| `comfyui_list_custom_nodes` | 列出自定义节点 | `q`: str = '' |
| `comfyui_get_config` | 获取配置 | -- |
| `comfyui_save_config` | 保存配置 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `nai_test_connection` | 测试连接 | -- |
| `nai_get_anlas` | 获取 Anlas 余额 | -- |
| `nai_generate` | 图片生成 | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | 列出模型 | -- |
| `nai_list_samplers` | 列出采样器 | -- |
| `nai_list_noise_schedules` | 列出噪声调度 | -- |
| `nai_get_config` | 获取配置 | -- |
| `nai_save_config` | 保存配置 | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `hailo_genai_status` | 扩展状态 | -- |
| `hailo_genai_model_status` | 模型加载状态 | -- |
| `hailo_genai_model_download` | 下载模型 | `model_name`: str = '' |
| `hailo_genai_model_unload` | 卸载模型 | -- |
| `hailo_llm_generate` | LLM 文本生成 | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | 清除 LLM 上下文 | -- |
| `hailo_vlm_generate` | VLM 图片转文本生成 | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | 运行 Hailo LLM 性能基准测试 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Hailo vs Ollama LLM 性能对比 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | 获取 Hailo GenAI 的 OpenAI 兼容 API 端点信息 | -- |

## Hailo Chat (7)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `hailo_chat_new` | 创建新的 Hailo Chat 对话 | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | 列出 Hailo Chat 对话 | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | 获取包含所有消息的对话 | `conversation_id`: int |
| `hailo_chat_active` | 获取当前活跃对话 ID | -- |
| `hailo_chat_search` | DuckDuckGo 网页搜索（上下文注入用） | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | 重命名对话 | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | 删除对话 | `conversation_id`: int |

## Hailo Remote Tagger (7)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `hailo_tagger_tag_file` | 使用 Hailo 远程标记器标记单个文件 | `file_id`: int |
| `hailo_tagger_batch` | 批量标记多个文件（最多 500） | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | 检查 Hailo 远程标记器连接状态 | -- |
| `hailo_tagger_get_config` | 获取 Hailo 远程标记器配置 | -- |
| `hailo_tagger_save_config` | 保存 Hailo 远程标记器配置 | `config`: dict |
| `hailo_tagger_get_tags` | 获取文件的 Hailo 标签 | `file_id`: int |
| `hailo_tagger_delete_tags` | 删除文件的 Hailo 标签 | `file_id`: int |

## Tagger Server Registry (13)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `tagger_servers_list` | 列出已注册的标签服务器和分布模式 | -- |
| `tagger_servers_add` | 新增标签服务器 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | 更新标签服务器设置 | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | 删除标签服务器 | `server_id`: str |
| `tagger_servers_test` | 测试标签服务器连接 | `server_id`: str |
| `tagger_servers_health` | 检查所有启用服务器的健康状态 | -- |
| `tagger_servers_set_mode` | 设置分布模式 (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | 分布式批量标签（共享队列工作窃取） | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | 取消正在运行的标签服务器集群批处理任务 | -- |
| `tagger_servers_tags` | 获取文件的标签器标签 | `file_id`: int |
| `tagger_servers_delete_tags` | 删除文件的标签器标签 | `file_id`: int |
| `tagger_servers_stats` | 标签器统计（未标签文件数） | -- |
| `tagger_servers_migrate_legacy` | 将旧版 hailo_tagger 配置迁移至注册表格式 | -- |

## 提示词库 (21)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `search_prompts` | 搜索提示词 | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | 获取提示词详情 | `prompt_id`: int |
| `create_prompt` | 创建提示词 | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | 从图片元数据创建提示词 | `file_id`: int |
| `update_prompt` | 更新提示词（部分更新） | `prompt_id`: int, ... |
| `delete_prompt` | 删除提示词 | `prompt_id`: int |
| `list_prompt_folders` | 列出文件夹 | -- |
| `create_prompt_folder` | 创建文件夹 | `name`: str |
| `update_prompt_folder` | 重命名文件夹 | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | 删除文件夹 | `folder_id`: int |
| `move_prompt_to_folder` | 移动提示词到文件夹 | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | 从文件夹移除（移至根目录） | `prompt_id`: int |
| `list_prompt_tags` | 列出标签 | -- |
| `create_prompt_tag` | 创建标签 | `name`: str |
| `delete_prompt_tag` | 删除标签 | `tag_id`: int |
| `set_prompt_tags` | 设置提示词的标签 | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | 批量删除 | `prompt_ids`: list |
| `bulk_move_prompts` | 批量移动 | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | 批量标签 | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | 导出所有提示词为 JSON | -- |
| `import_prompts` | 从 JSON 导入提示词 | `data`: dict |

## 提示词模拟器 (6)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `prompt_dp_analyze` | Dynamic Prompts 语法分析 | `text`: str |
| `prompt_emphasis` | 强调语法转换 | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | A1111 <-> NAI 格式转换 | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | 列出通配符 | -- |
| `prompt_set_wildcard_dirs` | 设置通配符目录 | `dirs`: list |
| `prompt_danbooru_autocomplete` | Danbooru 标签自动补全 | `q`: str |

## 提示词语法 (1)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `analyze_prompt_syntax` | 提示词语法分析（令牌信息） | `text`: str, `engine`: str = 'a1111' |

## SD/NAI 转换 (3)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `convert_sd_to_nai` | SD 转 NAI 提示词转换 | `text`: str |
| `convert_nai_to_sd` | NAI 转 SD 提示词转换 | `text`: str |
| `convert_prompt_batch` | 批量提示词转换 | `items`: list, `direction`: str = 'sd-to-nai' |

## 聊天日志 (16)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `search_chat_logs` | FTS5 全文搜索 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | 按对话分组搜索 | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | 对话详情（所有消息） | `conversation_id`: int |
| `get_chat_full` | get_conversation 的别名 | `conversation_id`: int |
| `get_chat_summary` | AI 生成摘要 | `conversation_id`: int |
| `get_chat_decisions` | AI 提取的决策 | `conversation_id`: int |
| `get_related_conversations` | 相关对话 | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | 按实体搜索对话 | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | 按主题搜索 | `topic`: str, `limit`: int = 50 |
| `search_decisions` | 跨对话搜索决策 | `query`: str, `limit`: int = 50 |
| `import_chat_log` | 从本地文件导入 | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | 导入进度 | -- |
| `get_chatlog_stats` | 聊天日志统计 | -- |
| `delete_conversation` | 删除对话 | `conversation_id`: int |
| `reprocess_chat_logs` | AI 重处理 | `target`: str = 'unprocessed' |
| `text_search` | 跨 MD/聊天/提示词搜索 | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown 查看器 (8)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `search_md_files` | 搜索 Markdown 文件 | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | 获取文件内容 | `file_id`: int |
| `get_md_scan_roots` | 列出扫描根目录 | -- |
| `set_md_scan_roots` | 设置扫描根目录 | `roots`: list |
| `remove_md_scan_root` | 移除扫描根目录 | `index`: int |
| `trigger_md_scan` | 启动扫描 | -- |
| `get_md_scan_status` | 扫描进度 | -- |
| `get_md_stats` | 统计 | -- |

## Freeze & Pull-back (6)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `generate_freeze_pullback` | 生成 Ken Burns 视频 | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | 渲染任务状态 | -- |
| `fpb_check` | 前置条件检查（ffmpeg 等） | -- |
| `fpb_cancel` | 取消生成 | -- |
| `fpb_list_outputs` | 列出输出文件 | -- |
| `fpb_delete_output` | 删除输出文件 | `filename`: str |

## 语音转文字 (8)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `s2t_status` | 后端状态 | -- |
| `s2t_transcribe_video` | 转录视频/音频 | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | 批量转录 | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | 获取已保存的转录 | `file_id`: int |
| `s2t_stream_start` | 开始流式转录 | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | 停止流式转录 | -- |
| `s2t_stream_status` | 获取流式转录状态 | -- |
| `s2t_stream_transcript` | 获取流式转录结果 | -- |

## 统计 (6)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_stats_timeline` | 时间线统计 | `period`: str = 'daily' |
| `get_stats_hourly` | 按小时统计 | -- |
| `get_stats_models` | 模型使用统计 | -- |
| `get_stats_resolutions` | 分辨率分布统计 | -- |
| `get_stats_story` | 图库故事叙述 | -- |
| `get_monthly_report` | 月度报告 | `month`: str = '' |

## 配置文件 (11)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_profiles` | 列出配置文件 | -- |
| `get_profile` | 获取配置文件 | `name`: str |
| `create_profile` | 创建配置文件 | `name`: str, `description`: str = '' |
| `update_profile` | 更新配置文件 | `name`: str, `settings`: dict |
| `delete_profile` | 删除配置文件 | `name`: str |
| `duplicate_profile` | 复制配置文件 | `name`: str, `new_name`: str |
| `rename_profile` | 重命名配置文件 | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | 切换收藏 | `name`: str |
| `export_profile` | 导出配置文件 | `name`: str |
| `import_profile` | 从导出数据导入配置文件 | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | 预览配置文件导入 | `qr_data`: str |

## 文件操作 (4)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `convert_image` | 转换图片格式 | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | 从 ZIP 提取文件 | `file_id`: int, `members`: list |
| `inspect_metadata` | 检查原始元数据 | `file_id`: int |
| `get_share_link` | 生成分享链接 | `file_id`: int |

## SVG 光栅化 (2)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `svg_info` | 获取 SVG 光栅化可用性及后端信息 | — |
| `svg_rasterize` | 将 SVG 光栅化为 PNG/WebP 位图。返回的 base64 可直接用作 img2img 输入 | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## 下载 (1)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `batch_download_zip` | 将多张图片下载为 ZIP | `file_ids`: list, `expected_count`: int = 0 |

## 视频分析 (3)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_video_analysis_config` | 获取视频分析配置 | -- |
| `save_video_analysis_config` | 保存视频分析配置 | `config`: dict |
| `get_video_analysis_status` | 视频分析状态 | -- |

## 备份 (5)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_backups` | 列出备份 | -- |
| `create_backup` | 创建备份 | -- |
| `restore_backup` | 恢复备份 | `filename`: str |
| `delete_backup` | 删除备份 | `filename`: str |
| `get_backup_status` | 备份状态 | -- |

## 归档清理 (7)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `archive_cleanup_scan` | 扫描归档对 | `path`: str = '' |
| `archive_cleanup_execute` | 执行清理 | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | 使用 LLM 验证操作（单个） | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | 使用 LLM 验证操作（批量） | `items`: list |
| `archive_cleanup_get_llm_config` | 获取 LLM 配置 | -- |
| `archive_cleanup_save_llm_config` | 保存 LLM 配置 | `config`: dict |
| `archive_cleanup_list_models` | 列出可用 LLM 模型 | -- |

## 自动扫描监视 (3)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `auto_scan_info` | 监视状态 | -- |
| `auto_scan_start` | 开始文件监视 | -- |
| `auto_scan_stop` | 停止文件监视 | -- |

## 调度器 (6)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_scheduler_status` | 获取任务调度器状态和已注册作业 | -- |
| `list_scheduled_jobs` | 列出所有计划作业的触发器和下次运行时间 | -- |
| `trigger_scheduled_job` | 立即触发计划作业执行 | `job_id`: str |
| `pause_scheduled_job` | 暂停计划作业 | `job_id`: str |
| `resume_scheduled_job` | 恢复已暂停的计划作业 | `job_id`: str |
| `get_scheduler_history` | 获取计划作业最近执行历史 | -- |

## Webhooks (9)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_webhooks` | 列出 Webhooks | -- |
| `create_webhook` | 创建 Webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | 更新 Webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | 删除 Webhook | `webhook_id`: str |
| `test_webhook` | 发送测试事件 | `webhook_id`: str |
| `get_webhook_deliveries` | 交付历史 | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | 创建用于外部触发的 inbound webhook。返回 token URL。 | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | 获取已注册的 inbound webhook 列表。 | — |
| `delete_inbound_webhook` | 删除 inbound webhook。 | `webhook_id`: str |

## 扩展 (25)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_extensions` | 列出扩展 | -- |
| `get_extension_detail` | 扩展详情 | `name`: str |
| `toggle_extension` | 切换启用/禁用 | `name`: str, `enabled`: bool |
| `install_extension` | 从 Git 仓库安装 | `url`: str |
| `update_extension` | 更新扩展 | `name`: str |
| `update_all_extensions` | 一次更新所有扩展 | -- |
| `uninstall_extension` | 卸载扩展 | `name`: str |
| `search_marketplace` | 搜索市场 | `query`: str = '' |
| `refresh_marketplace` | 刷新市场目录 | -- |
| `get_extension_config` | 获取配置 | `name`: str |
| `set_extension_config` | 更新配置 | `name`: str, `values`: dict |
| `get_extension_permissions` | 获取权限信息 | `name`: str |
| `approve_extension_permissions` | 批准/拒绝权限 | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | 静态代码分析 | `name`: str |
| `rescan_extension` | 重新扫描代码 | `name`: str |
| `get_extension_tokens` | 能力令牌状态 | `name`: str |
| `get_extension_integrity` | 文件完整性和监控状态 | `name`: str |
| `get_extension_hooks` | 列出已注册的钩子 | -- |
| `get_extension_isolation_status` | 进程隔离状态 | -- |
| `get_extension_os_isolation_status` | 操作系统级隔离状态 | -- |
| `create_extension` | 创建新的自定义扩展（含脚手架文件） | `name`: str, `description`: str = "" |
| `validate_extension` | 验证扩展清单和代码 | `extension_name`: str |
| `list_extension_files` | 列出自定义扩展的文件 | `extension_name`: str |
| `read_extension_file` | 读取自定义扩展的文件 | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | 向自定义扩展写入文件 | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI 管理 (4)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_uis` | 列出 UI | -- |
| `switch_ui` | 切换活动 UI | `name`: str |
| `install_ui` | 安装 UI | `url`: str |
| `uninstall_ui` | 卸载 UI | `name`: str |

## 设置 (18)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `settings_get_schema` | 获取设置架构 | -- |
| `settings_get_all` | 获取所有设置 | -- |
| `settings_get` | 获取单个设置 | `key`: str |
| `settings_set` | 更新设置 | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | 获取旧版 config.json | -- |
| `save_legacy_config` | 保存旧版 config.json | `config`: dict |
| `secrets_status` | 加密密钥状态 | -- |
| `secrets_export` | 导出加密密钥 | `password`: str |
| `secrets_import` | 导入加密密钥 | `export_json`: str, `password`: str |
| `get_op_status` | 1Password CLI 状态 | -- |
| `delete_op_mapping` | 删除 1Password 映射 | `key`: str |
| `migrate_secrets_to_keychain` | 迁移到操作系统钥匙链 | -- |
| `get_bw_status` | 获取 Bitwarden CLI 集成状态 | -- |
| `list_bw_folders` | 列出 Bitwarden 文件夹 | -- |
| `delete_bw_mapping` | 删除 Bitwarden 字段映射 | `key`: str |
| `list_op_vaults` | 列出 1Password 保险库 | -- |
| `push_secrets_to_1password` | 将所有密钥推送到 1Password 并自动链接 op_secrets 映射 | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | 将所有密钥推送到 Bitwarden 并自动链接映射 | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS 分享 (15)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `share_to_bluesky` | 发布到 Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | 测试 Bluesky 连接 | -- |
| `get_x_share_url` | 获取 X (Twitter) 分享 URL | `file_id`: int |
| `get_sns_preview` | SNS 分享预览 | `file_id`: int |
| `get_sns_config` | 获取 SNS 配置 | -- |
| `save_sns_config` | 保存 SNS 配置 | `config`: dict |
| `bsky_get_pending_notifications` | 从队列获取未读 Bluesky 通知 | -- |
| `bsky_get_notification_queue` | 按筛选条件获取通知队列项 | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | 立即轮询 Bluesky 通知 | -- |
| `bsky_triage_notification` | 设置通知分类结果 | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | 发送自动回复 | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | 获取 Bluesky 监控配置 | -- |
| `bsky_save_monitor_config` | 保存 Bluesky 监控配置 | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | 获取 Bluesky 分类提示词和模板 | -- |
| `bsky_save_triage_prompts` | 保存 Bluesky 分类提示词 | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN 共享 (2)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `create_lan_share` | 创建 LAN 共享令牌 | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | 撤销共享令牌 | `token`: str |

## MCP 客户端 (8)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_mcp_connections` | 列出 MCP 连接 | -- |
| `create_mcp_connection` | 创建 MCP 连接 | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | 更新 MCP 连接 | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | 删除 MCP 连接 | `connection_id`: str |
| `connect_mcp_server` | 连接到 MCP 服务器 | `connection_id`: str |
| `disconnect_mcp_server` | 断开 MCP 服务器连接 | `connection_id`: str |
| `get_mcp_connection_tools` | 列出已连接服务器的工具 | `connection_id`: str |
| `call_mcp_tool` | 调用已连接服务器上的工具 | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `cross_search_get_scan_roots` | 获取 Cross Search 扫描根目录 | -- |
| `cross_search_set_scan_roots` | 设置 Cross Search 扫描根目录 | `roots`: list |
| `cross_search_delete_scan_root` | 按索引删除扫描根 | `index`: int |
| `cross_search_scan` | 启动 Cross Search 文本文件扫描 | -- |
| `cross_search_scan_stop` | 停止正在运行的扫描 | -- |
| `cross_search_scan_status` | 获取扫描进度状态 | -- |
| `cross_search_get_txt` | 获取已索引文件的文本内容 | `file_id`: int |
| `cross_search_open_file` | 在系统文件管理器中打开文件 | `path`: str |
| `cross_search_stats` | 获取 Cross Search 统计信息 | -- |

## 标签字典 (6)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `search_tag_dictionary` | 搜索标签字典 | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | 标签字典统计 | -- |
| `split_tags` | 拆分连接的标签 | `text`: str |
| `import_tag_dictionary` | 导入标签字典 | `data`: dict |
| `clear_tag_dictionary` | 清除标签字典 | -- |
| `get_tag_dict_info` | 获取单个标签的详细信息 | `tag`: str |

## 奖杯 (1)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `list_trophies` | 列出奖杯 | -- |

## 源代码浏览 (3)

安全浏览项目源代码的只读工具。三层安全防护保护访问：路径规范化、扩展名白名单和敏感文件黑名单。详见 [`docs/api/source.md`](source.md)。

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `source_tree` | 显示目录树 | `path`: str = '', `depth`: int = 3 |
| `source_read` | 读取文件内容（带行号） | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | 按文本搜索源代码 | `query`: str, `glob`: str = '', `limit`: int = 30 |

## 帮助 (3)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `help_toc` | 帮助目录 | -- |
| `help_get_section` | 获取章节内容 | `section`: str |
| `help_search` | 搜索帮助 | `query`: str, `limit`: int = 5 |

## 系统信息 (3)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_server_info` | 服务器信息 | -- |
| `get_inference_info` | 推理引擎信息 | -- |
| `get_market_quotes` | 市场信息 | -- |

## 系统更新 (5)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `check_for_update` | 检查 GitHub 是否有新版本可用 | -- |
| `get_update_status` | 获取当前安装方式和版本 | -- |
| `apply_system_update` | 应用可用的更新（仅 git/portable） | `confirm`: str |
| `check_unified_updates` | 一次检查系统 + 所有扩展的更新状态 | `force`: bool (optional) |
| `apply_unified_updates` | 一次更新系统 + 扩展（自动备份配置） | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## 建议 (4)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_suggestions` | 标签/提示词自动补全 | `q`: str, `limit`: int = 10 |
| `suggest_tags` | 标签自动补全 | `q`: str, `limit`: int = 10 |
| `suggest_lora` | LoRA 名称自动补全 | `q`: str = '' |
| `suggest_embedding` | 嵌入名称自动补全 | `q`: str = '' |

## 日志与调试 (9)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `get_recent_logs` | 获取最近日志 | `limit`: int = 100 |
| `get_debug_log` | 输出调试日志 | `lines`: int = 200 |
| `clear_debug_log` | 清除调试日志 | -- |
| `get_cache_info` | 缓存统计 | -- |
| `clear_cache` | 清除缓存 | -- |
| `rebuild_groups` | 重建目录组 | -- |
| `list_dirs` | 列出目录 | `path`: str = '' |
| `debug_file_meta` | 文件调试元数据 | `file_id`: int |
| `debug_model_check` | 模型可用性检查 | -- |

## 代理安全网关 (25)

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `agent_status` | 整体安全功能状态 | -- |
| `agent_kill` | 激活 Kill Switch（立即阻止所有工具） | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | 停用 Kill Switch | -- |
| `agent_circuit_breaker_status` | Circuit Breaker 状态 | -- |
| `agent_circuit_breaker_reset` | 重置 Circuit Breaker | -- |
| `agent_budget_status` | Budget Tracker 状态 | -- |
| `agent_budget_reset` | 重置 Budget Tracker | -- |
| `agent_approval_status` | 列出待审批请求 | -- |
| `agent_approval_respond` | 响应审批请求 | `request_id`: str, `action`: str |
| `agent_approval_history` | 审批历史 | `limit`: int = 50 |
| `agent_scope_status` | Scope Fence 状态 | -- |
| `agent_scope_get` | 获取会话范围 | `session_id`: str |
| `agent_scope_set` | 设置会话范围 | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | 删除会话范围 | `session_id`: str |
| `agent_tool_level` | 检查工具安全级别 | `tool_name`: str = '' |
| `agent_auto_approve_list` | 列出自动审批规则 | -- |
| `agent_auto_approve_add` | 添加自动审批规则 | `tool_name`: str |
| `agent_auto_approve_remove` | 移除自动审批规则 | `index`: int |
| `agent_undo` | 撤销操作 | `journal_id`: int |
| `agent_undoable` | 列出可撤销的操作 | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | 搜索操作日志 | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | 日志统计 | -- |
| `agent_anomaly_status` | 异常检测状态 | -- |
| `agent_anomaly_alerts` | 异常告警历史 | `limit`: int = 50 |
| `agent_anomaly_reset` | 重置异常检测 | -- |

---

## GitHub Integration (12)

GitHub 账号的 Issue 监控、分类与报告。

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `github_list_accounts` | 列出已注册的 GitHub 账号（令牌已遮蔽） | — |
| `github_fetch_issues` | 获取账号仓库的 Issue | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | 获取并分类 Issue（valid_bug / skip / needs_info），返回优先度报告 | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | 获取 Issue 详细信息，格式化为 Claude Code 分析用，含评论 | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | 确认 GitHub API 速率限制 | `account_label`: str |
| `github_get_pending_issues` | 从本地队列获取待处理 Issue | -- |
| `github_get_issue_queue` | 按状态筛选获取 Issue 队列 | `status`: str = "" |
| `github_poll_issues` | 立即轮询 GitHub Issue | -- |
| `github_triage_queue_item` | 设置队列 Issue 的分类结果 | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | 驳回队列 Issue（可选自动关闭） | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | 获取 Issue/PR/Discussion 分类提示词 | `repo`: str = "" |
| `github_save_triage_prompts` | 保存分类提示词 | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## 调试工具 (9)

系统验证和调试工具。仅在 `YU_DEBUG_MODE=1` 时可用。

| 工具 | 说明 | 参数 |
|------|-------------|------------|
| `debug_health_check` | 系统健康检查：Flask、DB 表、Schema 版本 | -- |
| `debug_validate_counts` | API 统计与 DB 计数交叉验证 | -- |
| `debug_validate_search` | 使用测试模式验证搜索 API | `patterns`: str = "all" |
| `debug_validate_collection` | 验证集合缓存计数与 DB | -- |
| `debug_validate_annotations` | 验证注解数据完整性 | -- |
| `debug_sample_files` | 随机采样文件并报告字段完整性 | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | 写入-读取-更新-删除往返测试 | -- |
| `debug_readonly_query` | 执行只读 SQL 查询 | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | 一次性运行所有调试验证 | -- |

---

## LoRA Dataset Manager (15)

| 工具 | 说明 | 参数 |
|------|------|------|
| `list_lora_projects` | 项目列表 | -- |
| `get_lora_project` | 获取项目详情 | `project_id`: int |
| `create_lora_project` | 创建项目 | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | 更新项目 | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | 删除项目 | `project_id`: int |
| `get_lora_project_tags` | 获取标签汇总 | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | 字幕预览 | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | 导出数据集 | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | 获取导出进度 | `project_id`: int |
| `list_lora_checkpoints` | Checkpoint 文件列表 | -- |
| `preview_lora_train_command` | 预览训练命令 (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | 开始 LoRA 训练 | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | 获取训练状态和日志 | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | 标签排除预设列表 | -- |
| `create_lora_tag_preset` | 创建标签排除预设 | `name`: str, `tags`: list |

## LLM 端点 (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm-endpoints-list` | 已配置的 LLM 端点列表 | — |
| `llm-endpoints-set` | 添加或更新 LLM 端点 | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | 移除 LLM 端点 | `category`: str |
| `llm-endpoints-test` | 测试 LLM 端点连接 | `category`: str |
| `llm-chat` | 委托聊天给已配置的 LLM | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## 服务器模式 (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `server-mode-get` | 获取当前服务器模式 | — |
| `server-subsystems-status` | 子系统状态列表 | — |

## 无法通过 MCP 使用的功能

以下功能由于 MCP 的限制不作为工具公开：

- **二进制响应**：缩略图（`/api/thumbnail/`）、原始图片（`/api/original/`）、ZIP 下载、视频文件
- **操作系统对话框**：文件夹选择对话框（`/api/tools/select-folder`）、文件管理器启动（`/api/open-folder/`）
- **SSE 流**：日志流（`/api/logs/stream`）
- **认证页面**：PIN 输入界面、LAN Share 访客页面
