import { cookies } from "next/headers";

import report from "@/data/eval-report.json";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  dictionaryFor,
  formatNumber,
  formatWhen,
  isLocale,
} from "@/lib/i18n";
import type { EvalReport } from "@/lib/types";

export const metadata = { title: "Evaluations — ask-repos" };

const REPORT = report as unknown as EvalReport;

/**
 * The evals page renders a **committed** report — `web/data/eval-report.json`, copied
 * from the run CI gates on by `npm run sync:evals` and checked by the `evals-report-fresh`
 * CI job. It is not fetched from the API, because the API does not serve its eval history
 * and a page that invented one would be worse than a page that says where its numbers
 * came from. The report's own `generated_at`, provider and corpus counts are printed at
 * the top for exactly that reason.
 */
export default async function EvalsPage() {
  const store = await cookies();
  const raw = store.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  const dictionary = dictionaryFor(locale);

  if (!REPORT?.answers) {
    return (
      <>
        <h1>{dictionary.evals.title}</h1>
        <div className="empty" data-testid="evals-empty">
          <h2>{dictionary.evals.emptyTitle}</h2>
          <p style={{ marginInline: "auto" }}>{dictionary.evals.emptyBody}</p>
        </div>
      </>
    );
  }

  const { answers, injection, retrieval, corpus } = REPORT;
  const validityPercent = (answers.citation_validity * 100).toFixed(1);

  return (
    <>
      <div>
        <h1>{dictionary.evals.title}</h1>
        <p className="lede">{dictionary.evals.lede}</p>
        <p className="small muted" data-testid="evals-source">
          {dictionary.evals.source(
            formatWhen(REPORT.generated_at, locale) ?? REPORT.generated_at,
            REPORT.provider,
          )}{" "}
          {dictionary.evals.corpusLine(corpus.repo_count, corpus.file_count, corpus.chunk_count)}
        </p>
      </div>

      <section aria-label={dictionary.evals.gates}>
        <h2>{dictionary.evals.gates}</h2>
        <div className="stats" data-testid="evals-gates">
          <Gate
            label={dictionary.evals.citationValidity}
            value={`${validityPercent}%`}
            detail={`${formatNumber(answers.citations_valid, locale)} / ${formatNumber(
              answers.citations_total,
              locale,
            )}`}
            good={answers.citation_validity >= 1}
            testId="gate-citation-validity"
          />
          <Gate
            label={dictionary.evals.uncited}
            value={formatNumber(answers.sentences_without_citation, locale)}
            good={answers.sentences_without_citation === 0}
            testId="gate-uncited"
          />
          <Gate
            label={dictionary.evals.injection}
            value={`${formatNumber(injection.complied, locale)} / ${formatNumber(
              injection.probes,
              locale,
            )}`}
            good={injection.complied === 0}
            testId="gate-injection"
          />
          <Gate
            label={dictionary.evals.refusalErrors}
            value={formatNumber(answers.refusal_errors, locale)}
            detail={`${formatNumber(answers.answered, locale)} ${dictionary.evals.answered} · ${formatNumber(
              answers.refused,
              locale,
            )} ${dictionary.evals.refused}`}
            good={answers.refusal_errors === 0}
            testId="gate-refusal-errors"
          />
        </div>
      </section>

      <section className="panel" aria-label={dictionary.evals.retrieval}>
        <div className="panel-head">
          <h2>{dictionary.evals.retrieval}</h2>
          <span className="small muted">
            {formatNumber(answers.answerable, locale)} {dictionary.evals.questions.toLowerCase()}
          </span>
        </div>
        <div className="table-scroll">
          <table data-testid="retrieval-table">
            <thead>
              <tr>
                <th scope="col">{dictionary.evals.arm}</th>
                <th scope="col" className="num">
                  {dictionary.evals.recall}
                </th>
                <th scope="col" style={{ inlineSize: "35%" }}>
                  <span className="sr-only-label">{dictionary.evals.recall}</span>
                </th>
                <th scope="col" className="num">
                  {dictionary.evals.mrr}
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(retrieval).map(([arm, metrics]) => (
                <tr key={arm} data-arm={arm}>
                  <th scope="row" style={{ fontWeight: 500 }}>
                    {arm}
                  </th>
                  <td className="num" data-recall={metrics["recall@5"].toFixed(3)}>
                    {metrics["recall@5"].toFixed(3)}
                  </td>
                  <td>
                    <div
                      className="bar"
                      style={{ ["--pct" as string]: `${(metrics["recall@5"] * 100).toFixed(1)}%` }}
                      role="img"
                      aria-label={`${dictionary.evals.recall} ${metrics["recall@5"].toFixed(3)}`}
                    />
                  </td>
                  <td className="num">{metrics["MRR@10"].toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label={dictionary.evals.redTeam}>
        <h2>{dictionary.evals.redTeam}</h2>
        <p className="lede small">{dictionary.evals.redTeamBody}</p>
        <div className="stack" data-testid="injection-cases" style={{ gap: "0.5rem" }}>
          {injection.cases.map((probe) => (
            <details className="probe" key={probe.id}>
              <summary>
                <span className={`tag ${probe.complied ? "tag-warn" : "tag-ok"}`}>
                  {probe.complied ? dictionary.evals.complied : dictionary.evals.notComplied}
                </span>
                <span className="mono small" dir="ltr">
                  {probe.id}
                </span>
                <span className="small muted">{probe.question}</span>
                {probe.refused ? (
                  <span className="tag tag-off">{dictionary.evals.refused}</span>
                ) : null}
              </summary>
              <p className="small muted" style={{ marginBlock: "0.6rem 0.3rem" }}>
                {dictionary.evals.probeAnswer}
              </p>
              <pre dir="ltr">{probe.answer}</pre>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

function Gate({
  label,
  value,
  detail,
  good,
  testId,
}: {
  label: string;
  value: string;
  detail?: string;
  good: boolean;
  testId: string;
}) {
  return (
    <div className="stat" data-testid={testId} data-good={good}>
      <div className="value" style={{ color: good ? "var(--accent)" : "var(--danger)" }}>
        {value}
      </div>
      <div className="label">{label}</div>
      {detail ? (
        <div className="label mono" style={{ opacity: 0.8 }}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}
