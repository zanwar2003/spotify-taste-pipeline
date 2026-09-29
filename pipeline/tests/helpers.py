"""Builders for fake Spotify API payloads and parsed tracks."""

from __future__ import annotations

from typing import Any

from tastepipe.silver.parse import ParsedTrack


def sid(n: int) -> str:
    """A valid 22-char Spotify ID derived from an integer."""
    return f"{n:022d}"


def raw_item(
    n: int = 1,
    *,
    name: str = "Song",
    artist: str = "Artist",
    duration_ms: int = 200_000,
    isrc: str | None = "USRC17607839",
    added_at: str | None = "2024-01-01T00:00:00Z",
    **overrides: Any,
) -> dict[str, Any]:
    track: dict[str, Any] = {
        "id": sid(n),
        "name": name,
        "type": "track",
        "duration_ms": duration_ms,
        "explicit": False,
        "artists": [{"id": "a1", "name": artist}],
        "external_ids": {"isrc": isrc} if isrc else {},
    }
    track.update(overrides)
    return {"added_at": added_at, "is_local": False, "track": track}


def parsed(
    n: int,
    *,
    title: str = "song",
    artist: str = "artist",
    tag: str = "",
    duration_ms: int = 200_000,
    isrc: str | None = None,
) -> ParsedTrack:
    return ParsedTrack(
        spotify_track_id=sid(n),
        title_norm=title,
        artist_norm=artist,
        version_tag=tag,
        duration_ms=duration_ms,
        isrc=isrc,
        explicit=None,
        added_at=None,
    )
