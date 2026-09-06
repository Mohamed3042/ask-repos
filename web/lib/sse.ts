/**
 * Reading server-sent events off a `fetch` body.
 *
 * `EventSource` cannot POST, so the question would have to go in a query string; the
 * stream is read by hand instead. The one thing that matters here is that frames are
 * split on the blank line that terminates them and **not** on chunk boundaries: a network
 * chunk can end anywhere, including in the middle of a JSON payload or between the two
 * newlines of a terminator. The buffer is therefore carried across reads, and a partial
 * frame simply waits.
 *
 * Extracted from the chat component so `lib/sse.test.ts` can feed it deliberately
 * hostile chunkings — one byte at a time, a split inside a UTF-8 character, a terminator
 * split down the middle — without a browser.
 */

export interface SseFrame {
  event: string;
  data: unknown;
}

const FRAME_SEPARATOR = "\n\n";

/** Parse one complete frame's text. Returns null for a frame carrying no data. */
export function parseFrame(frame: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // a comment / keep-alive
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    // A frame that is not JSON is not ours. Skipping it is better than killing the
    // stream: a proxy's keep-alive should not end an answer.
    return null;
  }
}

/**
 * Yield frames from a byte stream. `signal` stops the loop between reads; the reader lock
 * is always released, so an aborted request cannot leave the body locked.
 */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!signal?.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      // `stream: true` keeps a multi-byte character split across chunks intact.
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf(FRAME_SEPARATOR);
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + FRAME_SEPARATOR.length);
        boundary = buffer.indexOf(FRAME_SEPARATOR);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
      }
    }
    // A stream that ends without a trailing blank line still owes us its last frame.
    buffer += decoder.decode();
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
