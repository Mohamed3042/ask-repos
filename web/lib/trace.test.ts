import { describe, expect, it } from "vitest";

import { buildTraceparent, parseTraceparent, traceContextFrom } from "@/lib/trace";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";
const SPAN_ID = "00f067aa0ba902b7";

function fakeSpan(traceId: string, spanId: string) {
  return { spanContext: () => ({ traceId, spanId, traceFlags: 1 }) } as never;
}

describe("traceContextFrom", () => {
  it("forwards the ids of a real active span and marks the request sampled", () => {
    const context = traceContextFrom(fakeSpan(TRACE_ID, SPAN_ID));
    expect(context).toEqual({
      traceId: TRACE_ID,
      spanId: SPAN_ID,
      sampled: true,
      traceparent: `00-${TRACE_ID}-${SPAN_ID}-01`,
    });
  });

  it("still produces a valid header when tracing is off", () => {
    const context = traceContextFrom(undefined);
    expect(context.sampled).toBe(false);
    const parsed = parseTraceparent(context.traceparent);
    expect(parsed).toEqual({ traceId: context.traceId, spanId: context.spanId });
  });

  it("does not forward the all-zero ids a disabled SDK reports", () => {
    const context = traceContextFrom(fakeSpan("0".repeat(32), "0".repeat(16)));
    expect(context.traceId).not.toBe("0".repeat(32));
    expect(context.sampled).toBe(false);
  });

  it("generates a different trace id each time", () => {
    const ids = new Set(Array.from({ length: 20 }, () => traceContextFrom(undefined).traceId));
    expect(ids.size).toBe(20);
  });
});

describe("parseTraceparent", () => {
  it("round-trips what buildTraceparent produced", () => {
    expect(parseTraceparent(buildTraceparent(TRACE_ID, SPAN_ID, true))).toEqual({
      traceId: TRACE_ID,
      spanId: SPAN_ID,
    });
    expect(parseTraceparent(buildTraceparent(TRACE_ID, SPAN_ID, false))).toEqual({
      traceId: TRACE_ID,
      spanId: SPAN_ID,
    });
  });

  it.each([
    ["a future version", `01-${TRACE_ID}-${SPAN_ID}-01`],
    ["a short trace id", `00-${TRACE_ID.slice(1)}-${SPAN_ID}-01`],
    ["an all-zero trace id", `00-${"0".repeat(32)}-${SPAN_ID}-01`],
    ["an all-zero span id", `00-${TRACE_ID}-${"0".repeat(16)}-01`],
    ["nonsense", "not-a-traceparent"],
  ])("rejects %s", (_label, header) => {
    expect(parseTraceparent(header)).toBeNull();
  });
});
