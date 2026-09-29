/** Small, pure helpers shared by the API routes. Kept dependency-free so they can be unit tested. */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

/**
 * CSRF defence for cookie-authenticated POSTs. Browsers always send Origin on cross-site
 * POSTs, so require its host (and port) to equal the Host the request was sent to.
 * Comparing against Host rather than Next's own idea of its URL matters: Next reports
 * "localhost" even when the app is reached at 127.0.0.1, which is the address Spotify
 * login requires. A missing, opaque ("null") or malformed Origin is refused.
 */
export function sameOrigin(originHeader: string | null, hostHeader: string | null): boolean {
  if (!originHeader || !hostHeader) return false;
  try {
    const origin = new URL(originHeader);
    return (origin.protocol === "http:" || origin.protocol === "https:") && origin.host === hostHeader;
  } catch {
    return false;
  }
}

/** Turn "45", "1.5 hours", "90 min" into whole minutes (1-480), or null if unusable. */
export function parseMinutes(input: string): number | null {
  const m = /^\s*(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?\s*$/i.exec(input);
  if (!m) return null;
  const unit = (m[2] ?? "m").toLowerCase();
  const minutes = Math.round(parseFloat(m[1]) * (unit.startsWith("h") ? 60 : 1));
  return minutes >= 1 && minutes <= 480 ? minutes : null;
}
