# Bridge Clipboard ショートカット

NAI Bridge / ComfyUI Bridge / SD WebUI Bridge の各ページで、ホットキーを押すと
クリップボードのテキストをプロンプト欄へ即座に送信できます。別のウィンドウから
プロンプトをコピーしてきた際、テキストエリアをクリックせずに反映できます。

## ショートカット

| OS | キー |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

ブラウザ標準の貼り付け (`Ctrl`+`V`) とは別に追加されたもので、既存の貼り付け
動作に干渉しません。

## 動作

1. いずれかの Bridge ページを開きます
2. 外部からテキストをコピー (`Ctrl`+`C`)
3. Bridge ページ内で `Ctrl`+`Alt`+`V` を押下
4. 貼り付け先が決まります:
   - テキストエリアにフォーカスがある場合 → そのエリアのキャレット位置に挿入
   - フォーカスが無い場合 → ポジティブプロンプトに挿入 (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. 成功時はトースト「クリップボードを挿入しました」を表示

## 対象フィールド

| Bridge | 挿入対象 (優先順) |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## ブラウザ権限

ブラウザの **Clipboard API** (`navigator.clipboard.readText()`) を使用するため、
初回はブラウザからクリップボード読み取りの許可を求められる場合があります。
許可しないと動作しません。

Clipboard API が利用できない古いブラウザでは、トースト「クリップボード API が
利用できません」を表示して何もしません。通常の `Ctrl`+`V` は引き続き利用できます。

## 制限

- HTTPS または `localhost` で提供されていないページでは `navigator.clipboard` が
  利用できないブラウザがあります (Chrome は `localhost` なら OK)
- 画像やリッチテキストは対象外 — 純粋なプレーンテキストのみ
- `<textarea>` 以外の要素 (例: contenteditable) にはフォーカスしていても貼り付けません
