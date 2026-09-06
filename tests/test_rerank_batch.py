"""The reranker scores in small batches, and the batch size is a setting.

Memory, not quality: a (query, passage) pair scores the same whichever batch it lands in, but
the size of a batch decides the activation memory of one forward pass. The hosted demo was
killed at 512 MB by the library default of 64 (2026-09-06), so the default is now 8 and the
value reaches the model call.
"""

from __future__ import annotations

from ask_repos.config import get_settings
from ask_repos.retrieval.embed import Reranker


class _FakeCrossEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def rerank(self, query: str, documents: list[str], batch_size: int = 64):
        self.calls.append((len(documents), batch_size))
        return [0.25 for _ in documents]


def test_default_batch_size_is_small(monkeypatch):
    monkeypatch.delenv("ASK_REPOS_RERANK_BATCH", raising=False)
    get_settings.cache_clear()
    try:
        reranker = Reranker(model_name="fake", cache_dir=None)
        fake = _FakeCrossEncoder()
        reranker._model = fake
        assert reranker.score("q", ["p"] * 20) == [0.25] * 20
        assert fake.calls == [(20, 8)]
    finally:
        get_settings.cache_clear()


def test_batch_size_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ASK_REPOS_RERANK_BATCH", "3")
    get_settings.cache_clear()
    try:
        reranker = Reranker(model_name="fake", cache_dir=None)
        fake = _FakeCrossEncoder()
        reranker._model = fake
        reranker.score("q", ["p"] * 7)
        assert fake.calls == [(7, 3)]
        # An explicit argument wins over the environment.
        assert Reranker(model_name="fake", batch_size=2).batch_size == 2
    finally:
        get_settings.cache_clear()


def test_a_nonsense_batch_size_is_clamped_to_one(monkeypatch):
    monkeypatch.setenv("ASK_REPOS_RERANK_BATCH", "0")
    get_settings.cache_clear()
    try:
        assert Reranker(model_name="fake", cache_dir=None).batch_size == 1
    finally:
        get_settings.cache_clear()


def test_empty_shortlist_never_touches_the_model():
    reranker = Reranker(model_name="fake", cache_dir=None)
    assert reranker.score("q", []) == []
    assert reranker._model is None
