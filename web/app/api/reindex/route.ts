import { NextResponse } from "next/server";

import { apiFetch, safeDetail } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Ask the agent to re-index.
 *
 * This deliberately goes through `/v1/ask` rather than `/v1/index`. `/v1/index` just does
 * it; the agent path is the one that stops at a LangGraph `interrupt` and hands the
 * decision to a human, which is the behaviour the Corpus page exists to show. The API's
 * own trigger is a natural-language one (`^re-?index\b`), so that is what is sent.
 */
export async function POST(request: Request) {
  let target = "";
  try {
    const body = (await request.json()) as { target?: unknown };
    if (typeof body.target === "string") target = body.target.trim();
  } catch {
    /* an empty body is fine: the API falls back to its configured owner */
  }
  // Only an owner or owner/repo may be interpolated into the question.
  if (target && !/^[A-Za-z0-9_.-]+(\/[A-Za-z0-9_.-]+)?$/.test(target)) {
    return NextResponse.json({ detail: "target is not a repository name" }, { status: 400 });
  }

  try {
    const { response, trace } = await apiFetch("/v1/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: `reindex ${target}`.trim() }),
      timeoutMs: 60_000,
    });
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
