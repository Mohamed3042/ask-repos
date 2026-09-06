"use client";

import Link from "next/link";
import { useState } from "react";

import { dictionaryFor, formatBytes, formatNumber, formatWhen, type Locale } from "@/lib/i18n";
import type { Corpus, RepoRow } from "@/lib/types";

/**
 * The repository table, built for the hand (RL 004):
 *
 *   click or Enter on a row  → selects it (whole row is the target, 40px tall, strong state)
 *   "Open on GitHub"         → navigates, and says so on the button
 *   "Ask about this…"        → navigates to the question page scoped to the selection
 *
 * Nothing navigates on a row click, so a mis-click costs nothing.
 */
export function CorpusExplorer({ corpus, locale }: { corpus: Corpus; locale: Locale }) {
  const dictionary = dictionaryFor(locale);
  const [selected, setSelected] = useState<string | null>(null);
  const row = corpus.repos.find((candidate) => candidate.full_name === selected) ?? null;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <h2>{dictionary.corpus.repos}</h2>
          <span className="small muted">{dictionary.corpus.selectHint}</span>
        </div>
        <div className="table-scroll">
          <table>
            <caption className="sr-only-label">{dictionary.corpus.repos}</caption>
            <thead>
              <tr>
                <th scope="col">{dictionary.corpus.table.repository}</th>
                <th scope="col">{dictionary.corpus.table.language}</th>
                <th scope="col" className="num">
                  {dictionary.corpus.table.files}
                </th>
                <th scope="col" className="num">
                  {dictionary.corpus.table.chunks}
                </th>
                <th scope="col" className="num">
                  {dictionary.corpus.table.size}
                </th>
                <th scope="col">{dictionary.corpus.table.indexed}</th>
              </tr>
            </thead>
            <tbody>
              {corpus.repos.map((repo) => {
                const isSelected = repo.full_name === selected;
                return (
                  <tr
                    key={repo.full_name}
                    className="selectable"
                    tabIndex={0}
                    aria-selected={isSelected}
                    data-repo={repo.full_name}
                    onClick={() => setSelected(isSelected ? null : repo.full_name)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(isSelected ? null : repo.full_name);
                      }
                    }}
                  >
                    <td dir="ltr">{repo.full_name}</td>
                    <td>{repo.language ?? <span className="muted">—</span>}</td>
                    <td className="num">{formatNumber(repo.files, locale)}</td>
                    <td className="num" data-chunks={repo.chunks}>
                      {formatNumber(repo.chunks, locale)}
                    </td>
                    <td className="num">{formatBytes(repo.bytes, locale)}</td>
                    <td>
                      {formatWhen(repo.last_indexed_at, locale) ?? (
                        <span className="muted">{dictionary.corpus.never}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {row ? <SelectedRepo row={row} locale={locale} /> : null}
    </div>
  );
}

function SelectedRepo({ row, locale }: { row: RepoRow; locale: Locale }) {
  const dictionary = dictionaryFor(locale);
  return (
    <div className="card" data-testid="selected-repo">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 dir="ltr" style={{ margin: 0 }}>
          {row.full_name}
        </h2>
        <span className="tag">{dictionary.corpus.selected}</span>
      </div>
      {row.description ? <p className="muted">{row.description}</p> : null}
      <dl className="detail">
        <div>
          <dt>{dictionary.corpus.table.files}</dt>
          <dd>{formatNumber(row.files, locale)}</dd>
        </div>
        <div>
          <dt>{dictionary.corpus.table.chunks}</dt>
          <dd>{formatNumber(row.chunks, locale)}</dd>
        </div>
        <div>
          <dt>{dictionary.corpus.table.size}</dt>
          <dd>{formatBytes(row.bytes, locale)}</dd>
        </div>
        <div>
          <dt>tree sha</dt>
          <dd className="mono small" dir="ltr">
            {row.tree_sha ? row.tree_sha.slice(0, 12) : <span className="muted">—</span>}
          </dd>
        </div>
      </dl>
      <div className="row">
        <a
          className="btn"
          href={row.html_url}
          target="_blank"
          rel="noreferrer noopener"
          data-testid="open-on-github"
        >
          {dictionary.corpus.open} ↗
        </a>
        <Link className="btn btn-primary" href={`/?repo=${encodeURIComponent(row.full_name)}`}>
          {dictionary.corpus.ask}
        </Link>
      </div>
    </div>
  );
}
