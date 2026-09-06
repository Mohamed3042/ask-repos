import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "node",
    // Playwright specs live in e2e/ and are run by `npm run e2e`; picking them up here
    // would launch a browser under vitest and fail in a confusing way.
    include: ["lib/**/*.test.ts", "scripts/**/*.test.mjs"],
  },
});
