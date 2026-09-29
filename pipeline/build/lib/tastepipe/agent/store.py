"""Persistence for playlists and their append-only versions.

Runs as the restricted app role. Each call opens a transaction and sets
`app.user_id`, so Postgres row-level security enforces that a user can only
touch their own rows even if this code had a bug.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .models import PlaylistRequest


class NotFoundError(LookupError):
    """No such playlist for this user (or it belongs to someone else)."""


@dataclass(frozen=True)
class StoredTrack:
    position: int
    spotify_track_id: str
    isrc: str | None
    rationale: str | None


@dataclass(frozen=True)
class StoredPlaylist:
    id: UUID
    title: str
    intent: str | None
    mood: str | None
    target_length_min: int | None
    source_profile_id: str | None
    status: str
    version_no: int
    tracks: list[StoredTrack]

    def request(self) -> PlaylistRequest:
        return PlaylistRequest(
            source_username=self.source_profile_id or "unknown",
            intent=self.intent or "general listening",
            mood=self.mood or "any",
            target_minutes=self.target_length_min or 60,
        )


@contextmanager
def user_tx(conninfo: str, user_id: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(conninfo) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
        yield conn  # commit on clean exit, rollback on exception (psycopg context manager)


def ensure_user(conn: psycopg.Connection, user_id: str) -> None:
    """The row normally exists from login; this keeps the FK safe if it doesn't."""
    conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))


def create_playlist(
    conn: psycopg.Connection, user_id: str, req: PlaylistRequest, title: str
) -> UUID:
    ensure_user(conn, user_id)
    row = conn.execute(
        """INSERT INTO playlists (owner_id, title, intent, mood, target_length_min, source_profile_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (user_id, title[:100], req.intent, req.mood, req.target_minutes, req.source_username),
    ).fetchone()
    assert row is not None
    return row[0]


def add_version(
    conn: psycopg.Connection,
    user_id: str,
    playlist_id: UUID,
    tracks: list[dict[str, Any]],
    *,
    feedback: str | None,
    diff: dict[str, Any],
    stats: dict[str, Any],
) -> int:
    """Append a version (never updates an old one) and return its number."""
    row = conn.execute(
        "SELECT coalesce(max(version_no), 0) + 1 FROM playlist_versions WHERE playlist_id = %s",
        (playlist_id,),
    ).fetchone()
    assert row is not None
    version_no = row[0]
    version_id = conn.execute(
        """INSERT INTO playlist_versions (playlist_id, owner_id, version_no, feedback_text, diff, stats)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (playlist_id, user_id, version_no, feedback, Jsonb(diff), Jsonb(stats)),
    ).fetchone()
    assert version_id is not None
    for position, t in enumerate(tracks):
        conn.execute(
            """INSERT INTO playlist_tracks
               (version_id, owner_id, position, spotify_track_id, isrc, rationale)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (version_id[0], user_id, position, t["spotify_track_id"], t.get("isrc"), t.get("rationale")),
        )
    conn.execute("UPDATE playlists SET updated_at = now() WHERE id = %s", (playlist_id,))
    return version_no


def get_playlist(conn: psycopg.Connection, playlist_id: UUID) -> StoredPlaylist:
    """Latest version of a playlist. RLS makes other users' playlists invisible."""
    head = conn.execute(
        """SELECT id, title, intent, mood, target_length_min, source_profile_id, status
             FROM playlists WHERE id = %s""",
        (playlist_id,),
    ).fetchone()
    if head is None:
        raise NotFoundError(str(playlist_id))
    ver = conn.execute(
        """SELECT id, version_no FROM playlist_versions
            WHERE playlist_id = %s ORDER BY version_no DESC LIMIT 1""",
        (playlist_id,),
    ).fetchone()
    tracks: list[StoredTrack] = []
    version_no = 0
    if ver is not None:
        version_no = ver[1]
        tracks = [
            StoredTrack(*r)
            for r in conn.execute(
                """SELECT position, spotify_track_id, isrc, rationale
                     FROM playlist_tracks WHERE version_id = %s ORDER BY position""",
                (ver[0],),
            )
        ]
    return StoredPlaylist(*head, version_no, tracks)


def set_status(conn: psycopg.Connection, playlist_id: UUID, status: str) -> None:
    updated = conn.execute(
        "UPDATE playlists SET status = %s::playlist_status, updated_at = now() WHERE id = %s",
        (status, playlist_id),
    ).rowcount
    if not updated:
        raise NotFoundError(str(playlist_id))
