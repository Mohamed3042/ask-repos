import { expect, test } from "@playwright/test";

import { API_URL, apiAsk, askInUi, chipsOnPage, parseChipCitation } from "./support";

const GOLDEN = "Which Kuwait branches does the Retail Ops Hub demo cover?";
const UNANSWERABLE = "What is the author's shoe size?";

test.describe("ask", () => {
  test("a golden question renders sentences whose chips link to the API's citation", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("answer-empty")).toBeVisible();

    // The route handler's trace id comes off the response *headers*. The body does not:
    // reading a server-sent-event body after the fact through the debugging protocol
    // fails with `Network.getResponseBody: No data found for resource` — Chromium does
    // not retain a streamed body. That version of this test passed locally and failed in
    // CI twice, which is the worst kind of test.
    const streamed = page.waitForResponse(
      (response) => response.url().includes("/api/ask") && response.status() === 200,
    );
    await askInUi(page, GOLDEN);
    expect((await streamed).headers()["x-trace-id"], "the handler echoes its trace id").toMatch(
      /^[0-9a-f]{32}$/,
    );

    await expect(page.getByTestId("answer-sentences")).toBeVisible();
    const chips = await chipsOnPage(page);
    expect(chips.length, "the golden question must be answerable").toBeGreaterThan(0);

    // (1) Always: the link must agree with the citation the chip is *displaying*. This is
    // the defect class that matters — a chip that says one thing and opens another — and
    // it holds whatever provider answered.
    for (const chip of chips) {
      expect(chip.citation, "chip carries its citation string").toBeTruthy();
      const parsed = parseChipCitation(chip.citation!);
      expect(parsed, `chip citation is well formed: ${chip.citation}`).toBeTruthy();
      const url = new URL(chip.href);
      expect(url.origin).toBe("https://github.com");
      expect(decodeURIComponent(url.pathname)).toBe(
        `/${parsed!.repo}/blob/${url.pathname.split("/")[4]}/${parsed!.path}`,
      );
      // The link carries the FULL sha; the chip shows its prefix.
      expect(url.pathname.split("/")[4]).toMatch(
        new RegExp(`^${parsed!.shortSha}[0-9a-f]*$`, "i"),
      );
      expect(url.hash).toBe(`#L${parsed!.lineStart}-L${parsed!.lineEnd}`);
      expect(chip.text).toContain(`L${parsed!.lineStart}-L${parsed!.lineEnd}`);
    }

    // (2) When the answer came from the deterministic keyless path — which is what CI
    // runs — the chips must be exactly the citations the API returns for the same
    // question. Gemini is not reproducible run to run, so asserting set equality against
    // it would fail for a reason that is not a defect.
    const provider = (await page.getByTestId("provider").textContent())?.trim() ?? "";
    expect(provider, "the answer says which provider produced it").not.toBe("");
    if (provider.startsWith("extractive")) {
      const control = await apiAsk(request, GOLDEN, "extractive");
      const byCitation = new Map(
        control.sentences
          .filter((sentence) => sentence.kept)
          .flatMap((sentence) => sentence.citations)
          .map((citation) => [citation.citation, citation]),
      );
      for (const chip of chips) {
        const source = byCitation.get(chip.citation!);
        expect(source, `the API returned citation ${chip.citation}`).toBeTruthy();
        expect(chip.href).toBe(source!.url);
      }
      expect(new Set(chips.map((chip) => chip.citation))).toEqual(new Set(byCitation.keys()));
    }
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
