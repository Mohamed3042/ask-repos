import { NextResponse } from "next/server";

import { apiFetch, safeDetail } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Resolve a run that stopped at the human-approval interrupt.
 *
 * A read-only deployment answers 403 to an approval and 200 to a decline; both are passed
 * through unchanged, because "approval was refused because this deployment is read-only"
 * is exactly what the page should say.
 */
export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "body is not JSON" }, { status: 400 });
  }
  const body = payload as { thread_id?: unknown; approved?: unknown; reason?: unknown };
  if (typeof body.thread_id !== "string" || !body.thread_id) {
    return NextResponse.json({ detail: "thread_id is required" }, { status: 400 });
  }
  const approved = body.approved === true;

  try {
    const { response, trace } = await apiFetch(
      `/v1/ask/${encodeURIComponent(body.thread_id)}/resume`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          approved,
          reason: typeof body.reason === "string" ? body.reason : null,
        }),
        timeoutMs: 180_000,
      },
    );
    const headers = { "x-trace-id": trace.traceId };
    if (!response.ok) {
      return NextResponse.json(
        { detail: await safeDetail(response) },
        { status: response.status, headers },
      );
    }
    return NextResponse.json(await response.json(), { headers });
  } catch {
    return NextResponse.json(
      { detail: "the ask-repos API is unreachable from this deployment" },
      { status: 502 },
    );
  }
}
