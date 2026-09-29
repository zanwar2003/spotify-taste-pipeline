import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { requireEnv } from "./env.ts";

export const SESSION_COOKIE = "tp_session";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 14;

export function sign(payload: object, secret: string): string {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const mac = createHmac("sha256", secret).update(body).digest("base64url");
  return `${body}.${mac}`;
}

export function verify<T>(token: string, secret: string): T | null {
  const [body, mac] = token.split(".");
  if (!body || !mac) return null;
  const expected = createHmac("sha256", secret).update(body).digest();
  const given = Buffer.from(mac, "base64url");
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;
  try {
    return JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as T;
  } catch {
    return null;
  }
}

type SessionPayload = { uid: string; exp: number };

export async function setSession(userId: string): Promise<void> {
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_SECONDS;
  const jar = await cookies();
  jar.set(SESSION_COOKIE, sign({ uid: userId, exp }, requireEnv("SESSION_SECRET")), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

/** Returns the signed-in Spotify user ID, or null. */
export async function getSessionUserId(): Promise<string | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const payload = verify<SessionPayload>(token, requireEnv("SESSION_SECRET"));
  if (!payload || payload.exp < Date.now() / 1000) return null;
  return payload.uid;
}
