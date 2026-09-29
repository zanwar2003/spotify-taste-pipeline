# Free deployment

Web app on Vercel, Postgres on Neon, playlist agent on Render. No credit card needed for any of them.

| Piece | Service | Free-tier caveat |
|---|---|---|
| Web (Next.js) | Vercel Hobby | Personal, non-commercial use only |
| Database | Neon Free | 0.5 GB, sleeps after 5 idle minutes (first query wakes it) |
| Agent (FastAPI) | Render Free web service | Sleeps after 15 idle minutes; waking takes about a minute |

Spotify development-mode apps allow at most five allowlisted test users, so this is a portfolio demo, not a public product.

## 1. Database (Neon)
1. Create a Neon project. Copy two connection strings: **direct** (owner) and **pooled**.
2. Apply the schema (the script also sets a random password on the app role):
   ```bash
   NEON_DIRECT_URL='<direct owner string>' ./scripts/setup_neon.sh
   ```
   The migration creates `tastepipe_app` with a default password; the script replaces it and prints the new one.
3. Build the app-role URL: the pooled string with user `tastepipe_app` and the new password.

## 2. Agent (Render)
1. New > Blueprint > pick this repo (it reads `render.yaml`).
2. Set the secrets: `DATABASE_URL` (Neon direct, owner), `APP_DATABASE_URL` (app role), `AGENT_INTERNAL_TOKEN` (`openssl rand -hex 32`), `GROQ_API_KEY` (free key from console.groq.com; `LLM_PROVIDER=groq` is preset in the blueprint), `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`.
3. Note the service URL, for example `https://tastepipe-agent.onrender.com`.

## 3. Web (Vercel)
1. Import the repo, set **Root Directory** to `web`.
2. Environment variables: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI=https://<your-app>.vercel.app/api/auth/callback`, `APP_DATABASE_URL`, `SESSION_SECRET` and `TOKEN_ENCRYPTION_KEY` (each `openssl rand -hex 32`), `AGENT_URL` (the Render URL), `AGENT_INTERNAL_TOKEN` (same value as Render).
3. Deploy.

## 4. Spotify dashboard
Add `https://<your-app>.vercel.app/api/auth/callback` as a redirect URI, and add each tester's Spotify email under User Management.

## Notes
- To use Claude instead, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. Gemini and OpenRouter work too (`LLM_PROVIDER=gemini` with `GEMINI_API_KEY`, and so on).
- Free models suggest fewer real songs than Claude; the Spotify check drops the rest, so drafts may come back shorter.
- The first request after idle is slow (Render wake plus Neon wake). Open `https://<agent>/healthz` first to warm it.
- Generation can take about a minute; the web route allows up to 120 s.
- Rotate any key that was ever pasted somewhere public.
