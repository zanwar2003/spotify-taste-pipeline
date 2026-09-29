# Spotify Taste Pipeline

A chatbot that builds a playlist from someone's **public** Spotify profile, plus the data pipeline underneath it. You give it a username, answer a few questions about intent, mood and length, and it builds a playlist from songs the profile already likes and songs similar to them. You can then refine it in conversation and keep every playlist in a personal library.

> **Status: Phase 1 (foundation).** Schema, Spotify login, bronze ingestion, and the chat and library shells are in place. Playlist generation, validation, dbt models, and CRM sync are in later phases (see the roadmap).
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
| UI | Chat shell with a step tracker, quick-reply chips and a live region for screen readers. Library with search, status filter and sorting. Mobile first. |

Spotify's content policy limits caching, so the app stores only track IDs, ISRCs and its own fields (rationale, tags, feedback). Titles and artwork are re-fetched at display time.

## Run it locally

Prerequisites: Docker, Node 22, Python 3.11+, and a [Spotify developer app](https://developer.spotify.com/dashboard) with the redirect URI `http://127.0.0.1:3000/api/auth/callback` (Spotify no longer accepts `localhost`).

```bash
cp .env.example .env            # fill in Spotify credentials; generate secrets with `openssl rand -hex 32`
docker compose up -d            # Postgres, schema applied automatically

# web app
cd web && npm install && npm run dev      # http://127.0.0.1:3000

# pipeline
cd pipeline && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
python -m tastepipe.ingest <spotify_username>
```

Development-mode Spotify apps only work for users you add to the app's allowlist.

## Tests

```bash
cd pipeline && pytest        # DB tests run when DATABASE_URL and APP_DATABASE_URL are set
cd web && npm run typecheck && npm test && npm run build
```

CI runs both, with a real Postgres, on every push.

## Design principles

The UI follows the [BYU–Hawaii UX and Design Guidelines](https://marcom.byuh.edu/websites/ux-and-design-guidelines): one clear purpose per page, consistent navigation and calls to action, accessibility as a baseline, content first, minimal friction, and mobile first. Pull requests carry a UX checklist based on them.

## Roadmap

1. **Foundation** (this phase): schema, login, bronze, UI shells
2. **Silver and validation**: typed models, ISRC / MusicBrainz entity resolution, quarantine table with reason codes
3. **Gold**: dbt star schema and tests, taste-profile models
4. **Agent**: LangGraph playlist generation and refinement, every suggestion verified against Spotify Search
5. **Library**: detail and diff views, export to Spotify, drift reconciliation
6. **CRM sync**: HubSpot / Salesforce upserts by external ID behind an approval queue
7. **Ops**: Dagster orchestration, Prometheus and Grafana, optional Delta Lake gold layer
