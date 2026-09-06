import { describe, expect, it } from "vitest";

import { parseFrame, readEvents } from "@/lib/sse";

/** A stream that hands out exactly the chunks given, so the splits are the test. */
function streamOf(chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const queue = chunks.map((chunk) =>
    typeof chunk === "string" ? encoder.encode(chunk) : chunk,
  );
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      const next = queue.shift();
      if (next === undefined) controller.close();
      else controller.enqueue(next);
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>, signal?: AbortSignal) {
  const out = [];
  for await (const frame of readEvents(stream, signal)) out.push(frame);
  return out;
}

const SENTENCE = 'event: sentence\ndata: {"text":"one","kept":true}\n\n';
const DONE = 'event: done\ndata: {"refused":false,"provider":"extractive"}\n\n';

describe("parseFrame", () => {
  it("reads the event name and the JSON payload", () => {
    expect(parseFrame('event: sentence\ndata: {"text":"hi"}')).toEqual({
      event: "sentence",
      data: { text: "hi" },
    });
  });

  it("defaults the event name to `message`", () => {
    expect(parseFrame('data: {"a":1}')).toEqual({ event: "message", data: { a: 1 } });
  });

  it("joins multi-line data as the SSE spec requires", () => {
    expect(parseFrame('event: x\ndata: {"a":\ndata: 1}')).toEqual({ event: "x", data: { a: 1 } });
  });

  it("ignores comment/keep-alive lines and frames with no data", () => {
    expect(parseFrame(": keep-alive")).toBeNull();
    expect(parseFrame("event: ping")).toBeNull();
    expect(parseFrame("")).toBeNull();
  });

  it("skips a frame whose data is not JSON rather than throwing", () => {
    expect(parseFrame("event: x\ndata: not json")).toBeNull();
  });
});

describe("readEvents", () => {
  it("yields each frame in order", async () => {
    const frames = await collect(streamOf([SENTENCE + DONE]));
    expect(frames.map((frame) => frame.event)).toEqual(["sentence", "done"]);
    expect(frames[0].data).toEqual({ text: "one", kept: true });
  });

  it("does not care where the chunk boundaries fall — one byte at a time", async () => {
    const whole = SENTENCE + DONE;
    const frames = await collect(streamOf([...whole]));
    expect(frames.map((frame) => frame.event)).toEqual(["sentence", "done"]);
    expect(frames[1].data).toEqual({ refused: false, provider: "extractive" });
  });

  it("holds a frame whose terminator is split across two chunks", async () => {
    // The classic break: "\n" ends one chunk and "\n" starts the next.
    const frames = await collect(
      streamOf(['event: sentence\ndata: {"text":"one"}\n', '\nevent: done\ndata: {}\n\n']),
    );
    expect(frames.map((frame) => frame.event)).toEqual(["sentence", "done"]);
  });

  it("keeps a multi-byte character that straddles a chunk boundary", async () => {
    // "السالمية" really does come back in these answers.
    const payload = 'event: sentence\ndata: {"text":"السالمية"}\n\n';
    const bytes = new TextEncoder().encode(payload);
    const cut = 24; // lands inside an Arabic code point
    const frames = await collect(streamOf([bytes.slice(0, cut), bytes.slice(cut)]));
    expect(frames).toHaveLength(1);
    expect((frames[0].data as { text: string }).text).toBe("السالمية");
  });

  it("emits a final frame that arrived without a trailing blank line", async () => {
    const frames = await collect(streamOf(['event: done\ndata: {"refused":true}']));
    expect(frames).toEqual([{ event: "done", data: { refused: true } }]);
  });

  it("stops when the signal is aborted, and releases the reader", async () => {
    const controller = new AbortController();
    const stream = streamOf([SENTENCE, DONE]);
    const frames = [];
    for await (const frame of readEvents(stream, controller.signal)) {
      frames.push(frame);
      controller.abort();
    }
    expect(frames.map((f) => f.event)).toEqual(["sentence"]);
    // A released lock is what lets the caller cancel the body.
    expect(() => stream.getReader()).not.toThrow();
  });

  it("survives a keep-alive comment in the middle of the stream", async () => {
    const frames = await collect(streamOf([SENTENCE, ": keep-alive\n\n", DONE]));
    expect(frames.map((frame) => frame.event)).toEqual(["sentence", "done"]);
  });
});
