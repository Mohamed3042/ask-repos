#!/usr/bin/env node
/**
 * Show the citation gates RED before anyone is asked to believe they are green.
 *
 * A test that cannot fail is decoration. This script sabotages a *copy* of the source (or
 * of the spec), asserts the sabotage actually applied — a no-op edit reads exactly like a
 * verified fail-first — runs the check, and requires it to fail.
 *
 *   node scripts/prove-fails-first.mjs           # the unit gate (fast, no browser)
 *   node scripts/prove-fails-first.mjs --e2e     # also the Playwright gate (needs the API)
 *
 * The runners are invoked as `node <the tool's own .mjs/.js entry>` rather than through
 * `npx`. On Windows `spawnSync("npx.cmd", …, { shell: false })` fails with EINVAL and
 * returns `status: null` — which this script would otherwise have read as "non-zero, so
 * the gate went red". A harness that reports RED when it never ran is worse than no
 * harness, so `run()` refuses to interpret a spawn failure at all.
 */

import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const VITEST = join(webRoot, "node_modules", "vitest", "vitest.mjs");
const PLAYWRIGHT = join(webRoot, "node_modules", "@playwright", "test", "cli.js");

let failures = 0;

function heading(text) {
  console.log(`\n== ${text} ==`);
}

function sabotage(file, from, to) {
  const source = readFileSync(file, "utf8");
  const occurrences = source.split(from).length - 1;
  if (occurrences !== 1) {
    throw new Error(
      `sabotage target appears ${occurrences} times in ${file}; expected exactly 1. ` +
        "A no-op sabotage reads as a verified fail-first, so this is fatal.",
    );
  }
  writeFileSync(file, source.replace(from, to), "utf8");
  if (!readFileSync(file, "utf8").includes(to)) throw new Error(`sabotage did not apply to ${file}`);
  console.log(`sabotage applied to ${file}\n  ${JSON.stringify(from)} -> ${JSON.stringify(to)}`);
}

function run(entry, args, label) {
  if (!existsSync(entry)) throw new Error(`runner not installed: ${entry}`);
  const result = spawnSync(process.execPath, [entry, ...args], {
    cwd: webRoot,
    encoding: "utf8",
    env: { ...process.env, CI: "1", FORCE_COLOR: "0" },
  });
  if (result.error || result.status === null) {
    // Never let "the runner did not start" be scored as "the gate went red".
    throw new Error(
      `${label} did not run: ${result.error?.code ?? "no exit status"} — the gate was not measured`,
    );
  }
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  if (!output.trim()) throw new Error(`${label} produced no output; refusing to score it`);
  const red = result.status !== 0;
  const line =
    output
      .split("\n")
      .map((candidate) => candidate.trim())
      .find((candidate) => /AssertionError|expected|Error:|✕|×|FAIL/i.test(candidate)) ??
    "(no failing line matched)";
  console.log(`${label}: exit ${result.status} → ${red ? "RED" : "GREEN"}`);
  console.log(`  ${line.slice(0, 220)}`);
  if (!red) failures += 1;
  return red;
}

// -- gate 1: the unit assertion that the chip's href equals the API's URL ------------
{
  heading("unit: blobUrl must equal the URL the API returned");
  const file = join(webRoot, "lib", "citations.ts");
  const backup = `${file}.orig`;
  copyFileSync(file, backup);
  try {
    // The short SHA is what the citation *string* carries; using it in the link is the
    // classic near-miss — the URL still resolves on GitHub, at a different revision.
    sabotage(file, "/blob/${citation.sha}/", "/blob/${citation.sha.slice(0, 7)}/");
    run(VITEST, ["run"], "vitest");
  } finally {
    copyFileSync(backup, file);
    rmSync(backup);
  }
  heading("unit: the same suite, unsabotaged");
  const green = run(VITEST, ["run"], "vitest");
  if (green) {
    console.error("the restored source did not pass; the sabotage was not undone");
    process.exit(1);
  }
  failures -= 1; // this run is expected to be GREEN
}

// -- gate 2: the same assertion, through the browser ---------------------------------
if (process.argv.includes("--e2e")) {
  heading("e2e: the rendered chip href must equal the API citation");
  const spec = join(webRoot, "e2e", "chat.spec.ts");
  const copy = join(webRoot, "e2e", "sabotaged.spec.ts");
  const source = readFileSync(spec, "utf8");
  // Target an assertion that runs for EVERY chip on every provider. The set-equality
  // check against a control API call only runs on the deterministic keyless path, so
  // sabotaging that one would quietly pass on a machine with a working Gemini key —
  // a gate that is only armed sometimes is not a gate.
  const from = "expect(url.hash).toBe(`#L${parsed!.lineStart}-L${parsed!.lineEnd}`);";
  const to = 'expect(url.hash).toBe(`#L${parsed!.lineStart}-L${parsed!.lineEnd}-wrong`);';
  const occurrences = source.split(from).length - 1;
  if (occurrences !== 1) {
    throw new Error(`expected exactly one ${JSON.stringify(from)} in chat.spec.ts, got ${occurrences}`);
  }
  writeFileSync(copy, source.replace(from, to), "utf8");
  console.log(`sabotaged copy written: ${copy}`);
  try {
    run(PLAYWRIGHT, ["test", "sabotaged.spec.ts", "-g", "renders sentences whose chips"], "playwright");
  } finally {
    rmSync(copy, { force: true });
  }
}

if (failures > 0) {
  console.error(`\nFAIL: ${failures} gate(s) stayed green under sabotage.`);
  process.exit(1);
}
console.log("\nALL GATES FAILED FIRST (as required).");
