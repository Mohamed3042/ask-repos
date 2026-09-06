"""Settings parsing. One of these is a start-up crash that reached a container."""

from __future__ import annotations

import pytest

from ask_repos.config import get_settings, reset_settings_cache


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ("https://a.example", ["https://a.example"]),
        ("https://a.example, https://b.example", ["https://a.example", "https://b.example"]),
        ("  ", []),
    ],
)
def test_cors_origins_accept_a_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]
) -> None:
    """Compose passes an empty string for an unset variable; that used to crash start-up."""
    monkeypatch.setenv("ASK_REPOS_CORS_ORIGINS", value)
    reset_settings_cache()
    assert get_settings().cors_origins == expected


def test_defaults_are_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GEMINI_API_KEY", "ASK_REPOS_API_KEY", "ASK_REPOS_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    reset_settings_cache()
    settings = get_settings()
    assert settings.has_gemini is False
    assert settings.api_key is None
    assert settings.embed_dim == 384
    assert settings.embed_model == "BAAI/bge-small-en-v1.5"
