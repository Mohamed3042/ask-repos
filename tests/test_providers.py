"""Answer drafters: the extractive floor, and the Gemini adapter's contract."""

from __future__ import annotations

import httpx
import pytest
import respx

from ask_repos.agent.cite_check import word_matches
from ask_repos.agent.providers import ExtractiveProvider, GeminiProvider, get_provider
from ask_repos.config import reset_settings_cache
from ask_repos.retrieval.search import Hit

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.5-flash:generateContent"
)


def hit(text: str, chunk_id: int = 1, path: str = "README.md", repo: str = "octo/demo") -> Hit:
    return Hit(
        chunk_id=chunk_id,
        repo=repo,
        path=path,
        sha="abc1234",
        line_start=1,
        line_end=4,
        kind="markdown",
        symbol=None,
        text=text,
        score=1.0,
    )


def test_word_matches_tolerates_inflections_but_not_coincidence() -> None:
    assert word_matches("chunk", "chunks")
    assert word_matches("index", "indexed")
    assert word_matches("repo", "repo")
    assert not word_matches("author", "authoritative")
    assert not word_matches("author", "authorization")
    assert not word_matches("size", "sizeable-layout-container")


def test_the_extractive_provider_quotes_a_relevant_chunk() -> None:
    provider = ExtractiveProvider()
    draft = provider.draft(
        "Which Kuwait branches does the retail hub cover?",
        [hit("The retail hub covers four Kuwait branches: Salmiya, Al Rai, Jabriya, Fintas.")],
    )
    assert len(draft.sentences) == 1
    assert draft.sentences[0]["citations"] == [1]
    assert "Kuwait branches" in draft.sentences[0]["text"]


def test_the_extractive_provider_says_nothing_when_nothing_is_relevant() -> None:
    provider = ExtractiveProvider()
    draft = provider.draft(
        "Which allergies does the author have?",
        [hit(".page-shell { margin: 0 auto; max-width: 1180px; padding-left: 24px; }")],
    )
    assert draft.sentences == [], "a stylesheet is not an answer about allergies"


def test_a_stylesheet_is_not_an_answer_about_shoes() -> None:
    """The regression that motivated whole-word matching.

    `size` used to match `font-size` as a substring, and `author` matched `authored`, so
    this question scored 0.67 against a stylesheet and was answered.
    """
    passage = hit("h1 { font-size: 32px; letter-spacing: -0.02em; }")
    question = "What is the author's shoe size?"
    loose = ExtractiveProvider(min_relevance=0.0)
    assert loose.draft(question, [passage]).sentences, "control: the floor is what rejects it"
    assert ExtractiveProvider().draft(question, [passage]).sentences == []


def test_a_short_question_is_not_punished_for_being_short() -> None:
    provider = ExtractiveProvider()
    draft = provider.draft(
        "What is flagship-disney-media?",
        [
            hit(
                "Runtime media for the Disney Edition II scroll cinema.",
                repo="octo/flagship-disney-media",
            )
        ],
    )
    assert draft.sentences, "the repository name is part of the evidence"


@respx.mock
def test_gemini_returns_structured_sentences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    reset_settings_cache()
    respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"answer_sentences": [{"text": "It covers four '
                                    'branches.", "citations": [7]}]}'
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"totalTokenCount": 42},
            },
        )
    )
    draft = GeminiProvider().draft("How many branches?", [hit("four branches", chunk_id=7)])
    assert draft.provider == "gemini"
    assert draft.sentences == [{"text": "It covers four branches.", "citations": [7]}]
    assert draft.usage["totalTokenCount"] == 42
    assert draft.fallback_reason is None


@respx.mock
def test_gemini_failure_falls_back_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    reset_settings_cache()
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(503, text="upstream unavailable"))
    draft = GeminiProvider().draft(
        "Which Kuwait branches does the retail hub cover?",
        [hit("The retail hub covers four Kuwait branches.", chunk_id=7)],
    )
    assert draft.provider == "extractive"
    assert draft.fallback_reason and "503" in draft.fallback_reason
    assert draft.sentences


def test_provider_selection_follows_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    reset_settings_cache()
    assert get_provider("auto").name == "extractive"
    assert get_provider("extractive").name == "extractive"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    reset_settings_cache()
    assert get_provider("auto").name == "gemini"
    assert get_provider("extractive").name == "extractive", "an explicit choice always wins"
