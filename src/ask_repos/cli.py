"""`ask-repos` command line.

Every subcommand prints the numbers it measured, because the README's claims are
supposed to be reproducible by the reader running the same line.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from ask_repos import __version__
from ask_repos.config import get_settings

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Ask any GitHub account about its repositories — every answer cites file and line.",
)


def _echo(message: str) -> None:
    typer.echo(message)


@app.command()
def version() -> None:
    """Print the version and the pinned model ids."""
    settings = get_settings()
    _echo(f"ask-repos {__version__}")
    _echo(f"embeddings : {settings.embed_model} ({settings.embed_dim} dims, local ONNX)")
    _echo(f"reranker   : {settings.rerank_model} (local ONNX)")
    _echo(f"generation : {settings.gemini_model if settings.has_gemini else 'extractive (no key)'}")


@app.command()
def migrate() -> None:
    """Create or upgrade the database schema."""
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    _echo("schema at head")


@app.command()
def index(
    owner: Annotated[str, typer.Option("--owner", "-o", help="GitHub account to index")] = "",
    repo: Annotated[str, typer.Option("--repo", "-r", help="One repository name only")] = "",
    force: Annotated[bool, typer.Option("--force", help="Re-read every file")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Index an account's PUBLIC repositories into the corpus."""
    from ask_repos.db.session import session_scope
    from ask_repos.ingest.pipeline import index_owner

    settings = get_settings()
    target = owner or settings.default_owner
    progress = None if quiet else _echo
    _echo(f"indexing {target} (public repos only)…")
    with session_scope() as session:
        stats = index_owner(
            session, target, only_repo=repo or None, force=force, progress=progress
        )
    _echo(stats.summary())


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="What to look for")],
    k: Annotated[int, typer.Option("-k", help="How many chunks to return")] = 8,
    mode: Annotated[str, typer.Option("--mode", help="vector | text | hybrid")] = "hybrid",
    repo: Annotated[str, typer.Option("--repo", help="Restrict to one repository")] = "",
    rerank: Annotated[bool, typer.Option("--rerank/--no-rerank")] = True,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Retrieve chunks without generating an answer."""
    from ask_repos.db.session import session_scope
    from ask_repos.retrieval.search import search as run_search

    with session_scope() as session:
        hits = run_search(session, query, k=k, mode=mode, repo=repo or None, rerank=rerank)
    if as_json:
        _echo(json.dumps([hit.as_dict() for hit in hits], indent=2))
        return
    for position, hit in enumerate(hits, start=1):
        _echo(f"{position:2}. {hit.citation}  score={hit.score:.4f}")
        if hit.symbol:
            _echo(f"    {hit.symbol}")
        first = next((line for line in hit.text.splitlines() if line.strip()), "")
        _echo(f"    {first[:110]}")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="The question")],
    k: Annotated[int, typer.Option("-k")] = 8,
    provider: Annotated[
        str, typer.Option("--provider", help="auto | gemini | extractive")
    ] = "auto",
    repo: Annotated[str, typer.Option("--repo")] = "",
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Answer a question with citations, or refuse."""
    from ask_repos.agent.graph import ask as run_ask
    from ask_repos.db.session import session_scope

    with session_scope() as session:
        result = run_ask(
            session, question, k=k, repo=repo or None, provider_name=provider, thread_id="cli"
        )
    if as_json:
        _echo(json.dumps(result, indent=2, default=str))
        return
    if result.get("status") == "interrupted":
        _echo(f"⏸ approval needed: {json.dumps(result['request'])}")
        raise typer.Exit(code=2)
    _echo(result["answer"])
    _echo("")
    for sentence in result.get("sentences", []):
        if not sentence["kept"]:
            continue
        for citation in sentence["citations"]:
            _echo(f"  ↳ {citation['citation']}")
            _echo(f"    {citation['url']}")
    dropped = result.get("dropped") or {}
    if dropped:
        _echo(f"\ndropped by cite-check: {dropped}")
    _echo(f"provider: {result.get('provider')} {result.get('model') or ''}".rstrip())
    if result.get("fallback_reason"):
        _echo(f"fallback: {result['fallback_reason']}")


@app.command()
def corpus(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """What is indexed right now."""
    from ask_repos.db.session import session_scope
    from ask_repos.service import corpus_summary

    with session_scope() as session:
        summary = corpus_summary(session)
    if as_json:
        _echo(json.dumps(summary, indent=2, default=str))
        return
    _echo(
        f"{summary['repo_count']} repos · {summary['file_count']} files · "
        f"{summary['chunk_count']} chunks · {summary['bytes_indexed']} bytes"
    )
    for row in summary["repos"]:
        _echo(
            f"  {row['full_name']:<50} {row['files']:>4} files {row['chunks']:>5} chunks  "
            f"{(row['last_indexed_at'] or '-')}"
        )


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port")] = 8080,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Run the HTTP API (OpenAPI docs at /docs)."""
    import uvicorn

    uvicorn.run("ask_repos.api.app:app", host=host, port=port, reload=reload)


@app.command()
def mcp(
    stdio: Annotated[bool, typer.Option("--stdio", help="Serve MCP over stdio")] = False,
    http: Annotated[bool, typer.Option("--http", help="Serve MCP over streamable HTTP")] = False,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8081,
) -> None:
    """Expose the corpus to MCP clients (Claude Desktop, Claude Code, any client)."""
    from ask_repos.mcpsrv.server import run_http, run_stdio

    if http and stdio:
        raise typer.BadParameter("choose either --stdio or --http")
    if http:
        run_http(host=host, port=port)
    else:
        run_stdio()


evals_app = typer.Typer(help="Golden set, retrieval metrics, red team.", no_args_is_help=True)
app.add_typer(evals_app, name="evals")


@evals_app.command("run")
def evals_run(
    golden: Annotated[str, typer.Option("--golden")] = "evals/golden.yaml",
    report_dir: Annotated[str, typer.Option("--report-dir")] = "evals/reports",
    min_citation_validity: Annotated[float, typer.Option("--min-citation-validity")] = 1.0,
    min_recall5: Annotated[float, typer.Option("--min-recall5")] = 0.0,
    provider: Annotated[str, typer.Option("--provider")] = "extractive",
    judge: Annotated[bool, typer.Option("--judge/--no-judge")] = False,
) -> None:
    """Run the eval suite and gate on the floors."""
    from ask_repos.evals.runner import run_evals

    report = run_evals(
        golden_path=golden,
        report_dir=report_dir,
        provider_name=provider,
        judge=judge,
    )
    _echo(report.render_text())
    failures = report.gate(min_citation_validity, min_recall5)
    for line in failures:
        _echo(f"GATE FAIL: {line}")
    raise typer.Exit(code=1 if failures else 0)


@evals_app.command("snapshot")
def evals_snapshot(
    owner: Annotated[str, typer.Option("--owner", "-o")] = "",
    out: Annotated[str, typer.Option("--out")] = "evals/corpus",
) -> None:
    """Freeze the live corpus into a replayable fixture so CI runs offline."""
    from ask_repos.evals.snapshot import write_snapshot

    settings = get_settings()
    path = write_snapshot(owner or settings.default_owner, out)
    _echo(f"snapshot written: {path}")


@evals_app.command("load")
def evals_load(
    source: Annotated[str, typer.Option("--source")] = "evals/corpus",
    force: Annotated[bool, typer.Option("--force")] = True,
    only: Annotated[
        str, typer.Option("--only", help="Comma-separated repository names; empty = all")
    ] = "",
) -> None:
    """Index the recorded snapshot into the database (no network)."""
    from ask_repos.evals.snapshot import load_snapshot

    names = [name for name in only.split(",") if name.strip()] or None
    stats = load_snapshot(source, force=force, progress=_echo, only=names)
    _echo(stats.summary())


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
