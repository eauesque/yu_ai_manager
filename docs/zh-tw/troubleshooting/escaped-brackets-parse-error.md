# 跳脫括號 `\(` `\[` `\{` 導致語法著色遺失

**版本**：在 v2.21.26 中修復
**嚴重度**：P1 -- 影響所有萬用字元檔案
**發現日期**：2026-02-23

---

## 症狀

WC Manager 在萬用字元檔案（例如 `__characters_genshin_impact__`）中遇到 `\(` 後會遺失語法著色。檔案的前幾行以正確顏色算繪，但在包含 `\(` 的項目之後，所有行的醒目提示完全遺失。

具體表現：
1. `\(` 中的 `(` 算繪為紅色 ERROR 標記。
2. 之後所有項目完全遺失語法醒目提示。
3. LoRA 標籤 `<lora:...>` 和權重 `(tag:1.2)` 也遺失顏色。

### 受影響的資料範例

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- 第 1 行：`\(` 觸發 ERROR。`genshin impact\)` 之後的所有內容成為無效標記。
- 第 2 行及之後：前一行的 `matchParen` 掃描剩餘文字並將其吸收為過大的標記，破壞所有顏色。
- 第 3 行在 `\(` 出現在 `()` 內部時正常運作，因為 `findMatchingClose` 正確處理了跳脫。這種不對稱性是造成混淆的根源。

---

## 根本原因

### 頂層分詞器流程（修復前）

```
輸入: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → 無比對器比對 → findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK（不在 specials 中）
                '(' → 在 specials 中 → break → 傳回 j=6
3. TEXT 標記: "yuko \" [0, 6)     ← '\' 作為文字被消費
4. i=6: '(' → matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1，掃描內部：
   - 'g','i','r','l','s'... → OK
   - '\)' → 作為跳脫略過 (j += 2)  ← '\)' 未被識別為閉括號！
   - ',' ' ' 'g','i','r','l','s'... → 掃描到後續行
   - 到達 EOF 但未找到比對的 ')'
   → 傳回 null
7. matchParen: result === null → ERROR 標記 { type: 'error', value: '(' }
8. i=7: 剩餘文字被分段解析；應連續的標記被分割，
   破壞後續行的所有醒目提示
```

**核心問題**：`findTextEnd` 將 `\` 作為普通文字消費，然後在後面的 `(` 處停止。裸 `(` 到達主迴圈中的 `text[i] === '('` 檢查並觸發 `matchParen`。在 `findMatchingClose` 內部，`\)` 被作為跳脫略過，因此永遠不會被識別為閉括號。比對搜尋一直執行到 EOF。

### 括號內部與頂層的不對稱性

`findMatchingClose` 已有跳脫處理：
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

這對於 `(artist:example_artist \(art style\):1.2)` 這樣的**括號內部**跳脫正確運作。外部 `()` 先比對，內部 `\(` `\)` 對被略過。

然而在**頂層**，`\` 和 `(` 在不同步驟中處理，永遠不會被識別為單一跳脫序列。這是 bug 的根本原因。

---

## 修復

### 在 `findTextEnd()` 中新增跳脫括號處理

**檔案**：`extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // 跳脫括號：\( \) \[ \] \{ \} → 作為字面文字消費
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      // ... 現有檢查 ...
    }
    return j;
}
```

### 修復後的流程

```
輸入: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → 偵測到跳脫括號 → j += 2（消費兩者）
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → 偵測到跳脫括號 → j += 2
                ')' 已被消費 → ',' → specials → break
3. TEXT 標記: "yuko \(girls und panzer\)" [0, 30)  ← 整個範圍為一個標記
4. i=30: ',' → COMMA 標記
5. 解析正常繼續
```

### 變更範圍

- 所有 6 個跳脫序列（`\(`、`\)`、`\[`、`\]`、`\{`、`\}`）現在在頂層作為文字消費。
- 括號運算式內部的跳脫處理（`findMatchingClose` / `findMatchingBrace`）未變更。
- `()`、`[]`、`{}` 的正常括號比對不受影響。
- 此修復符合提示語法規格第 9 節中定義的跳脫表示。

---

## 驗證

| 測試 | 預期結果 | 狀態 |
|------|---------|------|
| `lumine \(genshin impact\)` | 單一 TEXT 標記，無 ERROR | PASS |
| 多個 `\(` 行之後的 `(masterpiece:1.2)` | 被識別為 SD_WEIGHT | PASS |
| `\[brackets\]` 和 `\{braces\}` | TEXT 標記，無 ERROR | PASS |
| 普通 `(masterpiece:1.2)` | 作為 SD_WEIGHT 運作 | PASS |
| 普通 `{emphasis}` | 作為 NAI_EMPHASIS 運作 | PASS |
| 普通 `[suppress]` | 作為 NAI_SUPPRESS 運作 | PASS |
| 括號內的 `\(`：`(artist:a \(b\):1.2)` | 作為 SD_WEIGHT 運作 | PASS |
| 純文字重建 | 與輸入比對 | PASS |

---

## 相關檔案

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` -- 修復位置
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` -- 分詞器主迴圈
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` -- `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` -- `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` -- 第 9 節跳脫規格
