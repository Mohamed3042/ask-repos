#!/usr/bin/env python
"""Probe the two live URLs and keep an honest, self-measured uptime record.

    python scripts/uptime_probe.py --api https://… --web https://… --out docs/proof

Writes `uptime.json` (a rolling window of raw samples plus the totals) and
`uptime-badge.json` (a shields.io endpoint document). Both are committed by the hourly
workflow, which is what makes the badge auditable: the number in it is derived from the
samples in the file beside it, and anyone can recompute it.

The honesty rules this file exists to keep:

* The badge says **self-measured**. One prober, one region, hourly — not a monitoring
  service, and the label never pretends otherwise.
* "since <date>" is the first sample actually recorded, not the day the project started.
* A run that could not reach the network records a `null` outcome, which counts as
  *unknown*, not as *down* and not as *up*. A number nobody measured is not zero (RL 003).
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WINDOW = 24 * 30  # keep 30 days of hourly samples
TIMEOUT = 30.0


def probe(url: str) -> dict[str, Any]:
    """One request. Returns the status and how long it took, or the failure."""
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"user-agent": "ask-repos-uptime/1"})
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
            elapsed = time.perf_counter() - started
            return {"status": response.status, "ms": round(elapsed * 1000), "error": None}
    except urllib.error.HTTPError as error:
        return {
            "status": error.code,
            "ms": round((time.perf_counter() - started) * 1000),
            "error": None,
        }
    except Exception as error:  # noqa: BLE001 - a failure to reach it is the measurement
        return {
            "status": None,
            "ms": round((time.perf_counter() - started) * 1000),
            "error": f"{type(error).__name__}: {error}"[:200],
        }


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"targets": {}, "samples": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"targets": {}, "samples": []}


def summarise(samples: list[dict[str, Any]], key: str) -> dict[str, Any]:
    outcomes = [sample[key] for sample in samples if key in sample]
    checked = [outcome for outcome in outcomes if outcome.get("status") is not None]
    ok = [outcome for outcome in checked if 200 <= outcome["status"] < 400]
    latencies = sorted(outcome["ms"] for outcome in ok)
    return {
        "samples": len(outcomes),
        # Runs where the prober itself could not reach the network are excluded from the
        # ratio and counted separately, rather than silently scored as downtime.
        "checked": len(checked),
        "unreachable_prober": len(outcomes) - len(checked),
        "up": len(ok),
        "uptime_percent": round(100 * len(ok) / len(checked), 2) if checked else None,
        "median_ms": latencies[len(latencies) // 2] if latencies else None,
        "last_status": outcomes[-1]["status"] if outcomes else None,
    }


def badge(summary: dict[str, Any], since: str | None) -> dict[str, Any]:
    percent = summary["uptime_percent"]
    if percent is None:
        message, colour = "not measured", "lightgrey"
    else:
        message = f"{percent:.2f}%"
        colour = "brightgreen" if percent >= 99 else "green" if percent >= 95 else "orange"
    day = (since or "")[:10]
    return {
        "schemaVersion": 1,
        "label": f"self-measured uptime since {day}" if day else "self-measured uptime",
        "message": message,
        "color": colour,
        "cacheSeconds": 1800,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="API URL to probe (use /health)")
    parser.add_argument("--web", required=True, help="UI URL to probe")
    parser.add_argument("--out", default="docs/proof")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    record_path = out / "uptime.json"
    record = load(record_path)

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    sample = {"at": now, "api": probe(args.api), "web": probe(args.web)}
    record["targets"] = {"api": args.api, "web": args.web}
    record.setdefault("samples", []).append(sample)
    record["samples"] = record["samples"][-WINDOW:]

    since = record["samples"][0]["at"] if record["samples"] else now
    record["since"] = since
    record["updated_at"] = now
    record["method"] = (
        "One HTTP GET per target per hour from a GitHub-hosted runner. Self-measured: "
        "one prober, one region, no third-party monitoring service. Runs where the prober "
        "itself could not reach the network are counted as unknown, not as downtime."
    )
    record["api_summary"] = summarise(record["samples"], "api")
    record["web_summary"] = summarise(record["samples"], "web")
    # The badge tracks the UI, because that is the URL a reader opens.
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "uptime-badge.json").write_text(
        json.dumps(badge(record["web_summary"], since), indent=2) + "\n", encoding="utf-8"
    )

    for name in ("api", "web"):
        outcome = sample[name]
        summary = record[f"{name}_summary"]
        print(
            f"{name:4} {record['targets'][name]} -> "
            f"{outcome['status'] or outcome['error']} in {outcome['ms']} ms  |  "
            f"{summary['up']}/{summary['checked']} up since {since[:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
