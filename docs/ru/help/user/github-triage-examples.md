# Примеры промптов для триажа GitHub

Промпты для триажа — инструкции для AI при классификации Issue / PR / Discussion GitHub.
Редактируются в **GitHub Integration > Settings > Triage Prompts**.

Скопируйте примеры ниже и настройте под свои нужды.

---

## Промпты для Issue

### По умолчанию (английский, строгий)

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

### Многоязычный (принимает не-английские)

```
Regardless of language, determine whether this GitHub issue is a valid bug report.

Valid: Reproduction steps, error log, or clear technical description in any language.
Invalid: Emotional content only, spam, no technical content.

Return verdict and reason in English.
```

### Строгий (приоритет безопасности)

```
Evaluate this GitHub issue from a security impact and technical validity standpoint.

CRITICAL (immediate action):
- Security vulnerability, data leak, authentication bypass
- Contains PoC or exploit details

VALID (regular bug):
- Technical bug with reproduction steps and error evidence

INVALID (reject):
- Feature requests, questions, emotional complaints, non-English, no technical facts

Return CRITICAL / VALID / INVALID and reason.
```

---

## Промпты для PR

### По умолчанию (отклонять все)

```
Do not accept pull requests. Close automatically.
```

### Принимать исправления багов

```
Accept only bug fix pull requests.

Valid: Reference to open issue, targeted fix, minimal scope.
Invalid: Feature additions, refactoring, docs only, unrelated changes.

Return verdict and reason.
```

---

## Промпты для Discussion

### По умолчанию (закрывать)

```
Discussions are closed. No action required.
```

### Мониторинг баг-репортов

```
Check if this Discussion contains an unreported bug.

If a reproducible bug with error details is described,
flag as "potential_bug" for issue creation.
Otherwise mark as "no_action".

Return potential_bug / no_action and reason.
```
