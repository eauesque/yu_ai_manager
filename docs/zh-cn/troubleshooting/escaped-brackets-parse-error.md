# 转义括号 `\(` `\[` `\{` 导致语法着色丢失

**版本**：在 v2.21.26 中修复
**严重度**：P1 -- 影响所有通配符文件
**发现日期**：2026-02-23

---

## 症状

WC Manager 在通配符文件（例如 `__characters_genshin_impact__`）中遇到 `\(` 后会丢失语法着色。文件的前几行以正确颜色渲染，但在包含 `\(` 的条目之后，所有行的高亮完全丢失。

具体表现：
1. `\(` 中的 `(` 渲染为红色 ERROR 标记。
2. 之后所有条目完全丢失语法高亮。
3. LoRA 标签 `<lora:...>` 和权重 `(tag:1.2)` 也丢失颜色。

### 受影响的数据示例

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- 第 1 行：`\(` 触发 ERROR。`genshin impact\)` 之后的所有内容成为无效标记。
- 第 2 行及之后：前一行的 `matchParen` 扫描剩余文本并将其吸收为过大的标记，破坏所有颜色。
- 第 3 行在 `\(` 出现在 `()` 内部时正常工作，因为 `findMatchingClose` 正确处理了转义。这种不对称性是造成混淆的根源。

---

## 根本原因

### 顶层分词器流程（修复前）

```
输入: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → 无匹配器匹配 → findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK（不在 specials 中）
                '(' → 在 specials 中 → break → 返回 j=6
3. TEXT 标记: "yuko \" [0, 6)     ← '\' 作为文本被消费
4. i=6: '(' → matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1，扫描内部：
   - 'g','i','r','l','s'... → OK
   - '\)' → 作为转义跳过 (j += 2)  ← '\)' 未被识别为闭括号！
   - ',' ' ' 'g','i','r','l','s'... → 扫描到后续行
   - 到达 EOF 但未找到匹配的 ')'
   → 返回 null
7. matchParen: result === null → ERROR 标记 { type: 'error', value: '(' }
8. i=7: 剩余文本被分段解析；应连续的标记被分割，
   破坏后续行的所有高亮
```

**核心问题**：`findTextEnd` 将 `\` 作为普通文本消费，然后在后面的 `(` 处停止。裸 `(` 到达主循环中的 `text[i] === '('` 检查并触发 `matchParen`。在 `findMatchingClose` 内部，`\)` 被作为转义跳过，因此永远不会被识别为闭括号。匹配搜索一直运行到 EOF。

### 括号内部与顶层的不对称性

`findMatchingClose` 已有转义处理：
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

这对于 `(artist:example_artist \(art style\):1.2)` 这样的**括号内部**转义正确工作。外部 `()` 先匹配，内部 `\(` `\)` 对被跳过。

然而在**顶层**，`\` 和 `(` 在不同步骤中处理，永远不会被识别为单个转义序列。这是 bug 的根本原因。

---

## 修复

### 在 `findTextEnd()` 中添加转义括号处理

**文件**：`extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // 转义括号：\( \) \[ \] \{ \} → 作为字面文本消费
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      // ... 现有检查 ...
    }
    return j;
}
```

### 修复后的流程

```
输入: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → 检测到转义括号 → j += 2（消费两者）
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → 检测到转义括号 → j += 2
                ')' 已被消费 → ',' → specials → break
3. TEXT 标记: "yuko \(girls und panzer\)" [0, 30)  ← 整个范围为一个标记
4. i=30: ',' → COMMA 标记
5. 解析正常继续
```

### 变更范围

- 所有 6 个转义序列（`\(`、`\)`、`\[`、`\]`、`\{`、`\}`）现在在顶层作为文本消费。
- 括号表达式内部的转义处理（`findMatchingClose` / `findMatchingBrace`）未变更。
- `()`、`[]`、`{}` 的正常括号匹配不受影响。
- 此修复符合提示语法规范第 9 节中定义的转义表示。

---

## 验证

| 测试 | 预期结果 | 状态 |
|------|---------|------|
| `lumine \(genshin impact\)` | 单个 TEXT 标记，无 ERROR | PASS |
| 多个 `\(` 行之后的 `(masterpiece:1.2)` | 被识别为 SD_WEIGHT | PASS |
| `\[brackets\]` 和 `\{braces\}` | TEXT 标记，无 ERROR | PASS |
| 普通 `(masterpiece:1.2)` | 作为 SD_WEIGHT 工作 | PASS |
| 普通 `{emphasis}` | 作为 NAI_EMPHASIS 工作 | PASS |
| 普通 `[suppress]` | 作为 NAI_SUPPRESS 工作 | PASS |
| 括号内的 `\(`：`(artist:a \(b\):1.2)` | 作为 SD_WEIGHT 工作 | PASS |
| 纯文本重建 | 与输入匹配 | PASS |

---

## 相关文件

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` -- 修复位置
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` -- 分词器主循环
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` -- `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` -- `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` -- 第 9 节转义规范
