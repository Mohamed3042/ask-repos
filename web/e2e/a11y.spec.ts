import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { askInUi } from "./support";

/**
 * Accessibility, measured rather than asserted in prose.
 *
 * This exists because reasoning about contrast is not measuring it. The tokens in
 * `globals.css` were chosen against WCAG AA and checked by hand — and then one component
 * put `opacity: 0.8` on a `.label`, which took a compliant #52605b down to an effective
 * #75807c at 4.08:1 on white. Lighthouse found it on the deployed site; nothing in the
 * repository could have. Now something can.
 *
 * Every page is scanned in both themes and both languages, because a colour token that
 * passes in light can fail in dark and a layout that passes in LTR can reflow in RTL.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function scan(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const summary = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact}): ${violation.nodes.length} node(s) — ` +
      violation.nodes
        .slice(0, 3)
        .map((node) => `${node.target.join(" ")} :: ${(node.failureSummary ?? "").slice(0, 160)}`)
        .join(" | "),
  );
  expect(summary, `${label}: WCAG A/AA violations`).toEqual([]);
}

const PAGES: [string, string][] = [
  ["/", "ask"],
  ["/corpus", "corpus"],
  ["/evals", "evals"],
];

test.describe("accessibility", () => {
  for (const [path, name] of PAGES) {
    for (const theme of ["light", "dark"] as const) {
      test(`${name} has no WCAG A/AA violations in ${theme}`, async ({ page, context }) => {
        await context.addCookies([
          { name: "ask_repos_theme", value: theme, url: "http://127.0.0.1" },
        ]);
        await page.goto(path);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await scan(page, `${path} (${theme})`);
      });
    }
  }

  test("the Arabic, right-to-left rendering has no violations either", async ({
    page,
    context,
  }) => {
    await context.addCookies([{ name: "ask_repos_locale", value: "ar", url: "http://127.0.0.1" }]);
    for (const [path] of PAGES) {
      await page.goto(path);
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      await scan(page, `${path} (ar, rtl)`);
    }
  });

  test("an answered question - chips, provider tag and all - has no violations", async ({
    page,
  }) => {
    await page.goto("/");
    await askInUi(page, "Which Kuwait branches does the Retail Ops Hub demo cover?");
    await expect(page.getByTestId("answer-sentences")).toBeVisible();
    await scan(page, "/ with an answer rendered");
  });

  test("the refusal state has no violations", async ({ page }) => {
    await page.goto("/");
    await askInUi(page, "What is the author's shoe size?");
    await expect(page.getByTestId("answer-refusal")).toBeVisible();
    await scan(page, "/ with a refusal rendered");
  });
});
