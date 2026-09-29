-- Synthetic demo data for developing and testing the gold layer.
-- Nothing here is real: no Spotify content and no real users. Safe to commit.
-- Run as the owner role (bypasses RLS), against a database migrated from db/init/*.sql.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/seed/demo_data.sql

TRUNCATE silver.review_queue, silver.playlist_track, silver.track_alias, silver.track,
         silver.playlist, silver.rejected_record, silver.run_log, bronze.raw_api_response,
         users CASCADE;

-- ------------------------------------------------------------------- bronze
INSERT INTO bronze.raw_api_response (source, endpoint, request_key, http_status, payload, payload_sha256)
SELECT 'spotify', 'users/{id}/playlists', 'user:demo_' || p || ':page:0', 200, '{}'::jsonb, md5('demo' || p)
  FROM generate_series(1, 3) p;

-- ------------------------------------------------------------------- silver
-- 60 recordings over 12 artists; every 15th is a live version.
INSERT INTO silver.track (canonical_key, isrc, title_norm, artist_norm, version_tag, duration_ms, explicit)
SELECT 'isrc:USAAA' || lpad(n::text, 7, '0'), 'USAAA' || lpad(n::text, 7, '0'),
       'song ' || n, 'artist ' || ((n - 1) % 12 + 1),
       CASE WHEN n % 15 = 0 THEN 'live' ELSE '' END,
       150000 + (n * 7919) % 120000, n % 5 = 0
  FROM generate_series(1, 60) n;

INSERT INTO silver.track_alias (spotify_track_id, canonical_key, match_reason)
SELECT lpad(n::text, 22, '0'), 'isrc:USAAA' || lpad(n::text, 7, '0'), 'canonical'
  FROM generate_series(1, 60) n;
-- eight re-release IDs that resolve to the first eight recordings
INSERT INTO silver.track_alias (spotify_track_id, canonical_key, match_reason)
SELECT lpad((100 + n)::text, 22, '0'), 'isrc:USAAA' || lpad(n::text, 7, '0'), 'same_isrc'
  FROM generate_series(1, 8) n;

INSERT INTO silver.playlist (spotify_playlist_id, owner_spotify_id, is_public, track_total,
                             source_profile_id, first_seen_at, last_seen_at)
SELECT 'DEMOPL' || p, 'demo_' || ((p - 1) / 2 + 1), true, 20, 'demo_' || ((p - 1) / 2 + 1),
       now() - interval '10 days', now() - interval '1 day'
  FROM generate_series(1, 6) p;

INSERT INTO silver.playlist_track (spotify_playlist_id, position, spotify_track_id, added_at)
SELECT 'DEMOPL' || p, pos,
       lpad(CASE WHEN t <= 8 AND pos % 2 = 0 THEN 100 + t ELSE t END::text, 22, '0'),
       now() - (pos || ' days')::interval - (p || ' hours')::interval
  FROM generate_series(1, 6) p
  CROSS JOIN generate_series(0, 19) pos
  CROSS JOIN LATERAL (SELECT (p * 7 + pos * 3) % 60 + 1 AS t) x;

INSERT INTO silver.rejected_record (bronze_id, item_index, entity, reason_code, severity, detail)
SELECT (SELECT min(id) FROM bronze.raw_api_response) + (i % 3), i, 'track',
       (ARRAY['NULL_TRACK', 'LOCAL_TRACK', 'BAD_ISRC', 'BAD_DURATION'])[i % 4 + 1],
       CASE WHEN i % 4 = 2 THEN 'warning' ELSE 'error' END, NULL
  FROM generate_series(1, 12) i;

INSERT INTO silver.run_log (started_at, status, items_in, items_valid, items_rejected, warnings,
                            canonical_tracks, aliases_merged, review_pairs, reject_rate, reject_reasons)
VALUES
  (now() - interval '3 days', 'ok',      130, 120, 10, 3, 60, 8, 1, 0.0769, '{"NULL_TRACK": 6, "LOCAL_TRACK": 4}'),
  (now() - interval '2 days', 'aborted',  40,   8, 32, 0,  0, 0, 0, 0.8000, '{"MISSING_ID": 32}'),
  (now() - interval '1 day',  'ok',      132, 123,  9, 2, 60, 8, 1, 0.0682, '{"NULL_TRACK": 5, "LOCAL_TRACK": 4}');

-- ---------------------------------------------------------------- app tables
INSERT INTO users (id, display_name, refresh_token_enc, created_at)
SELECT 'demo_user_' || u, 'Demo User ' || u, 'ENCRYPTED-PLACEHOLDER', now() - ((35 - u * 5) || ' days')::interval
  FROM generate_series(1, 4) u;

-- Ten playlists with deliberately messy free-text moods (cleaned in staging).
INSERT INTO playlists (id, owner_id, title, intent, mood, target_length_min, source_profile_id,
                       status, is_favorite, spotify_playlist_id, created_at, updated_at)
SELECT ('00000000-0000-0000-0000-' || lpad(p::text, 12, '0'))::uuid,
       'demo_user_' || ((p - 1) % 4 + 1),
       'Demo playlist ' || p,
       (ARRAY['Workout', 'Focus', 'Road trip', 'Party', 'Wind down'])[(p - 1) % 5 + 1],
       (ARRAY['Upbeat', 'upbeat ', 'Chill', 'CHILL', 'Moody', 'Nostalgic', ' energetic', 'Upbeat', 'Chill', 'Nostalgic'])[p],
       (ARRAY[30, 60, 45, 120, 30, 60, 90, 30, 60, 45])[p],
       'demo_' || ((p - 1) % 3 + 1),
       (ARRAY['exported', 'approved', 'draft', 'approved', 'draft', 'exported', 'archived', 'approved', 'draft', 'approved']::playlist_status[])[p],
       p % 4 = 0,
       CASE WHEN p IN (1, 6) THEN 'DEMOEXPORT' || p END,
       now() - ((20 - p) || ' days')::interval,
       now() - ((10 - p) || ' days')::interval
  FROM generate_series(1, 10) p;

-- 1 to 4 versions per playlist; version 1 is generation, later versions are refinements.
INSERT INTO playlist_versions (id, playlist_id, owner_id, version_no, feedback_text, diff, stats, created_at)
SELECT md5('v' || p || '-' || v)::uuid,
       ('00000000-0000-0000-0000-' || lpad(p::text, 12, '0'))::uuid,
       'demo_user_' || ((p - 1) % 4 + 1),
       v,
       CASE WHEN v = 1 THEN NULL ELSE 'make it more ' || (ARRAY['upbeat', 'mellow', 'nostalgic'])[v % 3 + 1] END,
       jsonb_build_object(
         'added', (SELECT jsonb_agg(lpad((((p * 3 + v * 5 + k) % 60) + 1)::text, 22, '0'))
                     FROM generate_series(1, CASE WHEN v = 1 THEN 8 ELSE 2 END) k),
         'removed', CASE WHEN v = 1 THEN '[]'::jsonb
                         ELSE (SELECT jsonb_agg(lpad((((p * 3 + v * 5 + k + 30) % 60) + 1)::text, 22, '0'))
                                 FROM generate_series(1, 2) k) END),
       jsonb_build_object(
         'suggested', 12,
         'verified', 12 - (p + v) % 3 - (p * v) % 2,
         'dropped_not_found', (p + v) % 3,
         'dropped_low_confidence', (p * v) % 2,
         'duplicates_removed', v % 2,
         'llm_calls', v,
         'rounds', v,
         'unverified_rate', round((((p + v) % 3 + (p * v) % 2) / 12.0)::numeric, 4)),
       now() - ((20 - p) || ' days')::interval + (v || ' hours')::interval
  FROM generate_series(1, 10) p
  CROSS JOIN LATERAL generate_series(1, 1 + p % 4) v;

INSERT INTO playlist_tracks (version_id, owner_id, position, spotify_track_id, isrc, rationale)
SELECT md5('v' || p || '-' || v)::uuid,
       'demo_user_' || ((p - 1) % 4 + 1),
       pos,
       lpad((((p * 3 + v * 5 + pos) % 60) + 1)::text, 22, '0'),
       'USAAA' || lpad((((p * 3 + v * 5 + pos) % 60) + 1)::text, 7, '0'),
       'Fits the mood.'
  FROM generate_series(1, 10) p
  CROSS JOIN LATERAL generate_series(1, 1 + p % 4) v
  CROSS JOIN generate_series(0, 7) pos;
