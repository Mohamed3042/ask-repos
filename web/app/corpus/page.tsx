import { cookies } from "next/headers";

import { CorpusExplorer } from "@/components/CorpusExplorer";
import { ReindexPanel } from "@/components/ReindexPanel";
import { getCorpus } from "@/lib/api";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  dictionaryFor,
  formatBytes,
  formatNumber,
  formatWhen,
  isLocale,
} from "@/lib/i18n";

export const dynamic = "force-dynamic";

export const metadata = { title: "Corpus — ask-repos" };

export default async function CorpusPage() {
  const store = await cookies();
  const raw = store.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  const dictionary = dictionaryFor(locale);
  const result = await getCorpus();

  if (!result.ok) {
    return (
      <>
        <h1>{dictionary.corpus.title}</h1>
        <div className="banner banner-danger" data-testid="corpus-error">
          <span aria-hidden="true">✕</span>
          <p>
            <strong>{dictionary.corpus.errorTitle}. </strong>
            {result.detail}
          </p>
        </div>
      </>
    );
  }

  const corpus = result.corpus;
  const lastRun = corpus.last_index_run;
  // An empty corpus is a state of its own: the service is up and has indexed nothing.
  // It is not "0 repositories" as a measurement (RL 003).
  const empty = corpus.chunk_count === 0;

  return (
    <>
      <div>
        <h1>{dictionary.corpus.title}</h1>
        <p className="lede">{dictionary.corpus.lede}</p>
      </div>

      {empty ? (
        <div className="empty" data-testid="corpus-empty">
          <h2>{dictionary.corpus.emptyTitle}</h2>
          <p style={{ marginInline: "auto" }}>{dictionary.corpus.emptyBody}</p>
        </div>
      ) : (
        <>
          <div className="stats" data-testid="corpus-stats">
            <Stat
              label={dictionary.corpus.repos}
              value={formatNumber(corpus.repo_count, locale)}
              testId="stat-repos"
            />
            <Stat
              label={dictionary.corpus.files}
              value={formatNumber(corpus.file_count, locale)}
              testId="stat-files"
            />
            <Stat
              label={dictionary.corpus.chunks}
              value={formatNumber(corpus.chunk_count, locale)}
              testId="stat-chunks"
            />
            <Stat
              label={dictionary.corpus.bytes}
              value={formatBytes(corpus.bytes_indexed, locale)}
              testId="stat-bytes"
            />
          </div>

          <CorpusExplorer corpus={corpus} locale={locale} />
        </>
      )}

      <div className="stack">
        <div className="card" data-testid="webhook-health">
          <h2>{dictionary.corpus.webhook.title}</h2>
          <div className="row">
            {corpus.webhook.configured ? (
              corpus.webhook.enabled ? (
                <span className="tag tag-ok">{dictionary.corpus.webhook.configured}</span>
              ) : (
                <span className="tag tag-warn">{dictionary.corpus.webhook.disabledReadonly}</span>
              )
            ) : (
              <span className="tag tag-off">{dictionary.corpus.webhook.notConfigured}</span>
            )}
          </div>
          <dl className="detail" style={{ marginBlockStart: "0.75rem" }}>
            <div>
              <dt>{dictionary.corpus.webhook.deliveries}</dt>
              <dd>{formatNumber(corpus.webhook.deliveries, locale)}</dd>
            </div>
            <div>
              <dt>{dictionary.corpus.webhook.last}</dt>
              <dd>
                {formatWhen(corpus.webhook.last_delivery_at, locale) ?? (
                  <span className="muted">{dictionary.corpus.webhook.none}</span>
                )}
                {corpus.webhook.last_repo ? (
                  <>
                    {" "}
                    <span className="mono small" dir="ltr">
                      {corpus.webhook.last_repo}
                    </span>
                  </>
                ) : null}
              </dd>
            </div>
            <div>
              <dt>{dictionary.corpus.lastRun}</dt>
              <dd>
                {lastRun ? (
                  <>
                    <span className="mono small">{lastRun.trigger}</span> ·{" "}
                    {formatWhen(lastRun.finished_at ?? lastRun.started_at, locale) ?? (
                      <span className="muted">{dictionary.corpus.never}</span>
                    )}{" "}
                    · {formatNumber(lastRun.chunks_written, locale)} {dictionary.units.chunks}
                  </>
                ) : (
                  <span className="muted">{dictionary.corpus.never}</span>
                )}
              </dd>
            </div>
          </dl>
        </div>

        <ReindexPanel locale={locale} target={corpus.owner} readonly={corpus.readonly} />

        <div className="card">
          <h2>{dictionary.corpus.models}</h2>
          <dl className="detail">
            <div>
              <dt>embeddings</dt>
              <dd className="mono small" dir="ltr">
                {corpus.embed_model} · {corpus.embed_dim}d
              </dd>
            </div>
            <div>
              <dt>reranker</dt>
              <dd className="mono small" dir="ltr">
                {corpus.rerank_model ?? <span className="muted">off</span>}
              </dd>
            </div>
            <div>
              <dt>generation</dt>
              <dd className="mono small" dir="ltr">
                {corpus.generation}
              </dd>
            </div>
            <div>
              <dt>service</dt>
              <dd className="mono small" dir="ltr">
                ask-repos {corpus.version}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="stat" data-testid={testId}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
