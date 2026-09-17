# SNS Share & Bluesky Monitor

## 概述

SNS Share 让您可以直接从 YU AI Manager 将 AI 生成的图像分享到 Bluesky 和 X (Twitter)。发帖文本通过可自定义的模板自动生成，图像元数据变量会自动展开。Bluesky Monitor 添加了通知监控功能，支持 AI 驱动的分类和自动回复。

## 设置

### 获取 Bluesky App Password

1. 登录 [bsky.app](https://bsky.app)，前往 **设置 > App Passwords**
2. 点击 **添加 App Password**
3. 输入名称（例如"YU AI Manager"），点击 **创建 App Password**
4. 复制显示的密码

> **注意**：App Password 只会显示一次，请务必在关闭对话框前复制。请勿使用 Bluesky 主密码。

### 在 YU AI Manager 中配置

1. 从导航菜单打开 **Settings**
2. 切换到 **SNS** 标签页
3. 填写以下信息：
   - **Bluesky 句柄**：您的句柄（例如 `yourname.bsky.social`）
   - **App Password**：上述步骤获取的 App Password
   - **发帖模板**：发帖文本模板（参见[模板变量](#模板变量)）
4. 点击 **保存**

### 测试连接

保存凭据后，点击 **测试连接** 验证 YU AI Manager 能否通过 Bluesky 认证。测试成功后会显示您的句柄和显示名称。

## 功能

### 分享到 Bluesky

从图像详情视图直接将图像分享到 Bluesky。

1. 打开图像详情模态框
2. 点击 **SNS** 按钮
3. 检查并编辑生成的发帖文本
4. 点击 **发布到 Bluesky**

- 发帖文本从已配置的模板生成，元数据变量自动展开
- 图像会自动压缩和调整大小以符合 Bluesky 的 1 MB 上传限制
- 帖子限制为 **300 grapheme**（超出部分会自动截断）
- 可以选择是否附加图像

### 分享到 X (Twitter)

通过 Web Intent（在浏览器中打开 X 的编辑页面）将图像信息分享到 X。

1. 打开图像详情模态框
2. 点击 **SNS** 按钮
3. 点击 **分享到 X**

这会在新的浏览器标签页中打开 X 的编辑页面，并自动填入模板生成的文本。发布前可以编辑文本。X 不支持自动附加图像，需要手动添加。

### Bluesky Monitor

Bluesky Monitor 轮询您的 Bluesky 通知，并在本地排队进行分类和回复。

#### 通知类型

- **提及**：有人在帖子中提到了您
- **回复**：有人回复了您的帖子
- **引用**：有人引用了您的帖子
- **关注**：有人关注了您
- **点赞**：有人点赞了您的帖子
- **转发**：有人转发了您的帖子

#### 轮询

通知以可配置的间隔自动获取（默认：30 分钟，最小：5 分钟）。也可以从 Settings 或通过 MCP 工具立即触发轮询。

#### 队列系统

每条通知以 **pending**（待处理）状态进入队列，之后可以转换为：

- **notified** -- 已报告给 MCP 客户端（Claude Desktop）
- **dismissed** -- 标记为无需关注

#### 分类

AI 驱动的分类判断每条通知是否需要回复：

- **valid** -- 需要关注（真实的问题、Bug 报告、协作请求等）
- **invalid** -- 可以忽略（普通称赞、垃圾信息、机器人内容等）

每种通知类型（提及、回复、引用）都有可自定义的分类提示词。提供默认提示词，可随时恢复。

#### 自动回复

对于被分类为 valid 的提及、回复和引用，可以发送基于模板的自动回复：

- 在 Monitor 配置中启用自动回复
- 为每种通知类型自定义回复模板
- 回复限制为 300 grapheme

#### 自动忽略

关注、点赞和转发可以自动忽略以减少队列噪音。每种类型可在 Settings 中独立切换。

#### MCP 连接时通知

当 MCP 客户端（Claude Desktop）连接时，待处理的通知会被批量报告，以便在开发过程中查看。

### Settings

SNS 设置在 Settings 页面的 **SNS** 标签页中配置：

- **Bluesky 凭据**：句柄和 App Password（密码加密存储，显示为掩码）
- **发帖模板**：包含变量占位符的模板文本
- **Monitor 设置**：
  - 轮询间隔（分钟）
  - 关注、点赞、转发的自动忽略
  - 自动回复启用/停用
  - 提及、回复、引用的分类提示词
  - 提及、回复、引用的自动回复模板

## MCP 集成

SNS Share & Bluesky Monitor 提供 15 个 MCP 工具：

**分享（6 个工具）**：
- `share_to_bluesky` -- 将图像发布到 Bluesky
- `get_x_share_url` -- 获取 X Web Intent URL
- `get_sns_preview` -- 预览模板展开
- `test_bluesky_connection` -- 测试 API 连接
- `get_sns_config` / `save_sns_config` -- 读取/写入 SNS 配置

**通知队列（5 个工具）**：
- `bsky_get_pending_notifications` -- 获取待处理通知
- `bsky_get_notification_queue` -- 获取带过滤器的队列项
- `bsky_triage_notification` -- 设置分类结果（valid/invalid）
- `bsky_send_auto_response` -- 发送通知回复
- `bsky_poll_notifications` -- 立即触发轮询

**Monitor 配置（4 个工具）**：
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- 读取/写入 Monitor 设置
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- 读取/写入分类提示词和回复模板

## 模板变量

发帖模板中可使用的变量：

| 变量 | 说明 |
|---|---|
| `{positive_short}` | 正向提示词（前 100 个字符） |
| `{positive}` | 正向提示词全文 |
| `{negative_short}` | 负向提示词（前 50 个字符） |
| `{model}` | 模型名称 |
| `{seed}` | 种子值 |
| `{steps}` | 采样步数 |
| `{cfg}` | CFG 缩放比例 |
| `{sampler}` | 采样器名称 |
| `{size}` | 图像尺寸 |
| `{tags}` | 前 5 个标签 |
| `{filename}` | 文件名 |

默认模板：`{positive_short}`

## 使用技巧

- **App Password 安全性**：请务必使用 App Password，切勿使用 Bluesky 主密码。App Password 可随时在 bsky.app 设置中撤销
- **速率限制**：Bluesky API 有速率限制，请避免连续快速发帖。图像上传也计入速率限制
- **Grapheme 计算**：Bluesky 的 300 字限制使用 grapheme 集群而非字符数。CJK 字符按 1 个 grapheme 计算
- **图像压缩**：超过 1 MB 的图像会自动调整大小。如果图像准备失败，将仅以文本形式发布
- **Monitor 轮询间隔**：根据通知频率设置轮询间隔。通知量大的账户可使用较短间隔
- **自动忽略**：启用关注、点赞和转发的自动忽略可以集中精力处理需要回复的通知
- **分类提示词**：根据您的沟通风格和收到的互动类型自定义分类提示词
