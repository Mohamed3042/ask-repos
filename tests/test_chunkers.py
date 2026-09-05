"""The chunkers' one job: slices that a citation can be checked against."""

from __future__ import annotations

import pytest

from ask_repos.ingest.chunkers import (
    MAX_CHARS,
    chunk_code,
    chunk_config,
    chunk_file,
    chunk_markdown,
)

MARKDOWN = """\
Intro paragraph before any heading.

# Title

Some prose about the project.

## Install

```bash
pip install ask-repos
# ## not a heading, it is inside a fence
```

### Notes

Deeply nested note.

## Usage

Run it.
"""

PYTHON = '''\
"""Module docstring.

def not_a_real_def(inside_the_docstring):
"""

import os
import sys

CONSTANT = 3


def alpha(value):
    return value + CONSTANT


class Beta:
    def method(self):
        return os.getcwd()


async def gamma():
    return sys.version
'''

GO = """\
package main

import "fmt"

func Alpha() string {
\treturn "a"
}

func Beta() string {
\treturn "b"
}
"""


def assert_spans_exact(text: str, chunks: list) -> None:
    """chunk.text must be exactly the lines it claims. This is the product's foundation."""
    lines = text.splitlines()
    for chunk in chunks:
        assert 1 <= chunk.line_start <= chunk.line_end <= len(lines), chunk
        expected = "\n".join(lines[chunk.line_start - 1 : chunk.line_end])
        assert chunk.text == expected, f"span drift at {chunk.line_start}-{chunk.line_end}"


@pytest.mark.parametrize(
    ("text", "language", "kind"),
    [
        (MARKDOWN, "markdown", "markdown"),
        (PYTHON, "python", "code"),
        (GO, "go", "code"),
        (PYTHON, "config", "config"),
        ("single line, no newline", "markdown", "markdown"),
        ("a\n" * 400, "python", "code"),
        ("x" * (MAX_CHARS * 3), "markdown", "markdown"),
    ],
)
def test_line_spans_are_exact(text: str, language: str, kind: str) -> None:
    assert_spans_exact(text, chunk_file(text, language, kind))


def test_markdown_headings_become_breadcrumbs() -> None:
    chunks = chunk_markdown(MARKDOWN)
    symbols = [chunk.symbol for chunk in chunks]
    assert None in symbols, "the preamble before the first heading is kept"
    assert "Title > Install" in symbols
    assert "Title > Install > Notes" in symbols
    assert "Title > Usage" in symbols


def test_markdown_ignores_headings_inside_code_fences() -> None:
    symbols = [chunk.symbol for chunk in chunk_markdown(MARKDOWN)]
    assert not any(symbol and "not a heading" in symbol for symbol in symbols)


def test_python_docstring_does_not_start_a_chunk() -> None:
    chunks = chunk_code(PYTHON, "python")
    assert not any(
        chunk.symbol and "not_a_real_def" in chunk.symbol for chunk in chunks
    ), "a def inside a docstring is not a definition"
    assert any(chunk.symbol and "def alpha(value):" in chunk.symbol for chunk in chunks)


def test_code_preamble_is_its_own_chunk() -> None:
    chunks = chunk_code(PYTHON, "python")
    assert chunks[0].symbol == "module preamble"
    assert chunks[0].line_start == 1


def test_go_definitions_are_found() -> None:
    chunks = chunk_code(GO, "go")
    assert any(chunk.symbol and "func Alpha" in chunk.symbol for chunk in chunks)


def test_windows_line_endings_do_not_shift_spans() -> None:
    text = MARKDOWN.replace("\n", "\r\n")
    chunks = chunk_markdown(text)
    assert_spans_exact(text, chunks)


def test_long_span_is_windowed_with_overlap() -> None:
    text = "\n".join(f"line {number}" for number in range(1, 501))
    chunks = chunk_config(text)
    assert len(chunks) > 1
    assert_spans_exact(text, chunks)
    starts = [chunk.line_start for chunk in chunks]
    ends = [chunk.line_end for chunk in chunks]
    assert starts[1] <= ends[0], "consecutive windows must overlap, not leave a gap"
    assert ends[-1] == 500, "the last line must be covered"


def test_empty_text_yields_nothing() -> None:
    assert chunk_file("", "python", "code") == []
    assert chunk_file("   \n\n  \n", "markdown", "markdown") == []
