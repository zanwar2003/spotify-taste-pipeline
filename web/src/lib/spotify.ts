import { createHash, randomBytes } from "node:crypto";
import { requireEnv } from "./env.ts";

const AUTHORIZE_URL = "https://accounts.spotify.com/authorize";
const TOKEN_URL = "https://accounts.spotify.com/api/token";
const ME_URL = "https://api.spotify.com/v1/me";

// Least privilege: create/edit the user's own playlists, nothing else.
export const SCOPES = ["playlist-modify-public", "playlist-modify-private"];

export function newPkcePair(): { verifier: string; challenge: string; state: string } {
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge, state: randomBytes(16).toString("base64url") };
}

export function authorizeUrl(challenge: string, state: string): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: requireEnv("SPOTIFY_CLIENT_ID"),
    redirect_uri: requireEnv("SPOTIFY_REDIRECT_URI"),
    scope: SCOPES.join(" "),
    code_challenge_method: "S256",
    code_challenge: challenge,
    state,
  });
  return `${AUTHORIZE_URL}?${params}`;
}

export type TokenResponse = { access_token: string; refresh_token?: string; expires_in: number };

export async function exchangeCode(code: string, verifier: string): Promise<TokenResponse> {
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: requireEnv("SPOTIFY_REDIRECT_URI"),
      client_id: requireEnv("SPOTIFY_CLIENT_ID"),
      code_verifier: verifier,
    }),
  });
  if (!res.ok) throw new Error(`Spotify token exchange failed (${res.status})`);
  return (await res.json()) as TokenResponse;
}

export async function fetchMe(accessToken: string): Promise<{ id: string; display_name: string | null }> {
  const res = await fetch(ME_URL, { headers: { Authorization: `Bearer ${accessToken}` } });
  if (!res.ok) throw new Error(`Spotify /me failed (${res.status})`);
  return (await res.json()) as { id: string; display_name: string | null };
}
