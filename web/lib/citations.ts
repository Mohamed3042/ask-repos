/**
 * Citations, parsed and rendered.
 *
 * The API hands back both a compact string — `owner/repo/path#L10-L24@5a44442` — and the
 * fully resolved GitHub URL. The UI could just render the URL, but then nothing would ever
 * catch the day the two stop agreeing. So the chip builds its own href from the parts and
 * `lib/citations.test.ts` asserts, for every citation in a recorded API response, that the
 * href it builds is byte-identical to the one the API produced.
 */

export interface Citation {
  chunk_id: number;
  repo: string;
  path: string;
  sha: string;
  line_start: number;
  line_end: number;
  citation: string;
  url: string;
}

export interface ParsedCitation {
  owner: string;
  name: string;
  repo: string;
  path: string;
  lineStart: number;
  lineEnd: number;
  shortSha: string;
}

/** `owner/repo/path/with/slashes.md#L10-L24@5a44442` */
const CITATION_RE = /^([^/\s]+)\/([^/\s]+)\/(.+)#L(\d+)-L(\d+)@([0-9a-f]+)$/i;

export function parseCitation(raw: string): ParsedCitation | null {
  const match = CITATION_RE.exec(raw.trim());
  if (!match) return null;
  const [, owner, name, path, start, end, shortSha] = match;
  const lineStart = Number(start);
  const lineEnd = Number(end);
  // A span that runs backwards is a malformed citation, not a citation to be rendered.
  if (!Number.isSafeInteger(lineStart) || !Number.isSafeInteger(lineEnd)) return null;
  if (lineStart < 1 || lineEnd < lineStart) return null;
  return { owner, name, repo: `${owner}/${name}`, path, lineStart, lineEnd, shortSha };
}

/**
 * The GitHub blob URL for a citation, built from the parts rather than trusted.
 * The full SHA is used, not the short one in the citation string, so the link keeps
 * pointing at the exact bytes the answer was checked against.
 */
export function blobUrl(citation: Citation): string {
  const path = citation.path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return (
    `https://github.com/${citation.repo}/blob/${citation.sha}/${path}` +
    `#L${citation.line_start}-L${citation.line_end}`
  );
}

/** What the chip shows: `repo · path:L10-L24`, shortened from the middle when long. */
export function chipLabel(citation: Citation): { repo: string; path: string; lines: string } {
  const name = citation.repo.includes("/") ? citation.repo.split("/")[1] : citation.repo;
  return {
    repo: name,
    path: shortenPath(citation.path),
    lines: `L${citation.line_start}-L${citation.line_end}`,
  };
}

export function shortenPath(path: string, maxSegments = 3): string {
  const parts = path.split("/");
  if (parts.length <= maxSegments) return path;
  return `…/${parts.slice(-(maxSegments - 1)).join("/")}`;
}

/** The plain-text form used by "copy answer with citations". */
export function answerToMarkdown(
  question: string,
  sentences: { text: string; citations: Citation[] }[],
  meta: { provider?: string | null; model?: string | null },
): string {
  const lines: string[] = [`> ${question}`, ""];
  for (const sentence of sentences) {
    lines.push(sentence.text);
    for (const citation of sentence.citations) {
      lines.push(`  - ${citation.citation}`);
      lines.push(`    ${blobUrl(citation)}`);
    }
    lines.push("");
  }
  const provider = [meta.provider, meta.model].filter(Boolean).join(" ");
  if (provider) lines.push(`provider: ${provider}`);
  return lines.join("\n").trimEnd() + "\n";
}
