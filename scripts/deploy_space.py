#!/usr/bin/env python
"""Upload the Hugging Face Space that hosts the API, and wait for it to answer.

    python scripts/deploy_space.py                       # upload, wait, verify
    python scripts/deploy_space.py --check               # only verify a running Space
    python scripts/deploy_space.py --space Medo4334/ask-repos

The Space repository holds five files: the Dockerfile, its entrypoint, the Space card, and
the corpus snapshot the image build reads. The application itself is not copied — the
Dockerfile starts `FROM ghcr.io/mohamed3042/ask-repos`, the image CI already publishes, so
the Space and the container in `docker compose up` are the same build.

Needs a write-scoped token: `hf auth login`, or `HF_TOKEN` in the environment. The token is
never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPACE = "Medo4334/ask-repos"
# (path in this repository, path in the Space repository)
FILES: list[tuple[str, str]] = [
    ("deploy/hf-space/Dockerfile", "Dockerfile"),
    ("deploy/hf-space/entrypoint.sh", "deploy/hf-space/entrypoint.sh"),
    ("deploy/hf-space/README.md", "README.md"),
    ("deploy/hf-space/.dockerignore", ".dockerignore"),
]
CORPUS_DIR = "evals/corpus"


def space_url(space_id: str) -> str:
    owner, name = space_id.split("/", 1)
    slug = f"{owner}-{name}".lower().replace("_", "-").replace(".", "-")
    return f"https://{slug}.hf.space"


def http_json(url: str, timeout: float = 30.0) -> tuple[int, dict | None]:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, None
    except urllib.error.HTTPError as error:
        return error.code, None
    except Exception:
        return 0, None


def verify(base: str, attempts: int = 90, delay: float = 20.0) -> dict:
    """Poll until /v1/corpus answers 200 with a non-empty corpus, or give up loudly."""
    last = (0, None)
    for attempt in range(1, attempts + 1):
        status, body = http_json(f"{base}/v1/corpus", timeout=60)
        last = (status, body)
        if status == 200 and body and body.get("chunk_count"):
            print(f"HTTP 200 from {base}/v1/corpus after {attempt} attempt(s)")
            return body
        print(f"  [{attempt}/{attempts}] {base}/v1/corpus -> {status or 'no answer'}", flush=True)
        time.sleep(delay)
    raise SystemExit(
        f"the Space never answered with a corpus: last status {last[0]}. "
        f"Open {base}/ and read the build log."
    )


def report(base: str, corpus: dict) -> None:
    print("\n-- measured on the live Space --")
    print(f"url                 {base}")
    print(f"version             {corpus.get('version')}")
    print(f"read-only           {corpus.get('readonly')}")
    print(f"rate limit          {corpus.get('rate_limit_per_minute')}/min")
    print(f"repositories        {corpus.get('repo_count')}")
    print(f"files               {corpus.get('file_count')}")
    print(f"chunks              {corpus.get('chunk_count')}")
    print(f"generation          {corpus.get('generation')}")
    status, _ = http_json(f"{base}/health")
    print(f"GET /health         {status}")
    request = urllib.request.Request(
        f"{base}/v1/index",
        data=b'{"owner":"Mohamed3042"}',
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"POST /v1/index      {response.status}  <-- expected 403")
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read()).get("detail", "")[:80]
        except Exception:
            pass
        print(f"POST /v1/index      {error.code}  {detail}")


def upload(space_id: str) -> None:
    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError

    api = HfApi()
    try:
        who = api.whoami()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "no Hugging Face credentials. Run `hf auth login` with a WRITE token "
            f"(account Medo4334), or set HF_TOKEN. ({type(exc).__name__})"
        ) from exc
    print(f"authenticated as {who.get('name')}")

    try:
        api.create_repo(space_id, repo_type="space", space_sdk="docker", exist_ok=True)
    except HfHubHTTPError as exc:
        raise SystemExit(f"could not create or reach the Space {space_id}: {exc}") from exc

    operations = []
    for local, remote in FILES:
        path = REPO_ROOT / local
        if not path.exists():
            continue
        operations.append((path, remote))
    corpus = REPO_ROOT / CORPUS_DIR
    for path in sorted(corpus.iterdir()):
        if path.is_file():
            operations.append((path, f"{CORPUS_DIR}/{path.name}"))

    print(f"uploading {len(operations)} files to {space_id}")
    from huggingface_hub import CommitOperationAdd

    api.create_commit(
        repo_id=space_id,
        repo_type="space",
        operations=[
            CommitOperationAdd(path_in_repo=remote, path_or_fileobj=str(path))
            for path, remote in operations
        ],
        commit_message="ask-repos: read-only API Space (corpus baked at build time)",
    )
    print(f"uploaded. Build log: https://huggingface.co/spaces/{space_id}?logs=build")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default=DEFAULT_SPACE)
    parser.add_argument("--check", action="store_true", help="verify only, do not upload")
    parser.add_argument("--attempts", type=int, default=90)
    args = parser.parse_args()

    base = space_url(args.space)
    if not args.check:
        upload(args.space)
        print("waiting for the Space to build and boot (this takes several minutes)")
    corpus = verify(base, attempts=args.attempts)
    report(base, corpus)
    return 0


if __name__ == "__main__":
    sys.exit(main())
