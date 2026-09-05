"""Language-aware chunking with exact line spans.

The whole product rests on one invariant, asserted in `tests/test_chunkers.py`:

    chunk.text == "\n".join(file_text.splitlines()[chunk.line_start - 1 : chunk.line_end])

If that ever stops holding, every citation this service prints becomes a lie, so the
chunkers only ever slice whole lines and never reflow, strip or normalise them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 2_000
MAX_LINES = 90
OVERLAP_LINES = 10

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# Top-level definition starters, by language family. Anchored at column 0 on purpose:
# a code chunk should begin where a reader would say "this is where the function starts".
_DEF_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"^(?:@|async\s+def\s|def\s|class\s|if\s+__name__)"),
    "js": re.compile(
        r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(?:function\b|class\b|const\s+\w+\s*=\s*(?:async\s*)?(?:\(|function\b)|"
        r"interface\b|type\s+\w+\s*=|enum\b)"
    ),
    "clike": re.compile(
        r"^(?:@\w|(?:public|private|protected|internal|static|final|abstract|sealed|partial|"
        r"override|virtual|async|export|pub)\s+|func\s|fn\s|class\s|struct\s|enum\s|interface\s|"
        r"impl\s|namespace\s|package\s|type\s|def\s|sub\s|function\s)"
    ),
    "shell": re.compile(r"^(?:\w[\w\-]*\s*\(\)\s*\{|function\s+\w+)"),
    "sql": re.compile(r"^(?i:create|alter|insert|drop|with|select)\b"),
}

_LANG_FAMILY = {
    "python": "python",
    "javascript": "js",
    "typescript": "js",
    "svelte": "js",
    "vue": "js",
    "astro": "js",
    "go": "clike",
    "rust": "clike",
    "java": "clike",
    "kotlin": "clike",
    "csharp": "clike",
    "cpp": "clike",
    "c": "clike",
    "php": "clike",
    "ruby": "clike",
    "gdscript": "python",
    "shell": "shell",
    "powershell": "clike",
    "sql": "sql",
}


@dataclass(frozen=True)
class ChunkDraft:
    """One retrievable unit with the exact 1-based inclusive line span it came from."""

    kind: str
    symbol: str | None
    line_start: int
    line_end: int
    text: str


def _slice(lines: list[str], start: int, end: int) -> str:
    """1-based inclusive slice, joined with newlines and nothing else."""
    return "\n".join(lines[start - 1 : end])


def _window(
    lines: list[str], start: int, end: int, kind: str, symbol: str | None
) -> list[ChunkDraft]:
    """Split a too-large span into overlapping line windows."""
    out: list[ChunkDraft] = []
    cursor = start
    while cursor <= end:
        stop = cursor
        chars = 0
        while stop <= end and (stop - cursor) < MAX_LINES and chars < MAX_CHARS:
            chars += len(lines[stop - 1]) + 1
            stop += 1
        stop = min(stop - 1, end)
        if stop < cursor:
            stop = cursor
        out.append(ChunkDraft(kind, symbol, cursor, stop, _slice(lines, cursor, stop)))
        if stop >= end:
            break
        cursor = max(stop - OVERLAP_LINES + 1, cursor + 1)
    return out


def _emit(
    lines: list[str], start: int, end: int, kind: str, symbol: str | None
) -> list[ChunkDraft]:
    if start > end:
        return []
    if not _slice(lines, start, end).strip():
        return []
    span_chars = sum(len(line) + 1 for line in lines[start - 1 : end])
    if span_chars <= MAX_CHARS and (end - start + 1) <= MAX_LINES:
        return [ChunkDraft(kind, symbol, start, end, _slice(lines, start, end))]
    return _window(lines, start, end, kind, symbol)


def chunk_markdown(text: str) -> list[ChunkDraft]:
    """Split at ATX headings; the symbol is the breadcrumb of enclosing headings."""
    lines = text.splitlines()
    if not lines:
        return []
    boundaries: list[tuple[int, int, str]] = []  # (line_no, level, title)
    in_fence = False
    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            boundaries.append((idx, len(match.group(1)), match.group(2)))

    chunks: list[ChunkDraft] = []
    if not boundaries or boundaries[0][0] > 1:
        preamble_end = boundaries[0][0] - 1 if boundaries else len(lines)
        chunks += _emit(lines, 1, preamble_end, "markdown", None)

    trail: list[tuple[int, str]] = []
    for position, (line_no, level, title) in enumerate(boundaries):
        while trail and trail[-1][0] >= level:
            trail.pop()
        trail.append((level, title))
        symbol = " > ".join(t for _, t in trail)
        end = boundaries[position + 1][0] - 1 if position + 1 < len(boundaries) else len(lines)
        chunks += _emit(lines, line_no, end, "markdown", symbol)
    return chunks


def _symbol_for(line: str) -> str:
    return line.strip()[:200]


def _join_symbols(definitions: list[str]) -> str | None:
    """A chunk holding several definitions is named after the first few of them."""
    if not definitions:
        return None
    shown = [definition[:90] for definition in definitions[:3]]
    label = " · ".join(shown)
    if len(definitions) > 3:
        label += f" · (+{len(definitions) - 3} more)"
    return label[:300]


def chunk_code(text: str, language: str) -> list[ChunkDraft]:
    """Split at top-level definitions; imports/preamble become their own chunk."""
    lines = text.splitlines()
    if not lines:
        return []
    family = _LANG_FAMILY.get(language)
    pattern = _DEF_PATTERNS.get(family or "")
    if pattern is None:
        return _emit(lines, 1, len(lines), "code", None)

    starts: list[int] = []
    in_fence_lang = language in {"python", "gdscript"}
    in_triple = False
    for idx, line in enumerate(lines, start=1):
        if in_fence_lang:
            # A crude but sufficient guard: never start a chunk inside a docstring.
            in_triple ^= (line.count('"""') + line.count("'''")) % 2 == 1
            if in_triple:
                continue
        if line[:1].strip() and pattern.match(line):
            starts.append(idx)

    if not starts:
        return _emit(lines, 1, len(lines), "code", None)

    chunks: list[ChunkDraft] = []
    if starts[0] > 1:
        chunks += _emit(lines, 1, starts[0] - 1, "code", "module preamble")

    # Group consecutive definitions until the group would exceed the size budget.
    group_start = starts[0]
    group_defs: list[str] = []
    for position, start in enumerate(starts):
        group_defs.append(_symbol_for(lines[start - 1]))
        end = starts[position + 1] - 1 if position + 1 < len(starts) else len(lines)
        group_chars = sum(len(line) + 1 for line in lines[group_start - 1 : end])
        is_last = position + 1 == len(starts)
        if group_chars > MAX_CHARS or (end - group_start + 1) > MAX_LINES or is_last:
            chunks += _emit(lines, group_start, end, "code", _join_symbols(group_defs))
            if not is_last:
                group_start = starts[position + 1]
                group_defs = []
    return chunks


def chunk_config(text: str) -> list[ChunkDraft]:
    lines = text.splitlines()
    if not lines:
        return []
    return _emit(lines, 1, len(lines), "config", None)


def chunk_file(text: str, language: str, kind: str) -> list[ChunkDraft]:
    """Dispatch on the classification `select_paths` gave the file."""
    if kind == "markdown":
        return chunk_markdown(text)
    if kind == "config":
        return chunk_config(text)
    return chunk_code(text, language)
