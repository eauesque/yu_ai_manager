#!/usr/bin/env python3
"""Verify translated documents against their Japanese original.

Written after a translation round that passed every structural check and still
shipped four broken documents: a shell command turned into prose, two runnable
code blocks replaced by a sentence, four inline comments dropped, and an ASCII
diagram that lost a cell. Structure — heading counts, table rows, fence counts —
was identical to ja in all of them.

So this checker looks at content, and `--inject` makes it prove that it does:
it breaks a real target the way translations actually break and requires a catch
for each. A checker that reports green is worth nothing until you have watched it
report red for the failure you care about.

Usage:
    check_translation_parity.py docs/ja/hailo/FOO.md
    check_translation_parity.py docs/ja/hailo/FOO.md --langs en,fr,ko
    check_translation_parity.py docs/ja/hailo/FOO.md --inject

Exit: 0 all parity, 1 mismatches found, 2 an injected defect went undetected.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

DEFAULT_LANGS = ["en", "de", "es", "fr", "it", "ko", "pt", "ru", "zh-cn", "zh-tw"]

# Unit spellings a translation may legitimately localise. French writes "Mo",
# Russian "МБ"; comparing the raw string reports losses that never happened.
UNIT_CLASS = {
    "mb": "M", "mo": "M", "мб": "M",
    "gb": "G", "go": "G", "гб": "G",
    "kb": "K", "ko": "K", "кб": "K",
}
# No \b: Korean attaches particles straight onto the unit ("512 MB이며"), and a
# word boundary never fires between "B" and a Hangul syllable. The separator also
# allows a hyphen, because German compounds the unit into the noun ("8-MB-Puffer").
MEM_RE = re.compile(
    r"(\d[\d.,   ]*?)[\s-]?(MB|Mo|МБ|GB|Go|ГБ|kB|ko|КБ)(?![A-Za-z0-9])"
)

# Tokens a translation must carry through untouched: they are typed, pasted, or
# compared by the reader.
LITERAL_PATTERNS = [
    r"[0-9a-f]{16,}",                     # hashes, srcversion
    r"\d+\.\d+\.\d+",                     # versions
    r"0x[0-9a-fA-F]+",                    # hex sizes
    r"\d{4}-\d{2}-\d{2}",                 # dates
    r"\]\((?:\.{1,2}/)[^)]+\)",           # relative links
]
# Backticked spans that look like a command, path, or config key rather than prose.
CODEISH = re.compile(r"`([^`\n]{3,})`")
CODEISH_HINT = re.compile(r"[=/]|\.(?:md|py|json|yaml|toml|txt|conf|sh)\b|_")
# Every code span, however short. Used to blank out verbatim quotes before looking
# for untranslated text. The {3,} form above must NOT be used for that: it skips
# `xz`, so its closing backtick pairs with the next span's opening one and the
# pairing is off by one for the rest of the line — which reported a correctly
# backticked Japanese error message as untranslated prose.
CODE_SPAN = re.compile(r"`[^`\n]+`")

# Kana leaking into a target is untranslated source text. Han characters are not
# usable for this (zh targets are full of them); kana is unique to Japanese.
# The ranges deliberately stop short of U+30FB "・" and U+30FC "ー": Chinese
# targets use the middle dot as an ordinary separator, so including it reports
# every zh-tw table header as untranslated Japanese.
KANA = re.compile(r"[ぁ-ゖァ-ヺ]")
# Japanese running text: kana, or kana-adjacent Han. Used to tell prose apart from
# commands inside a fenced block. Han alone would also match Chinese, but here it
# is only ever applied to the *ja* side, where Han means Japanese.
JP_TEXT = re.compile(r"[ぁ-ゖァ-ヺ一-鿿]")


def split_fences(text: str):
    """Return (prose_lines, blocks) where blocks is a list of fenced-body line lists."""
    prose, blocks, cur, in_fence = [], [], None, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if in_fence:
                blocks.append(cur)
                cur = None
            else:
                cur = []
            in_fence = not in_fence
            continue
        (cur if in_fence else prose).append(line)
    if in_fence:  # unterminated fence
        blocks.append(cur or [])
    return prose, blocks


def profile(text: str):
    """Structural fingerprint, computed outside code fences.

    Counting headings without tracking fence state mistakes `# comment` lines in
    shell snippets for headings — which silently inflates the count on both sides
    and hides a genuinely dropped section.
    """
    prose, blocks = split_fences(text)
    heads = []
    rows = 0
    for line in prose:
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            # A leading number counts as a section number only in the forms "7." or
            # "7.1" — not a bare "2 ", which in Japanese is usually a counter
            # ("## 2 つのモード比較" = "Comparison of the Two Modes"). Treating that
            # as a section number reports every translation of the heading as a
            # numbering mismatch.
            num = re.match(r"^(\d+(?:\.\d+)+|\d+\.)\s", m.group(2))
            if num:
                key = num.group(1).rstrip(".")
            else:
                # Appendix letters: the word before the letter is localised, the
                # letter is not.
                ap = re.match(r"^\S+\s+([A-Z])\.", m.group(2))
                key = f"app-{ap.group(1)}" if ap else "-"
            heads.append((len(m.group(1)), key))
        elif line.startswith("|"):
            rows += 1
    return heads, len(blocks), rows


def command_part(line: str) -> str:
    """The part of a fenced line that must not change: everything before ` #`."""
    idx = line.find(" #")
    return line if idx < 0 else line[:idx].rstrip()


def literals(text: str) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for pat in LITERAL_PATTERNS:
        for m in re.findall(pat, text):
            c[m] += 1
    for m in CODEISH.findall(text):
        if m.isascii() and CODEISH_HINT.search(m):
            c[f"`{m}`"] += 1
    return c


def mem_values(text: str) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for num, unit in MEM_RE.findall(text):
        digits = re.sub(r"\D", "", num)
        if digits:
            c[(digits, UNIT_CLASS[unit.lower()])] += 1
    return c


def compare(ja: str, tr: str, lang: str) -> list[str]:
    flags: list[str] = []

    ja_heads, ja_fences, ja_rows = profile(ja)
    tr_heads, tr_fences, tr_rows = profile(tr)
    if len(tr_heads) != len(ja_heads):
        flags.append(f"headings {len(tr_heads)} != {len(ja_heads)}")
    elif tr_heads != ja_heads:
        bad = [i for i, (a, b) in enumerate(zip(tr_heads, ja_heads, strict=True)) if a != b]
        flags.append(f"heading level/number differs at index {bad[:5]}")
    if tr_fences != ja_fences:
        flags.append(f"code blocks {tr_fences} != {ja_fences}")
    if tr_rows != ja_rows:
        flags.append(f"table rows {tr_rows} != {ja_rows}")

    _, ja_blocks = split_fences(ja)
    _, tr_blocks = split_fences(tr)
    if len(ja_blocks) == len(tr_blocks):
        for i, (a, b) in enumerate(zip(ja_blocks, tr_blocks, strict=True)):
            if len(a) != len(b):
                flags.append(f"code block {i}: {len(b)} lines != {len(a)} (dropped or added a line)")
                continue
            for j, (la, lb) in enumerate(zip(a, b, strict=True)):
                if la.strip().startswith("#"):
                    continue  # whole-line comment: translating it is expected
                # Some fenced blocks are pseudo-terminals whose lines are Japanese
                # prose, not commands. Judge by the ja line: if the command half
                # carries Japanese text it is prose and may be translated. Box
                # drawing and other non-ASCII symbols are not Japanese text, so a
                # corrupted ASCII-art diagram is still compared strictly.
                if JP_TEXT.search(command_part(la)):
                    continue
                if command_part(la) != command_part(lb):
                    flags.append(
                        f"code block {i} line {j}: content changed\n"
                        f"        ja: {command_part(la)!r}\n"
                        f"        {lang}: {command_part(lb)!r}"
                    )
                elif (" #" in la) != (" #" in lb):
                    # The command survived but its trailing note did not. Comparing
                    # only command_part hides this, because command_part is exactly
                    # the half that strips the note off both sides.
                    flags.append(
                        f"code block {i} line {j}: inline comment dropped\n"
                        f"        ja: {la.strip()!r}"
                    )

    ja_lit, tr_lit = literals(ja), literals(tr)
    lost = {t: (n, tr_lit[t]) for t, n in ja_lit.items() if tr_lit[t] < n}
    if lost:
        shown = sorted(lost.items())[:6]
        flags.append(f"literals lost ({len(lost)}): {shown}")

    ja_mem, tr_mem = mem_values(ja), mem_values(tr)
    lost_mem = {k: (n, tr_mem.get(k, 0)) for k, n in ja_mem.items() if tr_mem.get(k, 0) < n}
    if lost_mem:
        flags.append(f"measured values lost: {sorted(lost_mem.items())[:5]}")

    prose, _ = split_fences(tr)
    if lang not in ("ja",):
        # Backticked spans are verbatim by policy: quoted command output can be
        # Japanese (an apt error under a ja locale) and must survive untranslated.
        # Only kana in running prose means the translator skipped a line.
        stripped = [(l, CODE_SPAN.sub("", l)) for l in prose]
        kana = [l.strip()[:70] for l, s in stripped if KANA.search(s)]
        if kana:
            flags.append(f"untranslated Japanese in {len(kana)} line(s): {kana[:2]}")

    if "glossary-candidate" in tr:
        flags.append("translator scaffolding left in a public document")

    return flags


# Injections mirror failures actually observed in translation rounds. Each must be
# caught; a MISSED line means this checker has a hole, not that the file is fine.
INJECTIONS = [
    ("drop a table row",
     lambda t: re.sub(r"\n\|[^\n]*\|", "", t, count=1)),
    ("paraphrase a command into prose",
     lambda t: _mutate_first_command(t, lambda _line: "run the command described above")),
    ("drop an inline comment from a command",
     lambda t: _mutate_first_command(t, command_part, need_comment=True)),
    ("drop a heading",
     lambda t: re.sub(r"\n(#{2,3}) ", "\n<!-- ", t, count=1)),
    ("break a relative link",
     lambda t: re.sub(r"\]\((\.{1,2}/[^)]+)\)", "](../gone.md)", t, count=1)),
    ("leave untranslated Japanese in prose",
     lambda t: t.replace("\n\n", "\n\nこの行は未翻訳である。\n\n", 1)),
]


def _mutate_first_command(text: str, fn, need_comment: bool = False) -> str:
    out, in_fence, done = [], False, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if (in_fence and not done and line.strip()
                and not line.strip().startswith("#")
                and (not need_comment or " #" in line)):
            out.append(fn(line))
            done = True
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def run_injections(ja_path: pathlib.Path, targets: dict[str, pathlib.Path]) -> int:
    lang, path = next(iter(targets.items()))
    ja = ja_path.read_text(encoding="utf-8")
    orig = path.read_text(encoding="utf-8")
    print(f"\n--- injection self-test on {path} ---")
    missed = []
    try:
        for name, mutate in INJECTIONS:
            broken = mutate(orig)
            if broken == orig:
                print(f"SKIP    {name} (pattern not present in this document)")
                continue
            flags = compare(ja, broken, lang)
            caught = bool(flags)
            print(f"{'CAUGHT ' if caught else 'MISSED '} {name}")
            if caught:
                print(f"        -> {flags[0].splitlines()[0][:110]}")
            else:
                missed.append(name)
    finally:
        path.write_text(orig, encoding="utf-8")
    ok = path.read_text(encoding="utf-8") == orig
    print(f"target restored: {ok}")
    if missed:
        print(f"\n{len(missed)} injected defect(s) went undetected: {missed}")
        print("Do not trust a green run until these are covered.")
        return 2
    print("\nall injected defects detected")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="path to the ja original, e.g. docs/ja/hailo/FOO.md")
    ap.add_argument("--langs", default=",".join(DEFAULT_LANGS),
                    help="comma-separated target languages")
    ap.add_argument("--inject", action="store_true",
                    help="break a target on purpose and require this checker to notice")
    args = ap.parse_args()

    ja_path = pathlib.Path(args.source)
    if not ja_path.exists():
        print(f"source not found: {ja_path}", file=sys.stderr)
        return 1
    parts = ja_path.parts
    if "ja" not in parts:
        print(f"source must live under a docs/ja/ tree: {ja_path}", file=sys.stderr)
        return 1
    ja_i = parts.index("ja")

    ja = ja_path.read_text(encoding="utf-8")
    heads, fences, rows = profile(ja)
    print(f"ja: headings={len(heads)} code-blocks={fences} table-rows={rows}  (reference)")
    print(f"    {len(literals(ja))} literals, {len(mem_values(ja))} measured values\n")

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    targets = {
        lang: pathlib.Path(*parts[:ja_i], lang, *parts[ja_i + 1:]) for lang in langs
    }

    if args.inject:
        present = {l: p for l, p in targets.items() if p.exists()}
        if not present:
            print("no target file to inject into", file=sys.stderr)
            return 1
        return run_injections(ja_path, present)

    bad = 0
    for lang, path in targets.items():
        if not path.exists():
            print(f"{lang:6} MISSING  {path}")
            bad += 1
            continue
        flags = compare(ja, path.read_text(encoding="utf-8"), lang)
        if flags:
            bad += 1
            print(f"{lang:6} {len(flags)} issue(s)")
            for f in flags[:6]:
                print(f"       - {f}")
        else:
            print(f"{lang:6} OK")

    print(f"\n{bad} language(s) need attention")
    if bad:
        print("Re-run with --inject to confirm this checker actually grips "
              "before trusting a later green run.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
