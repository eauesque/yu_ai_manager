# WD-Tagger 配置文件 UI 使用指南

本文介绍 WD-Tagger **配置文件管理 UI**（v4.197.0+ 新增）的使用方法。

## 1. 概述

- **配置文件（profile）**会将 WD-Tagger 的模型文件、标签定义、阈值、预处理等设置打包在一起。
- 在 Tools 页面 → **WD-Tagger** 区域点击 `管理配置文件...` 打开（以弹窗形式显示）。
- 弹窗内可在 **列表（List）** 与 **表单（Form）** 间切换。

## 2. 列表（List）

### 2.1 徽标（Builtin / User）

- `builtin`: 内置配置文件（只读）
- `user`: 用户配置文件（可创建/编辑/删除）
- `↻` 标记: 表示该配置文件使用相同 `id` **覆盖内置**配置文件

### 2.2 筛选（All / User / Builtin）

顶部按钮：

- `全部`
- `用户`
- `内置`

### 2.3 按钮（操作）

每行右侧操作：

- `复制`: 复制配置文件并打开表单（需要修改内置配置文件时请用此方式）
- `编辑`: 编辑用户配置文件（内置不可编辑）
- `删除`: 删除用户配置文件（内置不可删除）
- `导出`: 下载配置文件 JSON（`.json`）
- `测试（干跑下载）`: **不进行实际下载**，验证所需文件是否可从 HuggingFace 获取

右上角操作：

- `+ 新建`: 创建空白新配置文件
- `导入`: 从 JSON 创建配置文件（Upload / Paste）

## 3. 表单（Form）

表单由 5 个 accordion 部分组成。

### 3.1 Metadata

- `id`: 配置文件标识（之后不可修改）
- `显示名称`: 列表显示名称
- `profile_version`: 配置文件结构版本（通常无需修改）

### 3.2 Model & Files

- `model_id`: HuggingFace 模型 id（例如：`SmilingWolf/wd-swinv2-tagger-v3`）
- `adapter_family`: 仅在需要时设置
- `backend`: 仅在需要时设置
- `hf_subdir`: HuggingFace 仓库内子目录（仅在需要时）
- `文件`:
  - `name`: 要下载的文件名（例如：`model.onnx`）
  - `必填`: 勾选后 Test 会视为必需
  - `size_hint_mb`: 可选大小提示
  - `+ 添加文件` / `移除`: 添加/移除行

### 3.3 Tag source

指定标签定义从哪里读取。

- `csv`:
  - `文件（file）`
  - `分隔符（delimiter）`
  - `名称列（name_col）`
  - `分类列（category_col）`（可选）
  - `分类映射（category_map）`（可选）
- `json_list`:
  - `文件（file）`
  - `结构（schema）`（需要时）
- `json_dict`:
  - `文件（file）`
  - `映射（mapping）`（需要时）
- `composite`:
  - `来源（sources）`: 合成规则

### 3.4 Threshold source

指定阈值从哪里读取。

- `global_per_category`: 在 UI 直接设置分类阈值（`通用` / `角色` / `版权` / `作者` / `元信息`）
- `per_tag`: 引用文件并指定回退
  - `文件（file）`
  - `回退模式（fallback.mode）`: `global` / `category_default`
  - `回退值（fallback.value）`

### 3.5 Preprocess & Categories

预处理与分类设置。

- 预处理（`preprocess_spec`）: `input_size`、`dtype`、`layout`、`channel_order`、`resize_strategy`（`letterbox` / `longest_side_pad` / `stretch`）、`scale`、`mean`、`std`
- 分类:
  - `支持的分类`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. 导入 / 导出（Import / Export）

### 4.1 导入（Import）

点击 `导入` 后会出现两个标签页：

- `上传 JSON`: 上传 `.json` 文件
- `粘贴 JSON`: 在文本框粘贴 JSON

导入后会打开表单，确认内容后点击 `保存`。

### 4.2 导出（Export）

在列表中点击 `导出` 下载所选配置文件 JSON。

## 5. 测试（dry-run download）

- `测试（干跑下载）` 会检查 `files` 中列出的文件能否从 **HuggingFace** 获取。
- 成功时会显示类似 `下载 OK：共 {n} 个文件（{total} MB）` 的提示。
- 失败时会显示原因（见下一节）。

## 6. 常见错误（简要说明）

- `id_conflict`: 已存在相同 `id` 的用户配置文件
- `id_immutable`: `id` 不可修改（改名用 复制 → 删除）
- `in_use`: 配置文件当前处于启用状态，无法删除
- `validation_failed`: JSON / 表单值校验失败（`{detail}` 为详细信息）
- `profile_too_large`: 导入 JSON 超过 1MB 上限
- `ssrf_blocked`: 已阻止跳转到 HuggingFace 以外的地址（SSRF 防护）
- `hf_unavailable`: HuggingFace 不可用或返回异常响应
- `timeout`: 超时（60s）
- `required_missing`: 缺少必需文件（被标记为 `必填`）

## 7. 限制（重要）

- 内置（`builtin`）配置文件不可编辑/删除，请用 `复制` 创建用户副本。
- `id` 不可修改。要改名：`复制` → `删除` 旧的。
- 导入的配置文件 JSON 上限 **1MB**。
- `测试` 仅允许 HuggingFace 域名（SSRF allowlist）：
  - `huggingface.co`
  - `hf.co`
