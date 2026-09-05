"""What the corpus accepts. Wrong answers here are wasted quota or missing evidence."""

from __future__ import annotations

import pytest

from ask_repos.ingest.filters import classify, looks_binary, select_paths


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "readme.rst",
        "docs/architecture.md",
        "docs/adr/0001-hybrid-retrieval.md",
        "CHANGELOG.md",
        "pyproject.toml",
        "Dockerfile",
        "deploy/Dockerfile.api",
        ".github/workflows/ci.yml",
        "src/ask_repos/cli.py",
        "web/app/page.tsx",
        "cmd/main.go",
        "scripts/build.ps1",
        "project.godot",
    ],
)
def test_accepted(path: str) -> None:
    assert classify(path) is not None, path


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/left-pad/index.js",
        "vendor/github.com/pkg/errors/errors.go",
        "dist/bundle.js",
        "build/output/app.py",
        ".venv/lib/site.py",
        "package-lock.json",
        "uv.lock",
        "poetry.lock",
        "static/app.min.js",
        "static/app.min.css",
        "dist/app.js.map",
        "assets/logo.png",
        "docs/proof/screenshots/home.png",
        "notes/scratch.md",
        "Library/ScriptAssemblies/Assembly-CSharp.dll",
    ],
)
def test_rejected(path: str) -> None:
    assert classify(path) is None, path


def test_kinds_are_assigned() -> None:
    assert classify("README.md").kind == "markdown"
    assert classify("src/main.py").kind == "code"
    assert classify("src/main.py").language == "python"
    assert classify("pyproject.toml").kind == "config"
    assert classify(".github/workflows/ci.yml").kind == "config"


def test_select_paths_filters_a_mixed_tree() -> None:
    tree = [
        "README.md",
        "src/app.py",
        "node_modules/x/index.js",
        "yarn.lock",
        "docs/guide.md",
    ]
    assert [selection.path for selection in select_paths(tree)] == [
        "README.md",
        "src/app.py",
        "docs/guide.md",
    ]


def test_binary_detection() -> None:
    assert looks_binary(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert looks_binary(b"\xff\xfe\xfd\xfc")
    assert not looks_binary(b"# hello\nprint('ok')\n")
    assert not looks_binary("مرحبا".encode())
