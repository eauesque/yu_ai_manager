# Bridge 剪貼簿快捷鍵

在 NAI Bridge / ComfyUI Bridge / SD WebUI Bridge 各頁面上，按下快捷鍵即可
將剪貼簿的文字立即送入提示欄位。從其他視窗複製提示後，不需要先點擊文字區
也能套用。

## 快捷鍵

| 作業系統 | 按鍵 |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

這是在瀏覽器原生的貼上（`Ctrl`+`V`）之外新增的功能，不會干擾既有的貼上行為。

## 行為

1. 開啟任一 Bridge 頁面
2. 從外部複製文字（`Ctrl`+`C`）
3. 在 Bridge 頁面上按下 `Ctrl`+`Alt`+`V`
4. 貼上目標：
   - 若焦點在文字區 → 插入到該文字區的游標位置
   - 若沒有焦點 → 插入到正向提示欄位（NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`）
5. 成功時顯示 toast「已貼上剪貼簿內容」

## 目標欄位

| Bridge | 目標優先順序 |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## 瀏覽器權限

使用瀏覽器的 **Clipboard API**（`navigator.clipboard.readText()`），首次使用時
瀏覽器可能要求剪貼簿讀取權限。若拒絕則無法運作。

在不支援 Clipboard API 的舊版瀏覽器，會顯示 toast「剪貼簿 API 無法使用」
且不執行任何操作。一般的 `Ctrl`+`V` 貼上仍可正常使用。

## 限制

- 部分瀏覽器要求 HTTPS 或 `localhost` 才能使用 `navigator.clipboard`
  （Chrome 允許 `localhost`）
- 僅支援純文字，不支援圖片或 RTF 等
- 即使焦點在 `<textarea>` 以外的元素（例如 `contenteditable`）也不會貼上
