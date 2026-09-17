# GitHub Integration

## 概述

GitHub Integration 讓您可以直接從 YU AI Manager 管理 GitHub 的倉庫、Issue、Pull Request、Discussion 和 Release。支援多個 GitHub 帳戶，令牌以加密方式安全儲存。儀表板提供通知和倉庫統計的快速概覽，並內建 AI 驅動的 Issue 分類功能。

## 設定

### 取得 GitHub Personal Access Token (PAT)

1. 登入 GitHub，前往 **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. 點擊 **Generate new token (classic)**
3. 輸入令牌名稱並設定有效期限
4. 在權限範圍中勾選 **`repo`**（需要完整的倉庫存取權限）
5. 點擊 **Generate token**，複製顯示的令牌

> **注意**：令牌只會顯示一次，請務必在離開頁面前複製。

### 新增帳戶

1. 從擴充功能啟動器點擊 **GitHub** 卡片，或直接前往 `/ext/github`
2. 開啟 **Settings** 分頁
3. 點擊 **新增帳戶**
4. 填寫以下資訊：
   - **標籤**：帳戶的顯示名稱（例如「個人」、「工作」）
   - **令牌**：上述步驟取得的 PAT
   - **倉庫**：要監控的倉庫，使用 `owner/repo` 格式（可填入多個）
5. 儲存後，從下拉選單中選擇帳戶

## 功能

### 儀表板

選擇帳戶後，儀表板會自動載入。

- **通知**：列出未讀的 GitHub 通知
- **倉庫統計**：以卡片形式顯示星星數、Fork 數和開放 Issue 數
- **摘要卡片**：快速瀏覽所有監控中倉庫的概況

### Issues

- 依倉庫和狀態（open/closed）篩選
- 檢視 Issue 詳情，包括內文、留言和標籤
- 建立新 Issue
- **分類功能**：AI 自動分類
  - `valid_bug` — 確認的錯誤回報
  - `needs_info` — 需要補充資訊
  - `skip` — 無需處理
- **Issue 佇列**：自動輪詢 GitHub 新 Issue 並在本地排隊。MCP 客戶端（Claude Desktop）連線時批次通知待處理 Issue。

### Pull Requests

- 列出和篩選 Pull Request
- 檢視差異統計（新增行數、刪除行數、變更檔案數）
- 詳細檢視中可查看各檔案的變更內容

### Discussions

- 透過 GraphQL API 取得 Discussion 列表
- 顯示類別徽章和已回答狀態

### Releases

- 檢視監控倉庫的最新 Release
- 閱讀 Release 說明

### Settings

- 新增、編輯、刪除帳戶，以及啟用/停用切換
- 檢視 API 速率限制狀態
- 設定語言篩選器和排程間隔
- 設定 Issue 佇列輪詢間隔、無效 Issue 自動關閉、MCP 連線通知
- 編輯 Issue、PR、Discussion 的分類提示詞（參見[範例](/help/github-triage-examples)）

### Issue 佇列

Issue 佇列會定期輪詢 GitHub，並將新 Issue 儲存在本地。

- **輪詢**：透過排程器自動執行（間隔可設定，預設 60 分鐘）
- **通知**：MCP 連線時，將待處理 Issue 批次報告給 Claude Desktop
- **分類**：可將佇列中的每個 Issue 分類為有效或無效
- **自動關閉**：無效 Issue 可附帶範本留言在 GitHub 上自動關閉
- **手動輪詢**：點擊 Settings 中的「Poll Now」可立即取得

### 分類提示詞

自訂用於 Issue、PR 和 Discussion 分類時的 AI 指令。

- 每種類型（Issue、PR、Discussion）都有獨立的可編輯提示詞
- 提供預設提示詞，可透過「還原預設」隨時恢復
- 多語言和多種風格的範本請參見[分類提示詞範例](/help/github-triage-examples)
- 提示詞儲存在 config.json 中（不含機密資訊，因此不加密）

## MCP 整合

GitHub Integration 提供 12 個 MCP 工具，可與 Claude Code 搭配使用：

- 列出和檢視 Issue
- 列出和檢視 Pull Request
- 取得通知
- 取得和更新分類提示詞
- 管理 Issue 佇列（待處理列表、分類、駁回、輪詢）

MCP 工具讓您在開發時無需離開編輯器即可存取 GitHub 資訊。

## 使用技巧

- **多帳戶管理**：將個人帳戶和工作帳戶分開管理更為方便
- **令牌權限**：`repo` 權限涵蓋所有核心功能。若要存取組織的私有倉庫，可能需要另外在組織中授權 SSO
- **分類功能**：對於 Issue 數量較多的倉庫，利用分類功能自動排序優先順序可提高效率
- **速率限制**：GitHub API 有每小時請求上限，可在 Settings 分頁中查看剩餘額度
- **令牌安全性**：令牌在伺服器端以加密方式儲存，不會以明文形式保存
- **儀表板更新**：切換帳戶時資料會自動重新載入
