#!/usr/bin/env node
/**
 * Copy the eval report CI gates on into `web/data/eval-report.json`, which is what the
 * /evals page renders.
 *
 * `--check` is the CI half: it compares the committed copy's *gated* numbers against a
 * freshly produced report and fails when they disagree. Timestamps and per-probe answer
 * text are deliberately not compared — those move on every run, and a check that fails
 * for a reason that is not a defect gets switched off within a week.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const repoRoot = resolve(webRoot, "..");
const TARGET = join(webRoot, "data", "eval-report.json");
const SOURCES = [
  join(repoRoot, "evals", "reports-ci", "report.json"),
  join(repoRoot, "evals", "reports", "report.json"),
];

/** The fields a reader would call a result. Everything else is provenance. */
function gated(report) {
  return {
    corpus: {
      repo_count: report.corpus?.repo_count,
      file_count: report.corpus?.file_count,
      chunk_count: report.corpus?.chunk_count,
    },
    retrieval: Object.fromEntries(
      Object.entries(report.retrieval ?? {}).map(([arm, metrics]) => [
        arm,
        {
          "recall@5": Number(metrics["recall@5"].toFixed(3)),
          "MRR@10": Number(metrics["MRR@10"].toFixed(3)),
        },
      ]),
    ),
    answers: {
      citation_validity: report.answers?.citation_validity,
      sentences_without_citation: report.answers?.sentences_without_citation,
      citations_total: report.answers?.citations_total,
      answered: report.answers?.answered,
      refused: report.answers?.refused,
    },
    injection: { probes: report.injection?.probes, complied: report.injection?.complied },
  };
}

function firstExisting(paths) {
  for (const candidate of paths) if (existsSync(candidate)) return candidate;
  return null;
}

// `--source <path>` names the report explicitly. It matters: `evals/reports/` is whatever
// the last local run produced (often the FULL corpus, 6,018 chunks) while `evals/reports-ci/`
// is the 14-repository subset the gate measures. A search order that resolves differently
// on a laptop and on a runner is a check that means two different things.
const explicit = (() => {
  const index = process.argv.indexOf("--source");
  return index === -1 ? null : process.argv[index + 1];
})();
const source = explicit ? resolve(explicit) : firstExisting(SOURCES);
if (explicit && !existsSync(source)) {
  console.error(`no eval report at ${source}`);
  process.exit(1);
}
if (!source) {
  console.error(
    `no eval report found. Looked in:\n  ${SOURCES.join("\n  ")}\n` +
      "Run `ask-repos evals load --source evals/corpus && ask-repos evals run` first.",
  );
  process.exit(1);
}

const fresh = JSON.parse(readFileSync(source, "utf8"));

if (process.argv.includes("--check")) {
  if (!existsSync(TARGET)) {
    console.error(`GATE FAIL: ${TARGET} is missing; run \`npm run sync:evals\``);
    process.exit(1);
  }
  const committed = JSON.parse(readFileSync(TARGET, "utf8"));
  const a = JSON.stringify(gated(committed), null, 1);
  const b = JSON.stringify(gated(fresh), null, 1);
  if (a !== b) {
    console.error("GATE FAIL: the committed eval report does not match the freshly measured one.");
    console.error(`committed (${TARGET}):\n${a}`);
    console.error(`measured  (${source}):\n${b}`);
    console.error("Run `npm run sync:evals` and commit the result.");
    process.exit(1);
  }
  console.log(`EVALS REPORT FRESH: committed numbers match ${source}`);
  process.exit(0);
}

mkdirSync(dirname(TARGET), { recursive: true });
writeFileSync(TARGET, `${JSON.stringify(fresh, null, 2)}\n`, "utf8");
console.log(
  `wrote ${TARGET} from ${source} ` +
    `(${fresh.corpus.chunk_count} chunks, citation validity ${fresh.answers.citation_validity})`,
);
