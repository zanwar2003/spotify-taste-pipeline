-- Phase 1 schema: app tables (row-level security) + bronze landing zone.
-- Spotify content policy: we store IDs/URIs/ISRCs and our own fields only.
-- Titles, artwork, etc. are re-fetched from Spotify at display time.

CREATE SCHEMA IF NOT EXISTS bronze;

-- ---------------------------------------------------------------- app tables

CREATE TABLE users (
    id                  text PRIMARY KEY,               -- Spotify user ID
    display_name        text,
    refresh_token_enc   text,                           -- AES-256-GCM, base64
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE playlist_status AS ENUM ('draft', 'approved', 'exported', 'archived');

CREATE TABLE playlists (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title               text NOT NULL,
    intent              text,
    mood                text,
    target_length_min   integer CHECK (target_length_min > 0),
    source_profile_id   text,                           -- Spotify username the taste came from
    status              playlist_status NOT NULL DEFAULT 'draft',
    is_favorite         boolean NOT NULL DEFAULT false,
    spotify_playlist_id text,                           -- NULL until exported
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX playlists_owner_created_idx ON playlists (owner_id, created_at DESC);
CREATE UNIQUE INDEX playlists_owner_spotify_uq
    ON playlists (owner_id, spotify_playlist_id) WHERE spotify_playlist_id IS NOT NULL;

-- Append-only: one row per approve/refine turn. Current state = latest version.
CREATE TABLE playlist_versions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    playlist_id         uuid NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    owner_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    version_no          integer NOT NULL CHECK (version_no > 0),
    feedback_text       text,                           -- user message that triggered this version
    diff                jsonb NOT NULL DEFAULT '{"added": [], "removed": []}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (playlist_id, version_no)
);

CREATE TABLE playlist_tracks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id          uuid NOT NULL REFERENCES playlist_versions (id) ON DELETE CASCADE,
    owner_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position            integer NOT NULL CHECK (position >= 0),
    spotify_track_id    text NOT NULL,
    isrc                text,
    rationale           text,                           -- the "why this song" line
    UNIQUE (version_id, position)
);

CREATE TABLE tags (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name                text NOT NULL,
    UNIQUE (owner_id, name)
);

CREATE TABLE playlist_tags (
    playlist_id         uuid NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    tag_id              uuid NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    owner_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (playlist_id, tag_id)
);

-- ------------------------------------------------------- row-level security
-- The app sets `SELECT set_config('app.user_id', <spotify id>, true)` at the start
-- of every transaction. FORCE applies policies to the table owner as well.

ALTER TABLE users             ENABLE ROW LEVEL SECURITY; ALTER TABLE users             FORCE ROW LEVEL SECURITY;
ALTER TABLE playlists         ENABLE ROW LEVEL SECURITY; ALTER TABLE playlists         FORCE ROW LEVEL SECURITY;
ALTER TABLE playlist_versions ENABLE ROW LEVEL SECURITY; ALTER TABLE playlist_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE playlist_tracks   ENABLE ROW LEVEL SECURITY; ALTER TABLE playlist_tracks   FORCE ROW LEVEL SECURITY;
ALTER TABLE tags              ENABLE ROW LEVEL SECURITY; ALTER TABLE tags              FORCE ROW LEVEL SECURITY;
ALTER TABLE playlist_tags     ENABLE ROW LEVEL SECURITY; ALTER TABLE playlist_tags     FORCE ROW LEVEL SECURITY;

CREATE POLICY users_self ON users
    USING (id = current_setting('app.user_id', true))
    WITH CHECK (id = current_setting('app.user_id', true));

CREATE POLICY playlists_owner ON playlists
    USING (owner_id = current_setting('app.user_id', true))
    WITH CHECK (owner_id = current_setting('app.user_id', true));

CREATE POLICY playlist_versions_owner ON playlist_versions
    USING (owner_id = current_setting('app.user_id', true))
    WITH CHECK (owner_id = current_setting('app.user_id', true));

CREATE POLICY playlist_tracks_owner ON playlist_tracks
    USING (owner_id = current_setting('app.user_id', true))
    WITH CHECK (owner_id = current_setting('app.user_id', true));

CREATE POLICY tags_owner ON tags
    USING (owner_id = current_setting('app.user_id', true))
    WITH CHECK (owner_id = current_setting('app.user_id', true));

CREATE POLICY playlist_tags_owner ON playlist_tags
    USING (owner_id = current_setting('app.user_id', true))
    WITH CHECK (owner_id = current_setting('app.user_id', true));

-- ------------------------------------------------------------------- bronze
-- Immutable landing zone for raw API responses. Re-ingesting an unchanged
-- payload is a no-op (unique on source + request_key + payload hash).

CREATE TABLE bronze.raw_api_response (
    id              bigserial PRIMARY KEY,
    source          text        NOT NULL,               -- 'spotify', later 'musicbrainz', 'lastfm'
    endpoint        text        NOT NULL,               -- e.g. 'users/{id}/playlists'
    request_key     text        NOT NULL,               -- stable key for the request, e.g. 'user:alice'
    http_status     integer     NOT NULL,
    payload         jsonb       NOT NULL,
    payload_sha256  text        NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, request_key, payload_sha256)
);
CREATE INDEX bronze_raw_lookup_idx ON bronze.raw_api_response (source, request_key, fetched_at DESC);

-- ---------------------------------------------------------------- app role
-- The web app connects as this role. It must NOT be a superuser or have
-- BYPASSRLS, otherwise the row-level security policies above are ignored.
-- (Local dev password only; set a real one via your secrets manager elsewhere.)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tastepipe_app') THEN
        CREATE ROLE tastepipe_app LOGIN PASSWORD 'tastepipe_app' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO tastepipe_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    users, playlists, playlist_versions, playlist_tracks, tags, playlist_tags
    TO tastepipe_app;
