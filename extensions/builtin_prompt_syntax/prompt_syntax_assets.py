"""Asset bundling helpers for prompt-syntax extension."""

from collections.abc import Iterable
from pathlib import Path

_ENGINE_PARTS = [
    "prompt-syntax-engine-core-lex-main.js",
    "prompt-syntax-engine-core-lex-matchers-general.js",
    "prompt-syntax-engine-core-lex-matchers-square.js",
    "prompt-syntax-engine-core-lex-matchers-brace.js",
    "prompt-syntax-engine-core-lex-matchers-paren.js",
    "prompt-syntax-engine-core-lex-helpers.js",
    "prompt-syntax-engine-core-analyze.js",
    "prompt-syntax-engine-render-utils.js",
    "prompt-syntax-engine-render-token-renderers.js",
    "prompt-syntax-engine-render.js",
    "prompt-syntax-engine-entry.js",
]

_WIDGET_PARTS = [
    "prompt-syntax-widget-core.js",
    "prompt-syntax-widget-editor-ui.js",
    "prompt-syntax-widget-editor.js",
    "prompt-syntax-widget-display.js",
    "prompt-syntax-widget-token-tip.js",
    "prompt-syntax-widget-entry.js",
]

_STYLE_PARTS = [
    "prompt-syntax-style-base.css",
    "prompt-syntax-style-tokens.css",
    "prompt-syntax-style-nai.css",
    "prompt-syntax-style-sd.css",
    "prompt-syntax-style-dp.css",
    "prompt-syntax-style-ui.css",
]


def _bundle(ext_dir: Path, parts: Iterable[str]) -> str:
    return "\n".join((ext_dir / name).read_text(encoding="utf-8") for name in parts)


def build_engine_js(ext_dir: Path) -> str:
    return _bundle(ext_dir, _ENGINE_PARTS)


def build_widget_js(ext_dir: Path) -> str:
    return _bundle(ext_dir, _WIDGET_PARTS)


def build_style_css(ext_dir: Path) -> str:
    return _bundle(ext_dir, _STYLE_PARTS)
