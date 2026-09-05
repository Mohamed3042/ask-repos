"""What goes into the corpus, and what it is called once it is there.

Everything here is a pure function over a path string so the rules are testable
without a network or a database.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

VENDORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "vendor",
        "third_party",
        "thirdparty",
        "dist",
        "build",
        "out",
        "target",
        "__pycache__",
        "site-packages",
        "Pods",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "coverage",
        "htmlcov",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "Library",  # Unity
        "Temp",
        "Binaries",  # Unreal
        "Intermediate",
        "DerivedDataCache",
        ".godot",
    }
)

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "Pipfile.lock",
        "go.sum",
    }
)

TOP_LEVEL_CONFIG = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yaml",
        "compose.yml",
        "Makefile",
        "justfile",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "netlify.toml",
        "vercel.json",
        "astro.config.mjs",
        "next.config.js",
        "next.config.mjs",
        "project.godot",
        "alembic.ini",
        ".env.example",
    }
)

DOC_EXTS = frozenset({".md", ".mdx", ".rst"})
CONFIG_EXTS = frozenset({".toml", ".ini", ".cfg"})

EXT_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".svelte": "svelte",
    ".vue": "vue",
    ".astro": "astro",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".h": "c",
    ".c": "c",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".gd": "gdscript",
    ".css": "css",
    ".scss": "css",
    ".html": "html",
}

MINIFIED_SUFFIXES = (".min.js", ".min.css", ".map", ".bundle.js", ".lock")


@dataclass(frozen=True)
class Selection:
    """Why a path was accepted, and how it should be chunked."""

    path: str
    kind: str  # markdown | code | config
    language: str


def _in_vendored_dir(path: str) -> bool:
    parts = path.split("/")[:-1]
    return any(part in VENDORED_DIRS for part in parts)


def classify(path: str) -> Selection | None:
    """Return how to treat `path`, or None when it does not belong in the corpus."""
    # `lstrip("./")` would eat the leading dot of `.github/...`; strip only whole prefixes.
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")
    if not path or _in_vendored_dir(path):
        return None
    name = posixpath.basename(path)
    if name in LOCKFILES or name.lower().endswith(MINIFIED_SUFFIXES):
        return None
    ext = posixpath.splitext(name)[1].lower()
    depth = path.count("/")

    if name.upper().startswith("README") and ext in DOC_EXTS | {""}:
        return Selection(path, "markdown", "markdown")
    if ext in DOC_EXTS and (path.startswith("docs/") or depth == 0):
        return Selection(path, "markdown", "markdown")
    if depth == 0 and name in TOP_LEVEL_CONFIG:
        return Selection(path, "config", "config")
    if path.startswith(".github/workflows/") and ext in {".yml", ".yaml"}:
        return Selection(path, "config", "yaml")
    if name in {"Dockerfile"} or name.startswith("Dockerfile."):
        return Selection(path, "config", "dockerfile")
    if ext in EXT_LANGUAGE:
        return Selection(path, "code", EXT_LANGUAGE[ext])
    if depth == 0 and ext in CONFIG_EXTS:
        return Selection(path, "config", "config")
    return None


def select_paths(paths: list[str]) -> list[Selection]:
    return [selection for path in paths if (selection := classify(path)) is not None]


def looks_binary(blob: bytes) -> bool:
    head = blob[:8000]
    if b"\x00" in head:
        return True
    try:
        blob.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False
