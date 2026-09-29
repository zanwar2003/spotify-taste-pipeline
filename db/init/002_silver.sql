-- Phase 2: silver layer (cleaned, typed, deduplicated) and quarantine.
-- Only normalized keys, IDs and durations are kept; display titles/artwork are
-- re-fetched from Spotify when needed (Spotify content policy).

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE silver.playlist (
    spotify_playlist_id text PRIMARY KEY,
    owner_spotify_id    text,
    is_public           boolean,
    track_total         integer CHECK (track_total >= 0),
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now()
);

-- One row per real-world recording, however many Spotify IDs point at it.
CREATE TABLE silver.track (
    canonical_key       text PRIMARY KEY,               -- 'isrc:<ISRC>' or 'nk:<sha1 of name key>'
    isrc                text CHECK (isrc ~ '^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'),
    title_norm          text NOT NULL,
    artist_norm         text NOT NULL,
    version_tag         text NOT NULL DEFAULT '',       -- 'live', 'remix', ... '' = original studio cut
    duration_ms         integer NOT NULL CHECK (duration_ms > 0),
    explicit            boolean,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX silver_track_artist_idx ON silver.track (artist_norm);

-- Every Spotify track ID we have seen -> the recording it resolves to.
CREATE TABLE silver.track_alias (
    spotify_track_id    text PRIMARY KEY CHECK (spotify_track_id ~ '^[0-9A-Za-z]{22}$'),
    canonical_key       text NOT NULL REFERENCES silver.track (canonical_key) ON DELETE CASCADE,
    match_reason        text NOT NULL CHECK (match_reason IN ('canonical', 'same_isrc', 'normalized_match'))
);
CREATE INDEX silver_alias_canonical_idx ON silver.track_alias (canonical_key);

CREATE TABLE silver.playlist_track (
    spotify_playlist_id text NOT NULL REFERENCES silver.playlist (spotify_playlist_id) ON DELETE CASCADE,
    position            integer NOT NULL CHECK (position >= 0),
    spotify_track_id    text NOT NULL REFERENCES silver.track_alias (spotify_track_id),
    added_at            timestamptz,
    PRIMARY KEY (spotify_playlist_id, position)
);

-- Near-matches we are not confident enough to merge automatically.
CREATE TABLE silver.review_queue (
    key_a               text NOT NULL REFERENCES silver.track (canonical_key) ON DELETE CASCADE,
    key_b               text NOT NULL REFERENCES silver.track (canonical_key) ON DELETE CASCADE,
    score               numeric(4, 3) NOT NULL,
    reason              text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key_a, key_b),
    CHECK (key_a <> key_b)  -- pairs are stored ordered by the pipeline; not collation-dependent
);

-- Quarantine: rows that failed validation, kept with the reason instead of failing the run.
-- severity 'error'   = row excluded from silver
-- severity 'warning' = row kept, one field was dropped or repaired
CREATE TABLE silver.rejected_record (
    id                  bigserial PRIMARY KEY,
    bronze_id           bigint NOT NULL REFERENCES bronze.raw_api_response (id),
    item_index          integer NOT NULL,
    entity              text NOT NULL CHECK (entity IN ('track', 'playlist')),
    reason_code         text NOT NULL,
    severity            text NOT NULL CHECK (severity IN ('error', 'warning')),
    detail              text,
    raw                 jsonb,
    rejected_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bronze_id, item_index, reason_code)
);
CREATE INDEX silver_rejected_reason_idx ON silver.rejected_record (reason_code, severity);

CREATE TABLE silver.run_log (
    id                  bigserial PRIMARY KEY,
    started_at          timestamptz NOT NULL DEFAULT now(),
    status              text NOT NULL CHECK (status IN ('ok', 'aborted')),
    items_in            integer NOT NULL,
    items_valid         integer NOT NULL,
    items_rejected      integer NOT NULL,
    warnings            integer NOT NULL,
    canonical_tracks    integer NOT NULL,
    aliases_merged      integer NOT NULL,
    review_pairs        integer NOT NULL,
    reject_rate         numeric(5, 4) NOT NULL,
    reject_reasons      jsonb NOT NULL DEFAULT '{}'
);
