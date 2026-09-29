import { NextRequest, NextResponse } from "next/server";
import { sameOrigin } from "./http.ts";
import { getSessionUserId } from "./session.ts";
import { requireEnv } from "./env.ts";

const AGENT_TIMEOUT_MS = 120_000; // generation makes many Spotify lookups

function fail(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status });
}

/**
 * Authenticate the browser session, then forward to the agent service with the shared
 * secret and the verified user ID. The browser never sees the token or talks to the agent.
 */
export async function proxyToAgent(
  req: NextRequest,
  path: string,
  body?: unknown,
): Promise<NextResponse> {
  if (!sameOrigin(req.headers.get("origin"), req.headers.get("host"))) {
    return fail(403, "forbidden", "Request blocked.");
  }
  const userId = await getSessionUserId();
  if (!userId) return fail(401, "signed_out", "Please connect Spotify again.");

  try {
    const res = await fetch(`${process.env.AGENT_URL ?? "http://127.0.0.1:8000"}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": requireEnv("AGENT_INTERNAL_TOKEN"),
        "X-User-Id": userId,
      },
      body: JSON.stringify(body ?? {}),
      signal: AbortSignal.timeout(AGENT_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => null);
    if (data === null) return fail(502, "bad_gateway", "The playlist service sent an unexpected reply.");
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("agent request failed", err);
    return fail(503, "agent_unavailable", "The playlist service isn't available right now. Try again shortly.");
  }
}

export async function readJson(req: NextRequest): Promise<Record<string, unknown> | null> {
  try {
    const body = await req.json();
    return body && typeof body === "object" && !Array.isArray(body) ? body : null;
  } catch {
    return null;
  }
}

export { fail };
