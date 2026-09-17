# Bridge Clipboard Shortcut

On the NAI Bridge / ComfyUI Bridge / SD WebUI Bridge pages, a hotkey lets you
instantly send clipboard text into the prompt field. When you've copied a prompt
from another window, you can apply it without first clicking into the textarea.

## Shortcut

| OS | Keys |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

This is added alongside the browser's native paste (`Ctrl`+`V`) and does not
interfere with existing paste behavior.

## Behavior

1. Open one of the Bridge pages
2. Copy text from an external source (`Ctrl`+`C`)
3. Press `Ctrl`+`Alt`+`V` while the Bridge page has focus
4. Target selection:
   - If a textarea is focused → inserted at the caret position in that textarea
   - If nothing is focused → inserted into the positive prompt field (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. On success, a toast "Clipboard text inserted" is shown

## Target Fields

| Bridge | Target priority |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Browser Permissions

This uses the browser's **Clipboard API** (`navigator.clipboard.readText()`),
so the browser may prompt you for clipboard read permission on first use.
If you deny it, the feature will not work.

On older browsers where the Clipboard API is unavailable, a toast "Clipboard
API not available" is shown and nothing happens. Regular `Ctrl`+`V` paste
continues to work as before.

## Limitations

- Some browsers require HTTPS or `localhost` for `navigator.clipboard` to be
  available (Chrome does allow `localhost`)
- Only plain text is supported — not images or rich text
- Non-`<textarea>` elements (e.g. `contenteditable` regions) are not targeted
  even when focused
