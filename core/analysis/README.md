# core/analysis

`builtin-analysis` extension への互換ブリッジ。

- ここは実装本体ではなく、主に旧 import path 互換の橋渡しを担当する。
- `extensions.builtin_analysis.*` を直接 import できるため、新規の repo 内コードは具体モジュールを優先する。
- 内部コードは、安定した具体モジュールへ直接 import できる場合はそちらを優先する。
- 逆に `ollama_utils` / `openai_compat_utils` のような bridge 性の高いものは、この package を経由する設計を許容する。

依存の目安:

- 外部互換 / bridge: `core.analysis.*`
- 実装本体: `extensions/builtin_analysis/core_impl/*`
