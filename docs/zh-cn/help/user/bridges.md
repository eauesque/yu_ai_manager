# Bridge 联动

Bridge 功能可从 YU AI Manager 直接将提示词发送至各种 AI 图片生成工具。

## 支持的 Bridge

### SD WebUI Bridge
与 Stable Diffusion WebUI (Automatic1111 / Forge) 联动。
- 提示词的收发
- 生成参数的传输

### NAI Bridge
与 NovelAI 联动。
- 提示词语法的自动转换（SD <-> NAI）
- 品质标签的自动插入

#### Vibe Transfer（NAI 药水）与 encode-vibe 缓存

NAI V4+ 模型需要先通过 `/ai/encode-vibe` API 对参考图像进行编码（**每次 2 Anlas**）才能用于生成。

为避免相同图像重复生成时浪费 Anlas，编码结果会缓存到本地：

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **键值**：原始图像 SHA256 + 模型名称 + 信息提取度（0.01 步进）
- **上限**：默认 500 MB。可在 Settings > NAI Bridge > "Vibe encode cache (MB)" 修改（0 = 禁用）
- **LRU 淘汰**：超出上限时，后台线程按最旧顺序删除

### ComfyUI Bridge
与 ComfyUI 联动。
- 将提示词插入工作流
- 输出格式的自定义

## 批次生成

三种 Bridge 的主要生成路径均支持批次生成（A1111 兼容语义）。

### Batch count / Batch size

- **Batch count** — 连续生成的次数（时间方向）。客户端每次调用一次 API
- **Batch size** — 单次 API 调用并行生成的张数（VRAM 方向）。NAI Bridge 不显示此项
- 总张数 = Batch count × Batch size

固定 Seed 时，loop 内的 seed 以 `base + i` 递增（与 A1111 相同）。`-1`（随机）时，每次都会生成新的随机 seed。

### 停止按钮

| Bridge | 单次 (count=1) | loop (count>1) |
|---|---|---|
| NAI | 无停止按钮 | 仅「完成本张后停止」 |
| SD WebUI | 「停止」(服务器 cancel API) | 「完成本张后停止」+「停止」 |
| ComfyUI | 「停止」(服务器 cancel API) | 「完成本张后停止」+「停止」 |

- **停止（即时）** — 中断正在进行的 API 调用并停止 loop。SD WebUI / ComfyUI 同时调用服务器 cancel API
- **完成本张后停止** — 让当前正在生成的图片完成后，不再发出下一次请求

NAI Bridge 的单次生成没有停止按钮，原因是 NAI API 在接受 fetch 的瞬间即扣除 Anlas（点数）。切断 HTTP 连接无法停止服务器端的生成或退费，因此显示停止按钮只会造成误解，故意图性地不显示。

### VRAM 注意事项

提高 Batch size 会按张数等比增加服务器 GPU 的 VRAM 使用量。SDXL 搭配 Batch size 4 以上可能导致 OOM，建议从 1 开始尝试。

## 品质预设

各 Bridge 工具栏上的「QP」按钮可一键插入品质提升标签。

内置预设：
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

也可创建自定义预设。

## 分辨率预设

SD WebUI Bridge 和 ComfyUI Bridge 的 Width/Height 输入框上方有「Resolution Preset」下拉菜单和 ⇄ 交换按钮，可一键选择常用分辨率。

- **SD 1.5** — 适用于 SD1.5 系模型的 5 种常用分辨率（512 基准）
- **SDXL Trained** — SDXL 官方训练桶 9 种（品质优先）
- **SDXL Cheat Sheet** — 电影・摄影的长宽比以 8 的倍数近似的 12 种（构图优先，来源 [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet)）

选择 `Custom` 会保留当前的 W/H 值。应用预设后手动编辑 W/H 会自动回到 `Custom`。⇄ 按钮可交换宽高。

Cheat Sheet 分辨率超出官方桶范围，部分模型可能产生轻微的构图偏差。

> ComfyUI Bridge 仅在 Simple 模式下应用，Raw JSON Workflow 模式的节点值不会被修改。

## Bridge 间传输

可在 Bridge 之间直接传输提示词。SD <-> NAI 之间的语法会自动转换。

## 发送至 Bridge

从图片详细模态窗口的工具栏，可将当前显示的图片的提示词或图片本身直接发送至生成 Bridge。

- **发送提示词 ▾** — 将显示图片的提示词发送至 NAI Bridge / SD WebUI / ComfyUI 的其中一个。以 NAI 语法编写的提示词，若目标为 SD/ComfyUI 则自动转换为 SD 语法，反之亦然。NAI v4 的角色提示词（positive/negative），若目标为 NAI Bridge 则保持结构化发送，否则合并至主提示词后发送。
- **发送图片 (img2img) ▾** — 将显示图片的完整分辨率直接设置至 NAI Bridge / SD WebUI / ComfyUI 的 img2img 槽位。ComfyUI 从 v4.121.0 起支持。
- **重混 ▾**（v4.121.3〜） — **同时**发送提示词与图片。对相同图片微调提示词并重新生成时，一键完成。可选目标：NAI / SD WebUI / ComfyUI。

按钮显示条件：
- 发送提示词：图片包含提示词元数据（positive/negative 或角色信息）时
- 发送图片：当前显示的媒体为图片（静态图片 / 动态图片 / 视频）时。视频时将捕获当前播放位置的帧发送（v4.121.20〜）
- 重混：以上两个条件均成立时

注意事项：
- PDF、音频不会显示「发送图片」
- 视频帧发送时，仅发送当前播放位置的 1 帧 PNG，不会发送原始视频
- 若提示词转换失败，会以原始语法发送，并在目标 Bridge 界面显示警告 toast
- 仅发送提示词/图片。采样器、步数、CFG、Seed 等参数不会在目标端还原（使用 Bridge 端的默认值或上次的设定值）
