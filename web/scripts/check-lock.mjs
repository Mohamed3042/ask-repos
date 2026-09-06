#!/usr/bin/env node
/**
 * Fail here rather than three minutes into CI.
 *
 * npm records only the optional platform packages it actually resolved. A
 * `package-lock.json` regenerated on Windows therefore omits the Linux-only optional
 * dependencies of `sharp` (which Next pulls in for image optimisation), and `npm ci` on an
 * Ubuntu runner then refuses the whole install with:
 *
 *   npm error `npm ci` can only install packages when your package.json and
 *   package-lock.json ... are in sync.
 *   npm error Missing: @emnapi/runtime@x.y.z from lock file
 *
 * That happened twice in one session — once for the initial lock, once after adding a
 * single dev dependency on Windows — which is exactly the shape of thing that needs a
 * check rather than a note in a README.
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LOCK = join(webRoot, "package-lock.json");

// Present only when the lock was resolved on Linux. Nested copies under
// `@unrs/resolver-binding-wasm32-wasi` do NOT count — those survive a Windows install and
// made the first version of this check pass on a lock that CI rejected.
const REQUIRED = ["node_modules/@emnapi/core", "node_modules/@emnapi/runtime"];

const lock = JSON.parse(readFileSync(LOCK, "utf8"));
const missing = REQUIRED.filter((name) => !(name in lock.packages));

if (missing.length) {
  console.error(
    `GATE FAIL: package-lock.json is missing ${missing.join(", ")}.\n` +
      "It was almost certainly regenerated on Windows or macOS. `npm ci` on the Linux\n" +
      "runner will refuse it. Regenerate it in a Linux container:\n\n" +
      '  docker run --rm -v "$PWD:/app" -w /app node:22-slim npm install --package-lock-only\n\n' +
      "On Git Bash prefix that with MSYS_NO_PATHCONV=1, or /app becomes\n" +
      "C:/Program Files/Git/app.",
  );
  process.exit(1);
}

console.log(`LOCK OK: ${REQUIRED.length} Linux-only optional packages present in the lock file`);
