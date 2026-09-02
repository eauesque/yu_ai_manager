# GitHub トリアージプロンプト例文集

トリアージプロンプトは、GitHub の issue / PR / discussion を分類する際に AI に送る指示文です。**GitHub Integration > Settings > Triage Prompts** で自由に編集できます。

以下の例文をコピーしてカスタマイズしてください。

---

## Issue プロンプト

### デフォルト（英語・厳格）

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

### 日本語版

```
以下のGitHub issueを精査し、技術的に有効なバグ報告かどうか判定しなさい。

有効（valid）の条件:
- 再現手順が具体的に記載されている
- エラーログまたはスタックトレースがある
- 環境情報（OS、バージョン等）がある

無効（invalid）の条件:
- 感情的な文章のみ
- 機能追加要求
- 英語以外で書かれている
- 技術的事実が何もない

判定結果とその理由を返しなさい。
```

### 緩い基準（機能要求も受け付ける）

```
以下のGitHub issueを分類しなさい。

カテゴリ:
- valid_bug: 再現手順、エラー情報、または予期しない挙動の明確な説明がある。
- feature_request: 新機能や改善の要望。有効として扱う。
- needs_info: 有効かもしれないが重要な情報が不足。有効として扱い注記を添える。
- invalid: スパム、無関係、または技術的内容のない感情的な文章のみ。

カテゴリと理由を1行で返しなさい。
```

### 厳格（セキュリティ重視）

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

### 多言語対応（英語以外も受け付ける）

```
言語を問わず、このGitHub issueが有効なバグ報告かどうか判定しなさい。

有効: 任意の言語で再現手順、エラーログ、または明確な技術的説明がある。
無効: 感情的なもののみ、スパム、技術的内容なし。

判定と理由を英語で返しなさい。
```

---

## PR プロンプト

### デフォルト（全て却下）

```
Do not accept pull requests. Close automatically.
```

### レビュー付き受け入れ

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

### バグ修正のみ受け入れ

```
バグ修正のプルリクエストのみ受け入れる。

有効: オープンissueへの参照あり、的を絞った修正、最小限のスコープ。
無効: 機能追加、リファクタリング、ドキュメントのみ、無関係な変更。

判定と理由を返しなさい。
```

---

## Discussion プロンプト

### デフォルト（全て閉鎖）

```
Discussions are closed. No action required.
```

### バグ報告の監視

```
このDiscussionに未報告のバグが含まれていないか確認しなさい。

エラー詳細を含む再現可能なバグが記述されている場合、
issue作成のため "potential_bug" としてフラグを立てる。
それ以外は "no_action" とする。

potential_bug / no_action と理由を返しなさい。
```

### コミュニティ対応

```
このDiscussionを分類しなさい:

- question: ヘルプを求めるユーザー。ドキュメントに明確な回答があれば回答する。
- bug_report: バグの記述。issue作成のためフラグを立てる。
- feature_idea: 興味深い機能提案。レビューのためフラグを立てる。
- off_topic: プロジェクトに無関係。対応不要。

カテゴリと推奨対応（該当する場合）を返しなさい。
```
