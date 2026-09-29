"""Taste profile: what a Spotify profile's public playlists say about the listener."""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

TOP_ARTISTS_SQL = """
SELECT t.artist_norm, count(*) AS n
  FROM silver.playlist p
  JOIN silver.playlist_track pt USING (spotify_playlist_id)
  JOIN silver.track_alias a ON a.spotify_track_id = pt.spotify_track_id
  JOIN silver.track t ON t.canonical_key = a.canonical_key
 WHERE p.source_profile_id = %s
 GROUP BY t.artist_norm
 ORDER BY n DESC, t.artist_norm
 LIMIT %s
"""

# Tracks that appear in several playlists are the strongest taste signal.
SAMPLE_TRACKS_SQL = """
SELECT t.artist_norm, t.title_norm
  FROM silver.playlist p
  JOIN silver.playlist_track pt USING (spotify_playlist_id)
  JOIN silver.track_alias a ON a.spotify_track_id = pt.spotify_track_id
  JOIN silver.track t ON t.canonical_key = a.canonical_key
 WHERE p.source_profile_id = %s AND t.version_tag = ''
 GROUP BY t.canonical_key, t.artist_norm, t.title_norm
 ORDER BY count(DISTINCT p.spotify_playlist_id) DESC, md5(t.canonical_key)
 LIMIT %s
"""

COUNTS_SQL = """
SELECT count(DISTINCT p.spotify_playlist_id), count(DISTINCT a.canonical_key)
  FROM silver.playlist p
  JOIN silver.playlist_track pt USING (spotify_playlist_id)
  JOIN silver.track_alias a ON a.spotify_track_id = pt.spotify_track_id
 WHERE p.source_profile_id = %s
"""


@dataclass(frozen=True)
class TasteProfile:
    username: str
    n_playlists: int
    n_tracks: int
    top_artists: list[tuple[str, int]] = field(default_factory=list)
    sample_tracks: list[tuple[str, str]] = field(default_factory=list)  # (artist, title)

    @property
    def is_empty(self) -> bool:
        return self.n_tracks == 0


def load_profile(
    conn: psycopg.Connection, username: str, max_artists: int = 15, max_samples: int = 50
) -> TasteProfile:
    with conn.cursor() as cur:
        cur.execute(COUNTS_SQL, (username,))
        n_playlists, n_tracks = cur.fetchone() or (0, 0)
        cur.execute(TOP_ARTISTS_SQL, (username, max_artists))
        artists = [(a, int(n)) for a, n in cur.fetchall()]
        cur.execute(SAMPLE_TRACKS_SQL, (username, max_samples))
        samples = [(a, t) for a, t in cur.fetchall()]
    return TasteProfile(username, int(n_playlists), int(n_tracks), artists, samples)
