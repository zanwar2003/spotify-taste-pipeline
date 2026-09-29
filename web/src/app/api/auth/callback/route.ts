import { NextRequest, NextResponse } from "next/server";
import { encrypt } from "@/lib/crypto";
import { withUser } from "@/lib/db";
import { setSession } from "@/lib/session";
import { exchangeCode, fetchMe } from "@/lib/spotify";

export const dynamic = "force-dynamic";

function fail(req: NextRequest, reason: string) {
  const url = new URL("/", req.url);
  url.searchParams.set("error", reason);
  const res = NextResponse.redirect(url);
  res.cookies.delete("tp_pkce");
  return res;
}

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  if (params.get("error")) return fail(req, "denied");

  const code = params.get("code");
  const state = params.get("state");
  let pkce: { verifier: string; state: string } | null = null;
  try {
    pkce = JSON.parse(req.cookies.get("tp_pkce")?.value ?? "null");
  } catch {
    pkce = null;
  }
  if (!code || !state || !pkce || pkce.state !== state) return fail(req, "state");

  try {
    const tokens = await exchangeCode(code, pkce.verifier);
    const me = await fetchMe(tokens.access_token);

    await withUser(me.id, async (db) => {
      await db.query(
        `INSERT INTO users (id, display_name, refresh_token_enc)
         VALUES ($1, $2, $3)
         ON CONFLICT (id) DO UPDATE
           SET display_name = EXCLUDED.display_name,
               refresh_token_enc = COALESCE(EXCLUDED.refresh_token_enc, users.refresh_token_enc),
               updated_at = now()`,
        [me.id, me.display_name, tokens.refresh_token ? encrypt(tokens.refresh_token) : null],
      );
    });

    await setSession(me.id);
    const res = NextResponse.redirect(new URL("/build", req.url));
    res.cookies.delete("tp_pkce");
    return res;
  } catch (err) {
    console.error("auth callback failed", err);
    return fail(req, "server");
  }
}
