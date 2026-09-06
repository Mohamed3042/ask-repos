import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      // Build and run artefacts: the Netlify adapter's bundled server, Playwright's
      // report and traces. Linting generated code produces thousands of warnings that
      // train everyone to ignore the linter.
      ".netlify/**",
      "playwright-report/**",
      "test-results/**",
      "blob-report/**",
    ],
  },
];

export default eslintConfig;
