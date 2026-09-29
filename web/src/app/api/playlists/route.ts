import { NextRequest } from "next/server";
import { fail, proxyToAgent, readJson } from "@/lib/agent";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const body = await readJson(req);
  if (!body) return fail(400, "invalid_request", "Send the playlist details as JSON.");
  // Only forward the fields the agent expects; it validates their contents.
  const { source_username, intent, mood, target_minutes } = body;
  return proxyToAgent(req, "/playlists", { source_username, intent, mood, target_minutes });
}
