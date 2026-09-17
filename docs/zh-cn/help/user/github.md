# GitHub Integration

## 概述

GitHub Integration 让您可以直接从 YU AI Manager 管理 GitHub 的仓库、Issue、Pull Request、Discussion 和 Release。支持多个 GitHub 账户，令牌以加密方式安全存储。仪表盘提供通知和仓库统计的快速概览，并内置 AI 驱动的 Issue 分类功能。

## 设置

### 获取 GitHub Personal Access Token (PAT)

1. 登录 GitHub，前往 **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. 点击 **Generate new token (classic)**
3. 输入令牌名称并设置有效期限
4. 在权限范围中勾选 **`repo`**（需要完整的仓库访问权限）
5. 点击 **Generate token**，复制显示的令牌

> **注意**：令牌只会显示一次，请务必在离开页面前复制。

### 添加账户

1. 从扩展功能启动器点击 **GitHub** 卡片，或直接前往 `/ext/github`
2. 打开 **Settings** 标签页
3. 点击 **添加账户**
4. 填写以下信息：
   - **标签**：账户的显示名称（例如"个人"、"工作"）
   - **令牌**：上述步骤获取的 PAT
   - **仓库**：要监控的仓库，使用 `owner/repo` 格式（可填入多个）
5. 保存后，从下拉菜单中选择账户

## 功能

### 仪表盘

选择账户后，仪表盘会自动加载。

- **通知**：列出未读的 GitHub 通知
- **仓库统计**：以卡片形式显示星标数、Fork 数和开放 Issue 数
- **摘要卡片**：快速浏览所有监控中仓库的概况

### Issues

- 按仓库和状态（open/closed）筛选
- 查看 Issue 详情，包括正文、评论和标签
- 创建新 Issue
- **分类功能**：AI 自动分类
  - `valid_bug` — 确认的 Bug 报告
  - `needs_info` — 需要补充信息
  - `skip` — 无需处理
- **Issue 队列**：自动轮询 GitHub 新 Issue 并在本地排队。MCP 客户端（Claude Desktop）连接时批量通知待处理 Issue。

### Pull Requests

- 列出和筛选 Pull Request
- 查看差异统计（新增行数、删除行数、变更文件数）
- 详细视图中可查看各文件的变更内容

### Discussions

- 通过 GraphQL API 获取 Discussion 列表
- 显示类别徽章和已回答状态

### Releases

- 查看监控仓库的最新 Release
- 阅读 Release 说明

### Settings

- 添加、编辑、删除账户，以及启用/停用切换
- 查看 API 速率限制状态
- 设置语言过滤器和调度间隔
- 配置 Issue 队列轮询间隔、无效 Issue 自动关闭、MCP 连接通知
- 编辑 Issue、PR、Discussion 的分类提示词（参见[示例](/help/github-triage-examples)）

### Issue 队列

Issue 队列会定期轮询 GitHub，并将新 Issue 存储在本地。

- **轮询**：通过调度器自动执行（间隔可配置，默认 60 分钟）
- **通知**：MCP 连接时，将待处理 Issue 批量报告给 Claude Desktop
- **分类**：可将队列中的每个 Issue 分类为有效或无效
- **自动关闭**：无效 Issue 可附带模板评论在 GitHub 上自动关闭
- **手动轮询**：点击 Settings 中的"Poll Now"可立即获取

### 分类提示词

自定义用于 Issue、PR 和 Discussion 分类时的 AI 指令。

- 每种类型（Issue、PR、Discussion）都有独立的可编辑提示词
- 提供默认提示词，可通过"恢复默认"随时还原
- 多语言和多种风格的模板请参见[分类提示词示例](/help/github-triage-examples)
- 提示词存储在 config.json 中（不含机密信息，因此不加密）

## MCP 集成

GitHub Integration 提供 12 个 MCP 工具，可与 Claude Code 配合使用：

- 列出和查看 Issue
- 列出和查看 Pull Request
- 获取通知
- 获取和更新分类提示词
- 管理 Issue 队列（待处理列表、分类、驳回、轮询）

MCP 工具让您在开发时无需离开编辑器即可访问 GitHub 信息。

## 使用技巧

- **多账户管理**：将个人账户和工作账户分开管理更为方便
- **令牌权限**：`repo` 权限涵盖所有核心功能。若要访问组织的私有仓库，可能需要另外在组织中授权 SSO
- **分类功能**：对于 Issue 数量较多的仓库，利用分类功能自动排序优先级可提高效率
- **速率限制**：GitHub API 有每小时请求上限，可在 Settings 标签页中查看剩余额度
- **令牌安全性**：令牌在服务器端以加密方式存储，不会以明文形式保存
- **仪表盘更新**：切换账户时数据会自动重新加载
