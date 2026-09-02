# WD-Tagger 設定檔 UI 操作指南

本文件說明 WD-Tagger **設定檔管理 UI**（v4.197.0+ 新增）的使用方式。

## 1. 概要

- **設定檔（profile）**會把 WD-Tagger 的模型檔案、標籤定義、閾值、前處理等設定打包在一起。
- 從 Tools 頁面 → **WD-Tagger** 區塊 → 點擊 `管理設定檔...` 開啟（以模態視窗顯示）。
- 模態視窗內可在 **列表畫面（List）** 與 **表單畫面（Form）** 之間切換。

## 2. 列表畫面（List）

### 2.1 徽章（Builtin / User）

- `builtin`: 內建設定檔（唯讀）
- `user`: 使用者設定檔（可建立/編輯/刪除）
- `↻` 標記: 代表此設定檔以相同 `id` **覆寫內建**設定檔

### 2.2 篩選（All / User / Builtin）

上方可用按鈕篩選：

- `全部`
- `使用者`
- `內建`

### 2.3 按鈕（操作）

每列右側操作：

- `複製`: 複製設定檔並打開表單（要修改內建設定檔時請用此方式）
- `編輯`: 編輯使用者設定檔（內建不可編輯）
- `刪除`: 刪除使用者設定檔（內建不可刪除）
- `匯出`: 下載設定檔 JSON（`.json`）
- `測試（乾跑下載）`: **不做實際下載**，確認所需檔案是否可由 HuggingFace 取得

右上角操作：

- `+ 新增`: 建立空白的新設定檔
- `匯入`: 從 JSON 建立設定檔（Upload / Paste）

## 3. 表單畫面（Form）

表單分為 5 個 accordion 區塊。

### 3.1 Metadata

- `id`: 設定檔識別碼（之後不可變更）
- `顯示名稱`: 列表顯示用名稱
- `profile_version`: 設定檔結構版本（通常不必改）

### 3.2 Model & Files

- `model_id`: HuggingFace 模型 id（例如：`SmilingWolf/wd-swinv2-tagger-v3`）
- `adapter_family`: 需要時才設定
- `backend`: 需要時才設定
- `hf_subdir`: HuggingFace 倉庫內子資料夾（需要時）
- `檔案`:
  - `name`: 要下載的檔名（例如：`model.onnx`）
  - `必填`: 勾選後 Test 會視為必需
  - `size_hint_mb`: 可選的大小提示
  - `+ 新增檔案` / `移除`: 新增/移除列

### 3.3 Tag source

指定標籤定義從哪裡讀取。

- `csv`:
  - `檔案（file）`: 從 `files` 中選擇
  - `分隔符（delimiter）`
  - `名稱欄位（name_col）`
  - `分類欄位（category_col）`（可選）
  - `分類對照表（category_map）`（可選）
- `json_list`:
  - `檔案（file）`
  - `結構（schema）`（需要時）
- `json_dict`:
  - `檔案（file）`
  - `對應表（mapping）`（需要時）
- `composite`:
  - `來源（sources）`: 合成規則

### 3.4 Threshold source

指定閾值從哪裡讀取。

- `global_per_category`: 在 UI 直接設定分類閾值（`一般` / `角色` / `版權` / `作者` / `元資訊`）
- `per_tag`: 參照檔案並設定 fallback
  - `檔案（file）`
  - `備援模式（fallback.mode）`: `global` / `category_default`
  - `備援值（fallback.value）`

### 3.5 Preprocess & Categories

前處理與分類相關設定。

- 前處理（`preprocess_spec`）: `input_size`、`dtype`、`layout`、`channel_order`、`resize_strategy`（`letterbox` / `longest_side_pad` / `stretch`）、`scale`、`mean`、`std`
- 分類:
  - `支援的分類`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 匯入（Import）

點擊 `匯入` 後可看到兩個分頁：

- `上傳 JSON`: 上傳 `.json` 檔
- `貼上 JSON`: 在文字區貼上 JSON

匯入後會打開表單，確認內容並按 `儲存`。

### 4.2 匯出（Export）

列表的 `匯出` 可下載所選設定檔 JSON。

## 5. 測試（dry-run download）

- `測試（乾跑下載）` 會檢查 `files` 內列出的檔案是否可從 **HuggingFace** 取得。
- 成功時會顯示類似 `下載 OK：共 {n} 個檔案（{total} MB）` 的訊息。
- 失敗時會顯示原因（見下一節）。

## 6. 常見錯誤（簡要）

- `id_conflict`: 已存在相同 `id` 的使用者設定檔
- `id_immutable`: `id` 不可變更（改名用 複製 → 刪除）
- `in_use`: 設定檔目前為啟用中，無法刪除
- `validation_failed`: JSON / 表單值未通過驗證（`{detail}` 有細節）
- `profile_too_large`: 匯入 JSON 超過 1MB 上限
- `ssrf_blocked`: 已封鎖 HuggingFace 以外的重新導向（SSRF 防護）
- `hf_unavailable`: HuggingFace 不可用或回應不正確
- `timeout`: 逾時（60s）
- `required_missing`: 缺少必填檔案（被標記為 `必填`）

## 7. 限制事項（重要）

- 內建（`builtin`）不可編輯/刪除，請用 `複製` 建立使用者副本。
- `id` 不可變更。要改名：`複製` → `刪除` 舊的。
- 匯入的設定檔 JSON 上限 **1MB**。
- `測試` 只允許 HuggingFace 網域（SSRF allowlist）：
  - `huggingface.co`
  - `hf.co`
