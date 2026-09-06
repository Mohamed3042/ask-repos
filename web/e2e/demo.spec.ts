import { expect, test } from "@playwright/test";

import { askInUi } from "./support";

/**
 * The recorded walkthrough behind `docs/proof/demo.gif`.
 *
 * It is a real session against a real service, recorded by Playwright — the same journey
 * the runbook describes, in the same order. `scripts/make-demo-gif.mjs` converts the video
 * this produces. Nothing here is staged: if the service stops answering, the recording
 * fails instead of quietly showing an old one.
 *
 *   DEMO=1 E2E_VIDEO=1 npx playwright test demo && node scripts/make-demo-gif.mjs
 */
test.describe("recorded demo", () => {
  test.skip(process.env.DEMO !== "1", "set DEMO=1 to record the walkthrough");
  test.setTimeout(240_000);

  test("ask, read the receipts, then look at the corpus and the evals", async ({ page }) => {
    await page.setViewportSize({ width: 1200, height: 760 });

    await page.goto("/");
    await expect(page.getByTestId("demo-limits")).toBeVisible();
    await page.waitForTimeout(1200);

    // 1. A question the corpus can answer, with citations.
    await askInUi(page, "Which Kuwait branches does the Retail Ops Hub demo cover?");
    await expect(page.getByTestId("answer-sentences")).toBeVisible();
    await page.locator("a.chip").first().hover();
    await page.waitForTimeout(2200);

    // 2. One it cannot. The refusal is the product.
    await page.getByRole("button", { name: /shoe size/i }).click();
    await expect(page.getByTestId("answer-refusal")).toBeVisible({ timeout: 120_000 });
    await page.waitForTimeout(2200);

    // 3. What the answers are drawn from.
    await page.getByRole("link", { name: "Corpus", exact: true }).click();
    await expect(page.getByTestId("corpus-stats")).toBeVisible();
    await page.waitForTimeout(1200);
    await page.locator("tbody tr").first().click();
    await expect(page.getByTestId("selected-repo")).toBeVisible();
    await page.waitForTimeout(1800);

    // 4. The re-index gate: a human has to approve it.
    await page.getByTestId("reindex-button").scrollIntoViewIfNeeded();
    await page.getByTestId("reindex-button").click();
    await expect(page.getByTestId("reindex-panel")).toHaveAttribute(
      "data-state",
      /interrupted|refused/,
      { timeout: 60_000 },
    );
    await page.waitForTimeout(2200);

    // 5. The numbers, including the unflattering ones.
    await page.getByRole("link", { name: "Evals", exact: true }).click();
    await expect(page.getByTestId("evals-gates")).toBeVisible();
    await page.waitForTimeout(1500);
    await page.locator("details").first().click();
    await page.waitForTimeout(2000);

    // 6. Arabic, right to left.
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await page.waitForTimeout(2500);
  });
});
