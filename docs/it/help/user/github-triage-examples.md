# Raccolta Esempi di Prompt Triage GitHub

I prompt di triage sono istruzioni inviate all'AI per classificare issue/PR/discussion di GitHub. Possono essere modificati liberamente in **GitHub Integration > Settings > Triage Prompts**.

Copiare e personalizzare gli esempi seguenti.

---

## Prompt per Issue

### Predefinito (inglese, rigoroso)

```
Review the following GitHub issue and determine whether it is a technically valid bug report.

Valid (valid) criteria:
- Concrete reproduction steps are provided
- Error log or stack trace is included
- Environment info (OS, version, etc.) is present

Invalid (invalid) criteria:
- Emotional text only, no technical facts
- Feature request, not a bug
- Written in a language other than English
- No actionable technical information

Return your verdict (valid / invalid) and the reason.
```

### Versione italiana

```
Esamina la seguente issue GitHub e determina se si tratta di un bug report tecnicamente valido.

Criteri valido (valid):
- I passi di riproduzione sono specificati concretamente
- È presente un log di errore o stack trace
- Sono presenti informazioni sull'ambiente (OS, versione ecc.)

Criteri non valido (invalid):
- Solo testo emotivo
- Richiesta di nuova funzionalità
- Scritto in lingua diversa dall'inglese
- Nessun fatto tecnico

Restituisci il tuo giudizio e la motivazione.
```

### Criteri permissivi (accetta anche richieste funzionalità)

```
以下のGitHub issueを分類しなさい。

カテゴリ:
- valid_bug: 再現手順、エラー情報、または予期しない挙動の明確な説明がある。
- feature_request: 新機能や改善の要望。有効として扱う。
- needs_info: 有効かもしれないが重要な情報が不足。有効として扱い注記を添える。
- invalid: スパム、無関係、または技術的内容のない感情的な文章のみ。

カテゴリと理由を1行で返しなさい。
```

### Rigoroso (priorità sicurezza)

```
このGitHub issueをセキュリティ上の影響と技術的妥当性の観点から評価しなさい。

CRITICAL（即時対応）:
- セキュリティ脆弱性、データ漏洩、認証バイパスの報告
- PoCやエクスプロイトの詳細を含む

VALID（通常のバグ）:
- 再現手順とエラー証拠のある技術的バグ

INVALID（却下）:
- 機能要求、質問、感情的な不満、英語以外、技術的事実なし

CRITICAL / VALID / INVALID と理由を返しなさい。
CRITICALの場合は人間による即時レビューが必要と記載すること。
```

### Multilingua (accetta lingue diverse dall'inglese)

```
言語を問わず、このGitHub issueが有効なバグ報告かどうか判定しなさい。

有効: 任意の言語で再現手順、エラーログ、または明確な技術的説明がある。
無効: 感情的なもののみ、スパム、技術的内容なし。

判定と理由を英語で返しなさい。
```

---

## Prompt per PR

### Predefinito (rifiuta tutto)

```
Do not accept pull requests. Close automatically.
```

### Accettazione con review

```
このプルリクエストのコード品質と関連性をレビューしなさい。

受け入れ（valid）:
- 文書化されたバグの修正、またはオープンissueへの対応
- プロジェクト規約に従ったコード
- テストまたはテスト計画を含む

却下（invalid）:
- 無関係な変更やスコープの拡大
- issue への参照なし
- 既存機能の破壊

accept / reject と理由を返しなさい。
```

### Solo correzioni bug

```
バグ修正のプルリクエストのみ受け入れる。

有効: オープンissueへの参照あり、的を絞った修正、最小限のスコープ。
無効: 機能追加、リファクタリング、ドキュメントのみ、無関係な変更。

判定と理由を返しなさい。
```

---

## Prompt per Discussion

### Predefinito (chiudi tutto)

```
Discussions are closed. No action required.
```

### Monitoraggio segnalazioni bug

```
このDiscussionに未報告のバグが含まれていないか確認しなさい。

エラー詳細を含む再現可能なバグが記述されている場合、
issue作成のため "potential_bug" としてフラグを立てる。
それ以外は "no_action" とする。

potential_bug / no_action と理由を返しなさい。
```

### Risposta alla community

```
このDiscussionを分類しなさい:

- question: ヘルプを求めるユーザー。ドキュメントに明確な回答があれば回答する。
- bug_report: バグの記述。issue作成のためフラグを立てる。
- feature_idea: 興味深い機能提案。レビューのためフラグを立てる。
- off_topic: プロジェクトに無関係。対応不要。

カテゴリと推奨対応（該当する場合）を返しなさい。
```

## Categorizzazione bug

Usa label:
- `bug` — Comportamento non corretto
- `feature` — Richiesta feature
- `documentation` — Miglioramenti doc
- `enhancement` — Miglioramento esistente

## Template risposta

Template per risposte comuni:

```
Grazie per report.
Versione: {version}
Steps to reproduce:
1. ...
2. ...
3. ...

Expected: 
Actual:

Environment: {os} {browser}
```

## Automazione

Etichette automatiche basate keyword in body issue:
- "crash" → `bug/critical`
- "slow" → `performance`
- "docs" → `documentation`

## Best practice

1. Uno issue = un problema
2. Includi version in report
3. Fornisci reproducibile steps
4. Allega screenshot se UI
5. Usa code blocks per log
