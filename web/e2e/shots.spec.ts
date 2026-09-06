import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { askInUi } from "./support";

/**
 * The screenshots used in the README, the changelog entry and the demo runbook.
 *
 * They are taken by driving the real interface against a real service — never assembled
 * or mocked — so re-running this spec regenerates every picture in the documentation:
 *
 *   npm run shots                       # against whatever the config points at
 *   E2E_BASE_URL=https://ask-repos-live.netlify.app npm run shots
 *
 * `SHOT_LABEL` goes into the filenames so live and local sets can sit side by side.
 */

const OUT = join(process.cwd(), "..", "docs", "proof", "shots");
const LABEL = process.env.SHOT_LABEL ?? "local";
const DESKTOP = { width: 1280, height: 900 };
const PHONE = { width: 390, height: 844 };

async function shoot(page: import("@playwright/test").Page, name: string, fullPage = false) {
  mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: join(OUT, `${LABEL}-${name}.png`), fullPage });
}

test.describe("documentation screenshots", () => {
  test.skip(process.env.SHOTS !== "1", "set SHOTS=1 to regenerate the documentation images");
  test.setTimeout(180_000);

  test("ask, answered with citation chips", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    await askInUi(page, "Which Kuwait branches does the Retail Ops Hub demo cover?");
    await expect(page.getByTestId("answer-sentences")).toBeVisible();
    await shoot(page, "ask-answered", true);
  });

  test("ask, refused", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    await askInUi(page, "What is the author's shoe size?");
    await expect(page.getByTestId("answer-refusal")).toBeVisible();
    await shoot(page, "ask-refused");
  });

  test("corpus, with a row selected", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/corpus");
    const row = page.locator("tbody tr").first();
    await row.click();
    await expect(page.getByTestId("selected-repo")).toBeVisible();
    await shoot(page, "corpus", true);
  });

  test("evals", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/evals");
    await expect(page.getByTestId("evals-gates")).toBeVisible();
    await shoot(page, "evals", true);
  });

  test("dark theme", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/evals");
    await page.getByRole("group", { name: /colour theme|سمة/i }).getByRole("button").nth(1).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await shoot(page, "evals-dark", true);
  });

  test("Arabic, right to left", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/corpus");
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("المصدر");
    await shoot(page, "corpus-arabic", true);
  });

  test("a phone", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto("/evals");
    await expect(page.getByTestId("evals-gates")).toBeVisible();
    await shoot(page, "phone-evals");
    await page.goto("/");
    await askInUi(page, "Which Kuwait branches does the Retail Ops Hub demo cover?");
    await shoot(page, "phone-ask");
  });
});
