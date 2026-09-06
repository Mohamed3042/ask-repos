import { describe, expect, it } from "vitest";

import recorded from "@/tests/fixtures/ask-response.json";
import {
  answerToMarkdown,
  blobUrl,
  chipLabel,
  parseCitation,
  shortenPath,
  type Citation,
} from "@/lib/citations";

/**
 * The fixture is a real `POST /v1/ask` response, captured from the running service
 * (see `tests/fixtures/README.md`). The first test is the one that matters: the URL the
 * chip builds must equal the URL the API produced, for every citation. If the citation
 * format ever changes on either side, this goes red instead of the chips quietly
 * pointing at the wrong lines.
 */
const citations: Citation[] = recorded.sentences.flatMap(
  (sentence) => sentence.citations as Citation[],
);

describe("blobUrl", () => {
  it("rebuilds exactly the URL the API returned, for every recorded citation", () => {
    expect(citations.length).toBeGreaterThan(0);
    for (const citation of citations) {
      expect(blobUrl(citation)).toBe(citation.url);
    }
  });

  it("uses the full stored SHA, not the short one in the citation string", () => {
    const citation = citations[0];
    expect(citation.sha.length).toBeGreaterThan(20);
    expect(blobUrl(citation)).toContain(`/blob/${citation.sha}/`);
  });

  it("percent-encodes each path segment but keeps the separators", () => {
    const url = blobUrl({
      ...citations[0],
      repo: "octo/demo",
      path: "docs/a b/ملف.md",
      sha: "a".repeat(40),
      line_start: 3,
      line_end: 9,
    });
    expect(url).toBe(
      `https://github.com/octo/demo/blob/${"a".repeat(40)}/docs/a%20b/%D9%85%D9%84%D9%81.md#L3-L9`,
    );
  });
});

describe("parseCitation", () => {
  it("parses every recorded citation string into its parts", () => {
    for (const citation of citations) {
      const parsed = parseCitation(citation.citation);
      expect(parsed, citation.citation).not.toBeNull();
      expect(parsed!.repo).toBe(citation.repo);
      expect(parsed!.path).toBe(citation.path);
      expect(parsed!.lineStart).toBe(citation.line_start);
      expect(parsed!.lineEnd).toBe(citation.line_end);
      expect(citation.sha.startsWith(parsed!.shortSha)).toBe(true);
    }
  });

  it("keeps slashes inside the path", () => {
    const parsed = parseCitation("octo/demo/src/deep/nested/file.py#L1-L2@abc1234");
    expect(parsed).toMatchObject({
      owner: "octo",
      name: "demo",
      path: "src/deep/nested/file.py",
      lineStart: 1,
      lineEnd: 2,
      shortSha: "abc1234",
    });
  });

  it.each([
    ["missing the sha", "octo/demo/README.md#L1-L2"],
    ["missing the line span", "octo/demo/README.md@abc1234"],
    ["no repository", "README.md#L1-L2@abc1234"],
    ["a backwards span", "octo/demo/README.md#L9-L2@abc1234"],
    ["a zero start line", "octo/demo/README.md#L0-L2@abc1234"],
    ["empty", ""],
  ])("returns null for %s", (_label, raw) => {
    expect(parseCitation(raw)).toBeNull();
  });
});

describe("chipLabel and shortenPath", () => {
  it("shows the repository name without the owner, and the line span", () => {
    const label = chipLabel(citations[0]);
    expect(label.repo).toBe(citations[0].repo.split("/")[1]);
    expect(label.lines).toBe(`L${citations[0].line_start}-L${citations[0].line_end}`);
  });

  it("elides the middle of a deep path, keeping the file name", () => {
    expect(shortenPath("a/b/c/d/e.md")).toBe("…/d/e.md");
    expect(shortenPath("README.md")).toBe("README.md");
    expect(shortenPath("docs/adr/0002.md")).toBe("docs/adr/0002.md");
  });
});

describe("answerToMarkdown", () => {
  it("carries every citation and its URL under its sentence", () => {
    const markdown = answerToMarkdown(
      recorded.question,
      recorded.sentences as { text: string; citations: Citation[] }[],
      { provider: recorded.provider, model: recorded.model },
    );
    expect(markdown).toContain(`> ${recorded.question}`);
    for (const citation of citations) {
      expect(markdown).toContain(citation.citation);
      expect(markdown).toContain(citation.url);
    }
    const provider = [recorded.provider, recorded.model].filter(Boolean).join(" ");
    expect(markdown.trimEnd().endsWith(`provider: ${provider}`)).toBe(true);
  });
});
