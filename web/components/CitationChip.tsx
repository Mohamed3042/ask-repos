import { blobUrl, chipLabel, type Citation } from "@/lib/citations";

/**
 * The chip is the product in miniature: it names the repository, the path and the exact
 * line span, and its href is rebuilt from those parts rather than copied from the API —
 * see `lib/citations.test.ts`, which asserts the two always agree.
 *
 * `dir="ltr"` is pinned because a path with line numbers is a code identifier: in an
 * Arabic (RTL) page a bare `README.md#L9-L37` would otherwise reorder on screen.
 */
export function CitationChip({ citation, hint }: { citation: Citation; hint: string }) {
  const label = chipLabel(citation);
  const href = blobUrl(citation);
  return (
    <a
      className="chip"
      dir="ltr"
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      title={`${citation.citation} — ${hint}`}
      data-citation={citation.citation}
      data-chunk-id={citation.chunk_id}
    >
      <span>
        {label.repo}/{label.path}
      </span>
      <span className="chip-lines">{label.lines}</span>
      <span className="chip-out" aria-hidden="true">
        ↗
      </span>
    </a>
  );
}
