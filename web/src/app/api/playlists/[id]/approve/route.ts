import { NextRequest } from "next/server";
import { fail, proxyToAgent } from "@/lib/agent";
import { isUuid } from "@/lib/http";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return fail(404, "playlist_not_found", "That playlist doesn't exist.");
  return proxyToAgent(req, `/playlists/${id}/approve`);
}
