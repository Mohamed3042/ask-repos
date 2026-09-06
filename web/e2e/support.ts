import { expect, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The API the UI is pointed at. The specs call it directly so they can compare what the
 * browser rendered against what the service actually said — a UI test that only checks
 * the UI proves nothing about the boundary.
 */
export const API_URL = (process.env.ASK_REPOS_API_URL ?? "http://localhost:8080").replace(
  /\/+$/,
  "",
);

export interface ApiCitation {
  chunk_id: number;
  repo: string;
  path: string;
  sha: string;
  line_start: number;
  line_end: number;
  citation: string;
  url: string;
}

export interface ApiAnswer {
  refused: boolean;
  answer: string;
  provider: string | null;
  model: string | null;
  sentences: { text: string; kept: boolean; citations: ApiCitation[] }[];
}

export async function apiAsk(
  request: APIRequestContext,
  question: string,
  provider: "auto" | "extractive" | "gemini" = "extractive",
): Promise<ApiAnswer> {
  const response = await request.post(`${API_URL}/v1/ask`, {
    data: { question, provider },
    timeout: 120_000,
  });
  expect(response.ok(), `POST /v1/ask -> ${response.status()}`).toBeTruthy();
  return (await response.json()) as ApiAnswer;
}

export async function apiCorpus(request: APIRequestContext) {
  const response = await request.get(`${API_URL}/v1/corpus`, { timeout: 60_000 });
  expect(response.ok(), `GET /v1/corpus -> ${response.status()}`).toBeTruthy();
  return await response.json();
}

/** Ask through the UI and wait until the stream has finished. */
export async function askInUi(page: Page, question: string) {
  await page.getByLabel(/your question/i).fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const panel = page.getByTestId("answer-panel");
  await expect(panel).toHaveAttribute("data-phase", /done|interrupted|error/, { timeout: 120_000 });
  return panel;
}

/** Parse `owner/repo/path#Lstart-Lend@shortsha` — the string the chip displays. */
export function parseChipCitation(raw: string) {
  const match = /^([^/\s]+)\/([^/\s]+)\/(.+)#L(\d+)-L(\d+)@([0-9a-f]+)$/i.exec(raw.trim());
  if (!match) return null;
  const [, owner, name, path, start, end, shortSha] = match;
  return {
    repo: `${owner}/${name}`,
    path,
    lineStart: Number(start),
    lineEnd: Number(end),
    shortSha,
  };
}

/** Every citation chip currently on the page, as `{ citation, href }`. */
export async function chipsOnPage(page: Page) {
  return await page.locator("a.chip").evaluateAll((nodes) =>
    nodes.map((node) => ({
      citation: node.getAttribute("data-citation"),
      href: (node as HTMLAnchorElement).href,
      text: node.textContent?.replace(/\s+/g, " ").trim() ?? "",
    })),
  );
}
