/**
 * W3C trace context across the UI → API boundary.
 *
 * The point of this file is one screenshot: a single trace in Jaeger whose root span is
 * the Next.js route handler and whose child is the FastAPI request it made. That only
 * happens if the route handler sends a `traceparent` header the API's OpenTelemetry
 * instrumentation recognises.
 *
 * When tracing is switched on, the ids come from the active span, so the header points at
 * a span that really exists. When it is off — the default, and what Netlify runs unless
 * an endpoint is configured — a random-but-valid trace id is still generated, so every
 * request is still correlatable in the API's own logs. Nothing here ever silently drops
 * the header.
 */

import { trace, type Span } from "@opentelemetry/api";

const HEX = "0123456789abcdef";
const INVALID_TRACE_ID = "00000000000000000000000000000000";
const INVALID_SPAN_ID = "0000000000000000";

function randomHex(length: number): string {
  const bytes = new Uint8Array(length / 2);
  crypto.getRandomValues(bytes);
  let out = "";
  for (const byte of bytes) {
    out += HEX[byte >> 4] + HEX[byte & 15];
  }
  return out;
}

export interface TraceContext {
  traceparent: string;
  traceId: string;
  spanId: string;
  /** true when the ids came from a real active span rather than being generated here. */
  sampled: boolean;
}

export function buildTraceparent(traceId: string, spanId: string, sampled: boolean): string {
  return `00-${traceId}-${spanId}-${sampled ? "01" : "00"}`;
}

/**
 * The trace context to forward. `span` is passed in by the caller so this stays testable
 * without a live SDK; in a route handler it is `trace.getActiveSpan()`.
 */
export function traceContextFrom(span: Span | undefined): TraceContext {
  const context = span?.spanContext();
  if (
    context &&
    context.traceId &&
    context.spanId &&
    context.traceId !== INVALID_TRACE_ID &&
    context.spanId !== INVALID_SPAN_ID
  ) {
    return {
      traceparent: buildTraceparent(context.traceId, context.spanId, true),
      traceId: context.traceId,
      spanId: context.spanId,
      sampled: true,
    };
  }
  const traceId = randomHex(32);
  const spanId = randomHex(16);
  return { traceparent: buildTraceparent(traceId, spanId, false), traceId, spanId, sampled: false };
}

export function currentTraceContext(): TraceContext {
  return traceContextFrom(trace.getActiveSpan());
}

const TRACEPARENT_RE = /^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/;

/** Parse a `traceparent` header. Used by the tests and by the trace-proof script. */
export function parseTraceparent(header: string): { traceId: string; spanId: string } | null {
  const match = TRACEPARENT_RE.exec(header.trim().toLowerCase());
  if (!match) return null;
  const [, traceId, spanId] = match;
  if (traceId === INVALID_TRACE_ID || spanId === INVALID_SPAN_ID) return null;
  return { traceId, spanId };
}
