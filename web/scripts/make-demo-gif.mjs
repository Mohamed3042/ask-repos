#!/usr/bin/env node
/**
 * Turn the Playwright recording of `e2e/demo.spec.ts` into `docs/proof/demo.gif`.
 *
 *   DEMO=1 E2E_VIDEO=1 npx playwright test demo
 *   node scripts/make-demo-gif.mjs
 *
 * Two-pass palette (`palettegen` / `paletteuse`) because a 256-colour GIF of a mostly-text
 * page dithers badly without one. The script refuses to write a file over the size cap
 * rather than committing an 18 MB GIF nobody can load, and it prints the size it produced.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const RESULTS = join(webRoot, "test-results");
const OUT_DIR = join(webRoot, "..", "docs", "proof");
const OUT = join(OUT_DIR, "demo.gif");
const MAX_BYTES = 8 * 1024 * 1024;

function newestVideo(root) {
  if (!existsSync(root)) return null;
  const found = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".webm")) found.push({ path, at: statSync(path).mtimeMs });
    }
  };
  walk(root);
  if (!found.length) return null;
  found.sort((a, b) => b.at - a.at);
  return found[0].path;
}

const video = newestVideo(RESULTS);
if (!video) {
  console.error(
    `no .webm under ${RESULTS}. Record one first:\n` +
      "  DEMO=1 E2E_VIDEO=1 npx playwright test demo",
  );
  process.exit(1);
}
console.log(`source: ${video} (${(statSync(video).size / 1e6).toFixed(1)} MB)`);

mkdirSync(OUT_DIR, { recursive: true });
const palette = join(webRoot, "test-results", "palette.png");
const fps = Number(process.env.DEMO_FPS ?? 10);
const width = Number(process.env.DEMO_WIDTH ?? 960);
const filters = `fps=${fps},scale=${width}:-1:flags=lanczos`;

function ffmpeg(args, label) {
  const result = spawnSync("ffmpeg", args, { encoding: "utf8" });
  if (result.error || result.status !== 0) {
    console.error(`${label} failed: ${result.error?.message ?? result.stderr?.slice(-800)}`);
    process.exit(1);
  }
}

ffmpeg(["-y", "-i", video, "-vf", `${filters},palettegen=stats_mode=diff`, palette], "palettegen");
ffmpeg(
  [
    "-y",
    "-i",
    video,
    "-i",
    palette,
    "-lavfi",
    `${filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3`,
    "-loop",
    "0",
    OUT,
  ],
  "paletteuse",
);
rmSync(palette, { force: true });

const bytes = statSync(OUT).size;
console.log(`wrote ${OUT} — ${(bytes / 1e6).toFixed(2)} MB at ${fps} fps, ${width}px wide`);
if (bytes > MAX_BYTES) {
  rmSync(OUT, { force: true });
  console.error(
    `that is over the ${MAX_BYTES / 1e6} MB cap and has been deleted. ` +
      "Re-run with a smaller DEMO_FPS or DEMO_WIDTH.",
  );
  process.exit(1);
}
