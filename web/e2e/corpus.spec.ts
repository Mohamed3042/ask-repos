import { expect, test } from "@playwright/test";

import { apiCorpus } from "./support";

test.describe("corpus", () => {
  test("the totals on the page equal the totals /v1/corpus returns", async ({ page, request }) => {
    const corpus = await apiCorpus(request);
    await page.goto("/corpus");

    const number = (value: number) => value.toLocaleString("en-GB");
    await expect(page.getByTestId("stat-repos")).toContainText(number(corpus.repo_count));
    await expect(page.getByTestId("stat-files")).toContainText(number(corpus.file_count));
    await expect(page.getByTestId("stat-chunks")).toContainText(number(corpus.chunk_count));

    // Every repository the API reports has a row, with the API's own chunk count on it.
    for (const repo of corpus.repos) {
      const row = page.locator(`tr[data-repo="${repo.full_name}"]`);
      await expect(row, repo.full_name).toHaveCount(1);
      await expect(row.locator("td[data-chunks]")).toHaveAttribute("data-chunks", `${repo.chunks}`);
    }
    await expect(page.locator("tbody tr")).toHaveCount(corpus.repos.length);
  });

  test("a row click selects it and reveals the two labelled actions", async ({ page, request }) => {
    const corpus = await apiCorpus(request);
    const first = corpus.repos[0];
    await page.goto("/corpus");

    await expect(page.getByTestId("selected-repo")).toHaveCount(0);
    const row = page.locator(`tr[data-repo="${first.full_name}"]`);
    await row.click();

    await expect(row).toHaveAttribute("aria-selected", "true");
    const detail = page.getByTestId("selected-repo");
    await expect(detail).toBeVisible();
    await expect(detail).toContainText(first.full_name);
    await expect(detail.getByTestId("open-on-github")).toHaveAttribute("href", first.html_url);

    // Clicking navigates nowhere; only the labelled button does.
    await expect(page).toHaveURL(/\/corpus$/);
    await detail.getByRole("link", { name: /ask about this repository/i }).click();
    await expect(page).toHaveURL(new RegExp(`repo=${encodeURIComponent(first.full_name)}`));
    await expect(page.getByTestId("repo-scope")).toContainText(first.full_name);
  });

  test("webhook health distinguishes not-configured from zero deliveries", async ({
    page,
    request,
  }) => {
    const corpus = await apiCorpus(request);
    await page.goto("/corpus");
    const card = page.getByTestId("webhook-health");
    await expect(card).toBeVisible();
    if (corpus.webhook.configured) {
      await expect(card).toContainText(corpus.webhook.enabled ? /configured/i : /disabled/i);
    } else {
      await expect(card).toContainText(/not configured/i);
    }
    if (!corpus.webhook.last_delivery_at) {
      await expect(card).toContainText(/none received/i);
    }
  });

  test("requesting a re-index stops at the human-approval interrupt", async ({ page }) => {
    await page.goto("/corpus");
    const panel = page.getByTestId("reindex-panel");
    await panel.getByTestId("reindex-button").click();
    // Either the interrupt is shown for a decision, or the deployment refused outright;
    // both are correct, and both are visible. What must never happen is a silent re-index.
    await expect(panel).toHaveAttribute("data-state", /interrupted|refused/, { timeout: 60_000 });
    const state = await panel.getAttribute("data-state");
    if (state === "interrupted") {
      await expect(panel.getByRole("button", { name: /approve re-index/i })).toBeVisible();
      await expect(panel.getByRole("button", { name: /^decline$/i })).toBeVisible();
    } else {
      await expect(panel.getByTestId("reindex-refused")).toBeVisible();
    }
  });
});
