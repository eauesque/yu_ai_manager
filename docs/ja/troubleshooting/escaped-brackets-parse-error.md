# エスケープ括弧 `\(` `\[` `\{` によるシンタックスカラー消失バグ

**バージョン**: v2.21.26 で修正
**深刻度**: P1 — ワイルドカードファイル全般に影響
**発見日**: 2026-02-23

---

## 症状

WC Manager でワイルドカードファイル（例: `__characters_genshin_impact__`）を開くと、
ファイル冒頭の数行だけシンタックスカラーが正常に動作し、
`\(` を含むエントリ以降のすべての行で色が消える。

具体的には:
1. `\(` の `(` が赤色の ERROR トークンとして表示される
2. その行以降のすべてのエントリでシンタックスハイライトが失われる
3. LoRA タグ `<lora:...>` やウェイト `(tag:1.2)` も色がつかなくなる

### 影響を受けるデータの例

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- 1行目: `\(` で ERROR 発生、`genshin impact\)` 以降が不正なトークンに
- 2行目以降: 前行の `matchParen` が残りテキスト全体を走査し巨大トークンに取り込むため、色が消える
- 3行目のように `()` の内部に `\(` がある場合は `findMatchingClose` のエスケープ処理で正常動作（この差が混乱の原因だった）

---

## 根本原因

### トークナイザのトップレベル処理フロー（修正前）

```
入力: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → どのマッチャーにも一致しない → findTextEnd(text, 0) 呼び出し
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK（specials に含まれない）
                '(' → specials に含まれる → break → j=6 を返す
3. TEXT トークン: "yuko \" [0, 6)     ← '\' がテキストに含まれる
4. i=6: '(' → matchParen(text, 6) 呼び出し
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, 内部を走査:
   - 'g','i','r','l','s'... → OK
   - '\)' → エスケープとしてスキップ (j += 2)  ← '\)' は閉じ括弧として認識されない！
   - ',' ' ' 'g','i','r','l','s'... → 次の行も走査
   - ファイル末尾まで走査しても一致する ')' が見つからない
   → return null
7. matchParen: result === null → ERROR トークン { type: 'error', value: '(' }
8. i=7: 以降のテキストも断片的にパースされるが、本来1トークンに収まるべき
   テキストが分断され、後続行のすべてのハイライトが破壊される
```

**問題の本質**: `findTextEnd` が `\` を通常テキストとして消費した後、
次の `(` で停止する。裸の `(` がメインループの `text[i] === '('` チェックに
到達し、`matchParen` が起動される。`findMatchingClose` 内部では `\)` を
エスケープとしてスキップするため、`\)` は閉じ括弧として認識されず、
一致検索がファイル末尾まで走り続ける。

### 括弧内部 vs トップレベルの非対称性

`findMatchingClose` には既にエスケープ処理がある:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

これは `(artist:example_artist \(art style\):1.2)` のような**括弧内部**の
エスケープでは正しく動作する（外側の `()` が先にマッチし、内部の `\(` `\)`
はスキップされる）。

しかし**トップレベル**の `\(` では、`\` と `(` が別々のステップで処理される
ため、エスケープとして認識されない。これがバグの根本原因。

---

## 修正内容

### `findTextEnd()` にエスケープ括弧ハンドリングを追加

**ファイル**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // Escaped brackets: \( \) \[ \] \{ \} → consume as literal text
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      // ... 既存のチェック ...
    }
    return j;
}
```

### 修正後のフロー

```
入力: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0) 呼び出し
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → エスケープ括弧検出 → j += 2（2文字消費）
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → エスケープ括弧検出 → j += 2
                ')' は消費済み → ',' → specials → break
3. TEXT トークン: "yuko \(girls und panzer\)" [0, 30)  ← 全体が1つのテキスト
4. i=30: ',' → COMMA トークン
5. 以降正常にパース続行
```

### 変更の影響範囲

- `\(`, `\)`, `\[`, `\]`, `\{`, `\}` の6種がトップレベルでテキストとして扱われる
- 括弧式内部（`findMatchingClose` / `findMatchingBrace`）のエスケープ処理は変更なし
- 通常の括弧 `()`, `[]`, `{}` によるマッチャー動作への影響なし
- プロンプト構文仕様書 Section 9 に定義済みのエスケープ記法に準拠

---

## 検証項目

| テスト | 期待結果 | 状態 |
|--------|----------|------|
| `lumine \(genshin impact\)` | TEXT トークン1つ、ERROR なし | PASS |
| 複数行の `\(` エントリ後に `(masterpiece:1.2)` | SD_WEIGHT として正常認識 | PASS |
| `\[brackets\]` と `\{braces\}` | TEXT トークン、ERROR なし | PASS |
| 通常の `(masterpiece:1.2)` | SD_WEIGHT として正常動作 | PASS |
| 通常の `{emphasis}` | NAI_EMPHASIS として正常動作 | PASS |
| 通常の `[suppress]` | NAI_SUPPRESS として正常動作 | PASS |
| 括弧内部の `\(`: `(artist:a \(b\):1.2)` | SD_WEIGHT として正常動作 | PASS |
| プレーンテキスト再構築 | 入力と一致 | PASS |

---

## 関連ファイル

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — 修正箇所
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — トークナイザメインループ
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Section 9 エスケープ仕様
