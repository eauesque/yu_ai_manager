# Bridge 剪贴板快捷键

在 NAI Bridge / ComfyUI Bridge / SD WebUI Bridge 各页面上，按下快捷键即可
将剪贴板的文本立即发送到提示字段。从其他窗口复制提示后，无需先点击文本区
也能应用。

## 快捷键

| 操作系统 | 按键 |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

这是在浏览器原生粘贴（`Ctrl`+`V`）之外新增的功能，不会干扰既有的粘贴行为。

## 行为

1. 打开任一 Bridge 页面
2. 从外部复制文本（`Ctrl`+`C`）
3. 在 Bridge 页面上按下 `Ctrl`+`Alt`+`V`
4. 粘贴目标：
   - 如焦点在文本区 → 插入到该文本区的光标位置
   - 如无焦点 → 插入到正向提示字段（NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`）
5. 成功时显示 toast "已粘贴剪贴板内容"

## 目标字段

| Bridge | 目标优先顺序 |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## 浏览器权限

使用浏览器的 **Clipboard API**（`navigator.clipboard.readText()`），首次使用时
浏览器可能会请求剪贴板读取权限。若拒绝则无法运行。

在不支持 Clipboard API 的旧版浏览器，会显示 toast "剪贴板 API 不可用"
且不执行任何操作。常规的 `Ctrl`+`V` 粘贴仍可正常使用。

## 限制

- 部分浏览器要求 HTTPS 或 `localhost` 才能使用 `navigator.clipboard`
  （Chrome 允许 `localhost`）
- 仅支持纯文本，不支持图片或富文本
- 即使焦点在 `<textarea>` 以外的元素（例如 `contenteditable`）也不会粘贴
