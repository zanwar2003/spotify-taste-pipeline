import { NextResponse } from "next/server";
import { authorizeUrl, newPkcePair } from "@/lib/spotify";

export const dynamic = "force-dynamic";

export async function GET() {
  const { verifier, challenge, state } = newPkcePair();
  const res = NextResponse.redirect(authorizeUrl(challenge, state));
  // Short-lived, httpOnly: holds the PKCE verifier and CSRF state across the redirect.
  res.cookies.set("tp_pkce", JSON.stringify({ verifier, state }), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/api/auth",
    maxAge: 600,
  });
  return res;
}
