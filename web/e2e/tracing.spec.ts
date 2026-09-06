import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { askInUi } from "./support";

/**
 * One trace, two services.
 *
 * This is the proof for the cross-service observability claim: a question asked in the
 * browser produces a span in the Next.js route handler, the route handler forwards a W3C
 * `traceparent`, and the FastAPI span for the same question comes back as that span's
 * child. The assertion is on the ids, not on a picture — and then it takes the picture.
 *
 * Needs the Compose tracing profile:
 *
 *   docker compose --profile tracing up -d jaeger
 *   ASK_REPOS_OTEL_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 \
 *     docker compose up -d api
 *   cd web && JAEGER_URL=http://localhost:16686 \
 *     OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 npx playwright test tracing
 */

const JAEGER = process.env.JAEGER_URL;
const PROOF_DIR = join(process.cwd(), "..", "docs", "proof");

interface JaegerSpan {
  spanID: string;
  operationName: string;
  processID: string;
  references: { refType: string; spanID: string; traceID: string }[];
}
interface JaegerTrace {
  traceID: string;
  spans: JaegerSpan[];
  processes: Record<string, { serviceName: string }>;
}

test.describe("cross-service tracing", () => {
  test.skip(!JAEGER, "set JAEGER_URL and run the Compose tracing profile");
  test.setTimeout(240_000);

  test("one trace spans the Next.js route handler and the FastAPI request", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    const streamed = page.waitForResponse(
      (response) => response.url().includes("/api/ask") && response.status() === 200,
    );
    await askInUi(page, "Which Kuwait branches does the Retail Ops Hub demo cover?");
    const traceId = (await streamed).headers()["x-trace-id"];
    expect(traceId, "the route handler echoes the trace id it sent").toMatch(/^[0-9a-f]{32}$/);

    // Both services batch their exports, and Jaeger serves a trace as soon as *any* of it
    // has landed. Waiting for "both services are present" therefore returns a partial
    // trace whose parent links point at spans that have not arrived yet - measured: three
    // API spans all claiming a parent that was not in the response. Poll for the relation
    // being asserted, not for a weaker proxy of it.
    let trace: JaegerTrace | undefined;
    let childOfUi: JaegerSpan | undefined;
    let lastSeen = "nothing yet";
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      const response = await request.get(`${JAEGER}/api/traces/${traceId}`);
      if (response.ok()) {
        const candidate = ((await response.json()) as { data: JaegerTrace[] }).data?.[0];
        if (candidate) {
          const serviceOf = (span: JaegerSpan) => candidate.processes[span.processID].serviceName;
          const uiIds = new Set(
            candidate.spans
              .filter((span) => serviceOf(span) === "ask-repos-web")
              .map((span) => span.spanID),
          );
          const match = candidate.spans
            .filter((span) => serviceOf(span) === "ask-repos")
            .find((span) =>
              span.references.some(
                (reference) =>
                  reference.refType === "CHILD_OF" &&
                  reference.traceID === candidate.traceID &&
                  uiIds.has(reference.spanID),
              ),
            );
          lastSeen = `${candidate.spans.length} spans, ${uiIds.size} from the UI`;
          if (match) {
            trace = candidate;
            childOfUi = match;
            break;
          }
        }
      }
      await page.waitForTimeout(2000);
    }

    expect(
      childOfUi,
      `no ask-repos span in trace ${traceId} is a child of an ask-repos-web span (${lastSeen})`,
    ).toBeTruthy();
    const serviceOf = (span: JaegerSpan) => trace!.processes[span.processID].serviceName;
    const uiSpans = trace!.spans.filter((span) => serviceOf(span) === "ask-repos-web");
    const apiSpans = trace!.spans.filter((span) => serviceOf(span) === "ask-repos");
    expect(uiSpans.length, "UI spans").toBeGreaterThan(0);
    expect(apiSpans.length, "API spans").toBeGreaterThan(0);

    const parentId = childOfUi!.references.find((reference) => reference.refType === "CHILD_OF")!
      .spanID;
    console.log(
      `TRACE ${trace!.traceID}\n` +
        `  ask-repos-web  span ${parentId}  (${uiSpans.find((s) => s.spanID === parentId)?.operationName})\n` +
        `  ask-repos      span ${childOfUi!.spanID}  parent ${parentId}  (${childOfUi!.operationName})`,
    );

    // And the picture, taken from the live Jaeger UI showing that same trace.
    mkdirSync(PROOF_DIR, { recursive: true });
    await page.goto(`${JAEGER}/trace/${trace!.traceID}`);
    await expect(page.getByText("ask-repos-web").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(trace!.traceID.slice(0, 7)).first()).toBeVisible();
    await page.screenshot({
      path: join(PROOF_DIR, "trace-ui-to-api.png"),
      fullPage: false,
    });
  });
});
