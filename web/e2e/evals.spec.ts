import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const report = JSON.parse(
  readFileSync(join(process.cwd(), "data", "eval-report.json"), "utf8"),
) as {
  generated_at: string;
  provider: string;
  corpus: { repo_count: number; file_count: number; chunk_count: number };
  retrieval: Record<string, { "recall@5": number; "MRR@10": number }>;
  answers: {
    citation_validity: number;
    sentences_without_citation: number;
    citations_total: number;
    citations_valid: number;
    refusal_errors: number;
  };
  injection: { probes: number; complied: number; cases: { id: string; complied: boolean }[] };
};

test.describe("evals", () => {
  test("the page renders the committed report, number for number", async ({ page }) => {
    await page.goto("/evals");

    await expect(page.getByTestId("evals-source")).toContainText(report.provider);
    await expect(page.getByTestId("evals-source")).toContainText(
      report.corpus.chunk_count.toLocaleString("en-GB"),
    );

    await expect(page.getByTestId("gate-citation-validity")).toContainText(
      `${(report.answers.citation_validity * 100).toFixed(1)}%`,
    );
    await expect(page.getByTestId("gate-citation-validity")).toContainText(
      `${report.answers.citations_valid.toLocaleString("en-GB")} / ${report.answers.citations_total.toLocaleString("en-GB")}`,
    );
    await expect(page.getByTestId("gate-uncited")).toContainText(
      `${report.answers.sentences_without_citation}`,
    );
    await expect(page.getByTestId("gate-injection")).toContainText(
      `${report.injection.complied} / ${report.injection.probes}`,
    );
    await expect(page.getByTestId("gate-refusal-errors")).toContainText(
      `${report.answers.refusal_errors}`,
    );
  });

  test("every retrieval arm is a row, with the report's recall to three decimals", async ({
    page,
  }) => {
    await page.goto("/evals");
    const arms = Object.entries(report.retrieval);
    expect(arms.length).toBeGreaterThan(1);
    for (const [arm, metrics] of arms) {
      const row = page.locator(`tr[data-arm="${arm}"]`);
      await expect(row, arm).toHaveCount(1);
      await expect(row.locator("td[data-recall]")).toHaveAttribute(
        "data-recall",
        metrics["recall@5"].toFixed(3),
      );
      await expect(row).toContainText(metrics["MRR@10"].toFixed(3));
    }
  });

  test("every injection probe is listed with its verdict and the answer it gave", async ({
    page,
  }) => {
    await page.goto("/evals");
    const cases = page.getByTestId("injection-cases").locator("details");
    await expect(cases).toHaveCount(report.injection.cases.length);
    for (const probe of report.injection.cases) {
      const item = cases.filter({ hasText: probe.id });
      await expect(item, probe.id).toHaveCount(1);
      await expect(item).toContainText(probe.complied ? "obeyed" : "did not obey");
      await item.locator("summary").click();
      await expect(item.locator("pre")).toBeVisible();
    }
  });
});
