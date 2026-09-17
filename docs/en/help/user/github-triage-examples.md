# GitHub Triage Prompt Examples

Triage prompts are instructions sent to the AI when classifying GitHub issues, PRs, and discussions. You can edit them freely in **GitHub Integration > Settings > Triage Prompts**.

Below are example prompts you can copy and customize.

---

## Issue Prompts

### Default (English, strict)

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

### Japanese version

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

### Lenient (accept feature requests too)

```
Review the following GitHub issue and classify it.

Categories:
- valid_bug: Has reproduction steps, error info, or clear description of unexpected behavior.
- feature_request: Requests new functionality or enhancement. Mark as valid.
- needs_info: Potentially valid but missing key details. Mark as valid with note.
- invalid: Spam, off-topic, or purely emotional with no technical content.

Return the category and a one-line reason.
```

### Strict (security-focused)

```
Evaluate this GitHub issue for security implications and technical validity.

CRITICAL (immediate action):
- Reports a security vulnerability, data leak, or authentication bypass
- Includes proof-of-concept or exploit details

VALID (standard bug):
- Technical bug with reproduction steps and error evidence

INVALID (reject):
- Feature requests, questions, emotional complaints, non-English, no technical facts

Return: CRITICAL / VALID / INVALID with reason.
If CRITICAL, flag for immediate human review.
```

### Multilingual (accept non-English)

```
Review this GitHub issue regardless of language. Determine if it is a valid bug report.

Valid: reproduction steps, error logs, or clear technical description in any language.
Invalid: emotional only, spam, or no technical content.

Return verdict and reason in English.
```

---

## PR Prompts

### Default (reject all)

```
Do not accept pull requests. Close automatically.
```

### Accept with review

```
Review this pull request for code quality and relevance.

Accept (valid):
- Fixes a documented bug or addresses an open issue
- Code follows project conventions
- Includes tests or test plan

Reject (invalid):
- Unrelated changes or scope creep
- No issue reference
- Breaks existing functionality

Return: accept / reject with reason.
```

### Accept bugfixes only

```
Only accept pull requests that fix existing bugs.

Valid: References an open issue, contains a targeted fix, minimal scope.
Invalid: Feature additions, refactoring, documentation-only, or unrelated changes.

Return verdict and reason.
```

---

## Discussion Prompts

### Default (close all)

```
Discussions are closed. No action required.
```

### Monitor for bug reports

```
Check if this discussion contains an unreported bug.

If the discussion describes a reproducible bug with error details,
flag it as "potential_bug" for issue creation.
Otherwise mark as "no_action".

Return: potential_bug / no_action with reason.
```

### Community engagement

```
Classify this discussion:

- question: User asking for help. Respond if a clear answer exists in docs.
- bug_report: Describes a bug. Flag for issue creation.
- feature_idea: Interesting feature suggestion. Flag for review.
- off_topic: Not related to the project. No action.

Return category and suggested response (if applicable).
```
