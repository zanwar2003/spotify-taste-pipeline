# Spotify Taste Pipeline

A chatbot that builds a playlist from someone's **public** Spotify profile, plus the data pipeline underneath it. You give it a username, answer a few questions about intent, mood and length, and it builds a playlist from songs the profile already likes and songs similar to them. You can then refine it in conversation and keep every playlist in a personal library.

> **Status: Phase 4 (playlist agent).** The chatbot works end to end: give it a username, answer three questions, get a playlist, refine it in conversation, approve it. Every suggestion is verified against Spotify before it can appear. The gold layer (dbt), library detail and export, and CRM sync are in later phases (see the roadmap).
>
> This is an original portfolio project built on public and synthetic data. It is not affiliated with Spotify.

## Why it looks like a data platform

Spotify removed its Recommendations, Related Artists, and Audio Features endpoints for new apps, so mood and similarity can't come from Spotify alone. That makes a multi-source pipeline necessary rather than decorative:

```
Spotify public playlists ─┐
MusicBrainz / ListenBrainz ├─► BRONZE  raw JSON, immutable, hash-deduplicated
Last.fm similar tracks ────┘      │
                                  ▼
                 SILVER  cleaned, typed, deduped, validated
                 └─ rejects ─► QUARANTINE (with reason codes)
                                  │
                                  ▼
             GOLD  dbt star schema, taste profiles, tests
                       │                     │
                       ▼                     ▼
          Claude playlist agent       CRM sync (HubSpot / Salesforce)
                       │               behind a human approval queue
                       ▼
          Chat UI ─► library ─► Spotify playlist export
```

## What works today

| Area | Detail |
|---|---|
| Auth | Spotify login with Authorization Code + PKCE. Session is a signed, httpOnly cookie. Refresh tokens are encrypted with AES-256-GCM at rest. |
| Data isolation | Postgres row-level security on every user-owned table, enforced for a **non-superuser app role** (superusers silently bypass RLS; this is tested). |
| Library data model | `users`, `playlists`, append-only `playlist_versions`, `playlist_tracks`, `tags`. Deleting a user cascades to everything (tested). |
| Bronze ingestion | Reads a user's public playlists and tracks via Spotify client credentials, follows pagination, honours `Retry-After` on 429, and lands raw pages idempotently by payload hash. |
| Silver: validation | Each raw track is parsed with Pydantic. Bad rows (deleted, local files, podcast episodes, missing IDs, implausible durations) go to `silver.rejected_record` with a reason code instead of failing the run. Fixable problems (a malformed ISRC or timestamp) are kept as warnings. |
| Silver: entity resolution | Many Spotify IDs collapse into one recording. Same ISRC, or same normalized title and artist with matching duration, merges automatically (a "2011 Remaster" is the same song). Live, remix, acoustic and re-recorded versions stay distinct. Near-misses go to a review queue instead of being merged. |
| Silver: quality gate | If more than half the records in a run are rejected, the run aborts without writing, so an upstream API change can't quietly corrupt the layer. Every run is recorded in `silver.run_log`. |
| Agent: generation | A LangGraph graph (`propose → verify → assemble`, with top-up rounds) builds a playlist from the profile's taste (top artists and most-repeated songs from silver) plus your intent, mood and length. Claude proposes songs through forced tool calls with schema-validated output. |
| Agent: verification | Nothing the model says reaches the playlist unchecked. Each suggestion must match a real Spotify search result on title **and** artist, and be the same kind of recording (a live take never stands in for a studio track). Failures are dropped and counted; the unverified rate is stored on every version. |
| Agent: refinement | Feedback like "swap the slow ones" or "same mood as the Entourage soundtrack" becomes an edit plan: removals, additions, and optionally a reference lookup that pulls real tracks from a matching Spotify playlist. Each turn appends an immutable version with a diff. |
| Agent: safety | User feedback, usernames and Spotify text are passed to the model inside escaped `<untrusted_...>` tags. The agent service only accepts calls from the web server (shared secret plus verified user ID), and playlists are written under row-level security. |
| UI | Chat shell with a step tracker, quick-reply chips and a live region for screen readers. Library with search, status filter and sorting. Mobile first. |

Spotify's content policy limits caching, so the app tables and silver store only IDs, ISRCs, normalized match keys, durations and the app's own fields (rationale, tags, feedback). Titles and artwork are re-fetched at display time.

**Known gap:** bronze lands raw API responses verbatim, and quarantined rows keep their raw item for debugging, so a local database does hold Spotify content. Nothing is committed to the repo, but a retention job that expires old bronze rows is planned for the ops phase; until then, treat the local database as disposable.

## Run it locally

Prerequisites: Docker, Node 22, Python 3.11+, and a [Spotify developer app](https://developer.spotify.com/dashboard) with the redirect URI `http://127.0.0.1:3000/api/auth/callback` (Spotify no longer accepts `localhost`).

```bash
cp .env.example .env            # fill in Spotify credentials; generate secrets with `openssl rand -hex 32`
docker compose up -d            # Postgres, schema applied automatically

# web app
cd web && npm install && npm run dev      # http://127.0.0.1:3000

# playlist agent (separate terminal; needs ANTHROPIC_API_KEY and AGENT_INTERNAL_TOKEN in .env)
cd pipeline && python -m tastepipe.agent.api   # 127.0.0.1:8000, called only by the web server

# pipeline
cd pipeline && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
python -m tastepipe.ingest <spotify_username>     # land raw data (bronze)
python -m tastepipe.silver                        # clean, validate, deduplicate (silver)
```

Development-mode Spotify apps only work for users you add to the app's allowlist.

## Tests

```bash
cd pipeline && pytest        # unit tests always run; DB tests need DATABASE_URL and APP_DATABASE_URL
# service tests commit data, so they also need TASTEPIPE_TEST_ALLOW_WRITES=1 (disposable DB only)
cd web && npm run typecheck && npm test && npm run build
```

CI runs both, with a real Postgres, on every push.

## Known limits

- The agent has been tested with a scripted model and an in-memory Spotify, and the UI against a stub agent in a real browser. It has not yet been run against the live Claude and Spotify APIs, so expect to tune prompts and matching thresholds on real data.
- Generation makes dozens of Spotify lookups and can take up to a minute. Development-mode Spotify apps have tight rate limits; the client honours `Retry-After` but a busy app will feel slow.
- Spotify's search behaviour and dev-mode restrictions have changed repeatedly. If a lookup returns nothing, the song is dropped and counted rather than guessed.

## Design principles

The UI follows the [BYU–Hawaii UX and Design Guidelines](https://marcom.byuh.edu/websites/ux-and-design-guidelines): one clear purpose per page, consistent navigation and calls to action, accessibility as a baseline, content first, minimal friction, and mobile first. Pull requests carry a UX checklist based on them.

## Roadmap

1. **Foundation** (done): schema, login, bronze, UI shells
2. **Silver and validation** (done, MusicBrainz enrichment still to come): typed models, ISRC entity resolution, quarantine with reason codes, quality gate
3. **Gold**: dbt star schema and tests, taste-profile models
4. **Agent** (done): LangGraph generation and refinement, every suggestion verified against Spotify Search
5. **Library**: detail and diff views, export to Spotify, drift reconciliation
6. **CRM sync**: HubSpot / Salesforce upserts by external ID behind an approval queue
7. **Ops**: Dagster orchestration, Prometheus and Grafana, optional Delta Lake gold layer
