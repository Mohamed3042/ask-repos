"""Capture proof screenshots of the running service.

Drives the live OpenAPI page with Playwright, executes real requests against the running
container, highlights the part that matters in the actual pixels, and writes PNGs.

    pip install -e ".[shots]" && python -m playwright install chromium
    python scripts/shots.py --base http://localhost:8080 --out changelog/<date>-<slug>

Nothing here fabricates a result: every pixel is the service's own response page.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HIGHLIGHT = """
(needle) => {
  const label = needle.label;
  const live = document.querySelector('.live-responses-table');
  if (live) live.scrollIntoView({block: 'start'});
  const scope = live || document;
  const nodes = [...scope.querySelectorAll('pre, code, .microlight, td, div')];
  const hit = nodes.reverse().find(n => n.textContent && n.textContent.includes(needle.text));
  if (!hit) return false;
  hit.scrollIntoView({block: 'center'});
  hit.style.outline = '3px solid #ff3b30';
  hit.style.outlineOffset = '4px';
  hit.style.borderRadius = '6px';
  const tag = document.createElement('div');
  tag.textContent = label;
  Object.assign(tag.style, {
    position: 'absolute', zIndex: 9999, background: '#ff3b30', color: '#fff',
    font: '600 13px system-ui, sans-serif', padding: '3px 8px', borderRadius: '4px',
    transform: 'translateY(-100%)',
  });
  const box = hit.getBoundingClientRect();
  tag.style.left = `${box.left + window.scrollX}px`;
  tag.style.top = `${box.top + window.scrollY - 6}px`;
  document.body.appendChild(tag);
  return true;
}
"""


def run_operation(page: Page, anchor: str, body: dict | None) -> None:
    page.click(f"#operations-{anchor} .opblock-summary")
    page.click(f"#operations-{anchor} button.try-out__btn")
    if body is not None:
        editor = page.locator(f"#operations-{anchor} textarea.body-param__text")
        editor.fill(json.dumps(body, indent=2))
    page.click(f"#operations-{anchor} button.execute")
    page.wait_for_selector(f"#operations-{anchor} .responses-table.live-responses-table",
                           timeout=120_000)
    page.wait_for_timeout(1200)


def shot(page: Page, out: Path, name: str, needle: str, label: str) -> None:
    found = page.evaluate(HIGHLIGHT, {"text": needle, "label": label})
    page.wait_for_timeout(300)
    target = out / name
    page.screenshot(path=str(target), full_page=False)
    print(f"{'wrote' if found else 'wrote (no highlight anchor found)'} {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--out", default="changelog/shots")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        # Reuse a Chromium already on the machine when its build does not match the
        # pinned Playwright: set ASK_REPOS_CHROMIUM to that chrome.exe.
        executable = os.environ.get("ASK_REPOS_CHROMIUM") or None
        browser = playwright.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 1480, "height": 1000}, device_scale_factor=2)

        page.goto(f"{args.base}/docs", wait_until="networkidle")
        run_operation(
            page,
            "ask-ask_v1_ask_post",
            {"question": "Which Kuwait branches does the Retail Ops Hub demo cover?", "k": 8},
        )
        shot(
            page,
            out,
            "01-ask-cited.png",
            "#L",
            "every sentence carries owner/repo/path#Lstart-Lend@sha",
        )

        page.goto(f"{args.base}/docs", wait_until="networkidle")
        run_operation(
            page,
            "ask-ask_v1_ask_post",
            {"question": "What is the author's monthly rent?", "k": 8},
        )
        shot(page, out, "02-refusal.png", "Not in the corpus", "nothing to anchor, so it refuses")

        page.goto(f"{args.base}/docs", wait_until="networkidle")
        run_operation(page, "corpus-corpus_v1_corpus_get", None)
        shot(page, out, "03-corpus.png", "chunk_count", "what the answers are drawn from")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
