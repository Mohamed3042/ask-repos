import { expect, test } from "@playwright/test";

import { API_URL, apiAsk, askInUi, chipsOnPage, type ApiCitation } from "./support";

const GOLDEN = "Which Kuwait branches does the Retail Ops Hub demo cover?";
const UNANSWERABLE = "What is the author's shoe size?";

/** Pull the citations out of the SSE body the browser actually received. */
function citationsFromStream(body: string): ApiCitation[] {
  const citations: ApiCitation[] = [];
  for (const frame of body.split("\n\n")) {
    if (!frame.includes("event: sentence")) continue;
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (!data) continue;
    const sentence = JSON.parse(data) as { kept: boolean; citations: ApiCitation[] };
    if (sentence.kept) citations.push(...sentence.citations);
  }
  return citations;
}

test.describe("ask", () => {
  test("a golden question renders sentences whose chips link to the API's citation", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("answer-empty")).toBeVisible();

    // Compare the chips against the *same run* that produced them. Comparing against a
    // second `POST /v1/ask` was the first version of this test, and it failed for a
    // reason that was not a defect: the UI uses provider `auto` (Gemini here) and the
    // control call used `extractive`, so the two runs legitimately cited different lines.
    const streamed = page.waitForResponse(
      (response) => response.url().includes("/api/ask") && response.status() === 200,
    );
    await askInUi(page, GOLDEN);
    const response = await streamed;
    const expectedCitations = citationsFromStream(await response.text());
    expect(expectedCitations.length, "the golden question must be answerable").toBeGreaterThan(0);
    expect(response.headers()["x-trace-id"], "the route handler echoes its trace id").toMatch(
      /^[0-9a-f]{32}$/,
    );

    await expect(page.getByTestId("answer-sentences")).toBeVisible();
    const chips = await chipsOnPage(page);
    expect(chips.length).toBe(expectedCitations.length);

    const byCitation = new Map(expectedCitations.map((citation) => [citation.citation, citation]));
    for (const chip of chips) {
      expect(chip.citation, "chip carries its citation string").toBeTruthy();
      const source = byCitation.get(chip.citation!);
      expect(source, `the stream contained citation ${chip.citation}`).toBeTruthy();
      expect(chip.href).toBe(source!.url);
      expect(chip.href).toContain(`/blob/${source!.sha}/`);
      expect(chip.href).toContain(`#L${source!.line_start}-L${source!.line_end}`);
      expect(chip.text).toContain(`L${source!.line_start}-L${source!.line_end}`);
    }

    await expect(page.getByTestId("provider")).toBeVisible();
  });

  test("the deterministic extractive answer is reproducible through the API", async ({
    request,
  }) => {
    // The keyless path is the one CI measures, so it is asserted directly: same question,
    // same citations, twice.
    const first = await apiAsk(request, GOLDEN, "extractive");
    const second = await apiAsk(request, GOLDEN, "extractive");
    const cite = (answer: typeof first) =>
      answer.sentences.filter((s) => s.kept).flatMap((s) => s.citations.map((c) => c.citation));
    expect(first.refused).toBe(false);
    expect(cite(first).length).toBeGreaterThan(0);
    expect(cite(second)).toEqual(cite(first));
  });

  test("every answered sentence carries at least one citation", async ({ page }) => {
    await page.goto("/");
    await askInUi(page, GOLDEN);
    const sentences = page.locator("article.sentence");
    const count = await sentences.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(sentences.nth(index).locator("a.chip")).not.toHaveCount(0);
    }
  });

  test("a question the corpus cannot answer is refused, distinctly", async ({ page }) => {
    await page.goto("/");
    await askInUi(page, UNANSWERABLE);
    const refusal = page.getByTestId("answer-refusal");
    await expect(refusal).toBeVisible();
    await expect(refusal).toContainText(/not in the corpus/i);
    await expect(page.getByTestId("answer-sentences")).toHaveCount(0);
  });

  test("the demo-limits banner states the corpus owner and the rate limit", async ({
    page,
    request,
  }) => {
    const corpus = await request.get(`${API_URL}/v1/corpus`).then((response) => response.json());
    await page.goto("/");
    const banner = page.getByTestId("demo-limits");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(corpus.owner);
    await expect(banner).toContainText(
      corpus.rate_limit_per_minute > 0
        ? `${corpus.rate_limit_per_minute} questions per minute`
        : /no rate limit/i,
    );
  });

  test("Arabic switches the document to right-to-left without losing the layout", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("اسأل");
    // A reload must keep the choice: it lives in a cookie the server reads.
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    // And the body must not overflow sideways in RTL.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("the theme toggle survives a reload", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByRole("group", { name: /colour theme|سمة/i }).getByRole("button").nth(1).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });
});
