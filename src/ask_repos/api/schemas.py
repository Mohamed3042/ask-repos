"""Request and response shapes. These are the OpenAPI document."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(
        min_length=1, max_length=2000, examples=["What did he build with FastAPI?"]
    )
    k: int = Field(default=8, ge=1, le=25)
    mode: Literal["hybrid", "vector", "text"] = "hybrid"
    repo: str | None = Field(default=None, examples=["Mohamed3042/ask-repos"])
    provider: Literal["auto", "gemini", "extractive"] = "auto"
    thread_id: str | None = Field(default=None, description="Reuse to resume an interrupted run")


class CitationOut(BaseModel):
    chunk_id: int
    repo: str
    path: str
    sha: str
    line_start: int
    line_end: int
    citation: str
    url: str


class SentenceOut(BaseModel):
    text: str
    kept: bool
    reason: str | None = None
    support: float = 0.0
    citations: list[CitationOut] = []


class AskResponse(BaseModel):
    """The result of one run.

    A run that stopped at the human-approval interrupt has produced no answer yet, so
    `answer` is empty and `refused` is false; `status` is the field that distinguishes
    "not answered yet" from "answered". Before these defaults existed, an interrupted
    `POST /v1/ask` failed response validation and the route returned 500 - the streaming
    route handled the case and the JSON route did not.
    """

    status: Literal["ok", "interrupted"] = "ok"
    thread_id: str
    question: str | None = None
    answer: str = Field(default="", description="Empty while status is 'interrupted'")
    refused: bool = Field(default=False, description="Meaningful only when status is 'ok'")
    sentences: list[SentenceOut] = []
    dropped: dict[str, int] = {}
    provider: str | None = None
    model: str | None = None
    fallback_reason: str | None = None
    steps: list[str] = []
    request: dict[str, Any] | None = Field(
        default=None, description="Present when status is interrupted: what a human must approve"
    )


class ResumeRequest(BaseModel):
    approved: bool
    reason: str | None = None


class SearchHitOut(BaseModel):
    chunk_id: int
    repo: str
    path: str
    sha: str
    line_start: int
    line_end: int
    kind: str
    symbol: str | None = None
    text: str
    score: float
    vector_rank: int | None = None
    text_rank: int | None = None
    rerank_score: float | None = None
    citation: str
    url: str


class SearchResponse(BaseModel):
    query: str
    mode: str
    count: int
    hits: list[SearchHitOut]


class IndexRequest(BaseModel):
    owner: str | None = None
    repo: str | None = None
    force: bool = False


class IndexResponse(BaseModel):
    started: bool
    detail: str


class FileSpanResponse(BaseModel):
    repo: str
    path: str
    sha: str
    language: str
    line_start: int
    line_end: int
    line_count: int
    text: str
    url: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    database: bool
    chunks: int
