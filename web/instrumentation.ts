/**
 * OpenTelemetry for the Next.js server.
 *
 * Next calls `register()` once per server process, before any route handler runs, and its
 * own instrumentation emits spans as soon as a tracer provider is registered globally.
 * The SDK is only started when an OTLP endpoint is configured — on Netlify nothing is, so
 * the import never happens and no exporter sits in the request path. Locally,
 * `docker compose --profile tracing up` provides Jaeger and this exports to it, which is
 * what makes one trace span the UI and the API.
 *
 * `traceparent` is sent on every outbound request whether or not this is active
 * (`lib/trace.ts`), so a request is always correlatable even with tracing off.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT?.trim();
  if (!endpoint) return;

  const [{ NodeTracerProvider, BatchSpanProcessor }, { OTLPTraceExporter }, resources, semconv] =
    await Promise.all([
      import("@opentelemetry/sdk-trace-node"),
      import("@opentelemetry/exporter-trace-otlp-http"),
      import("@opentelemetry/resources"),
      import("@opentelemetry/semantic-conventions"),
    ]);

  const url = endpoint.endsWith("/v1/traces")
    ? endpoint
    : `${endpoint.replace(/\/+$/, "")}/v1/traces`;

  const provider = new NodeTracerProvider({
    resource: resources.defaultResource().merge(
      resources.resourceFromAttributes({
        [semconv.ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || "ask-repos-web",
        [semconv.ATTR_SERVICE_VERSION]: process.env.NEXT_PUBLIC_UI_VERSION || "0.2.0",
      }),
    ),
    spanProcessors: [new BatchSpanProcessor(new OTLPTraceExporter({ url }))],
  });
  provider.register();
  console.log(`[otel] ask-repos-web exporting spans to ${url}`);
}
