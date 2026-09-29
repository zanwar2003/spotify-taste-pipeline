-- Phase 4: agent support.

-- Which profile (Spotify username) a playlist was listed under. A profile's public
-- list can include playlists owned by other people, so owner_spotify_id is not enough.
ALTER TABLE silver.playlist ADD COLUMN source_profile_id text;
CREATE INDEX silver_playlist_profile_idx ON silver.playlist (source_profile_id);

-- Per-turn agent metrics (suggested / resolved / dropped, hallucination rate, LLM calls).
ALTER TABLE playlist_versions ADD COLUMN stats jsonb NOT NULL DEFAULT '{}';
