"""Things that only break outside the machine they were written on."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LF_ONLY = ["deploy/entrypoint.sh", "scripts/verify.sh"]


@pytest.mark.parametrize("relative", LF_ONLY)
def test_shell_scripts_have_unix_line_endings(relative: str) -> None:
    """A CRLF shebang makes the kernel look for `/bin/sh\r`.

    Measured on this repository on 2026-09-06: with `core.autocrlf=true`, the working tree
    copy of `deploy/entrypoint.sh` had 16 CRLF pairs and the container it built exited 255
    with `exec /usr/local/bin/entrypoint.sh: no such file or directory`. Linux CI never
    reproduces it, so the check lives here and `.gitattributes` pins the endings.
    """
    data = (REPO_ROOT / relative).read_bytes()
    assert b"\r\n" not in data, f"{relative} has CRLF line endings; see .gitattributes"
    assert data.startswith(b"#!/bin/sh\n") or data.startswith(b"#!/usr/bin/env bash\n"), (
        f"{relative} does not start with a clean LF shebang"
    )


def test_gitattributes_pins_shell_scripts_to_lf() -> None:
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes
