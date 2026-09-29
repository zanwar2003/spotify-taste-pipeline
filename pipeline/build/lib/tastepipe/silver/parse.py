"""Parse and validate raw Spotify playlist-track items.

Each raw item becomes either a `ParsedTrack` or a list of `Issue`s.
Errors exclude the row (it goes to quarantine); warnings keep the row and
record that a field was dropped or repaired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .normalize import SPOTIFY_ID_RE, clean_isrc, normalize_artist, normalize_title

# Reason codes (stable strings: they are stored in silver.rejected_record).
NULL_TRACK = "NULL_TRACK"  # deleted / unavailable item
LOCAL_TRACK = "LOCAL_TRACK"  # user's local file, no Spotify ID
NOT_A_TRACK = "NOT_A_TRACK"  # podcast episode etc.
MISSING_ID = "MISSING_ID"
BAD_ID_FORMAT = "BAD_ID_FORMAT"
MISSING_TITLE = "MISSING_TITLE"
MISSING_ARTIST = "MISSING_ARTIST"
BAD_DURATION = "BAD_DURATION"
BAD_ISRC = "BAD_ISRC"  # warning: ISRC dropped, row kept
BAD_ADDED_AT = "BAD_ADDED_AT"  # warning: timestamp dropped, row kept
SCHEMA_ERROR = "SCHEMA_ERROR"  # item shape is not what we expect

MIN_DURATION_MS = 5_000  # anything shorter is almost certainly bad data
MAX_DURATION_MS = 4 * 60 * 60 * 1000


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # 'error' | 'warning'
    detail: str = ""


class ParsedTrack(BaseModel):
    model_config = ConfigDict(frozen=True)

    spotify_track_id: str
    title_norm: str
    artist_norm: str
    version_tag: str
    duration_ms: int
    isrc: str | None
    explicit: bool | None
    added_at: datetime | None

    @field_validator("spotify_track_id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not SPOTIFY_ID_RE.match(v):
            raise ValueError("bad spotify id")
        return v


@dataclass
class ParseResult:
    track: ParsedTrack | None
    issues: list[Issue] = field(default_factory=list)


def _err(code: str, detail: str = "") -> ParseResult:
    return ParseResult(None, [Issue(code, "error", detail)])


def _parse_added_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def parse_item(item: Any) -> ParseResult:
    """Validate one entry of a playlist-tracks page."""
    if not isinstance(item, dict):
        return _err(SCHEMA_ERROR, f"item is {type(item).__name__}, expected object")

    # Spotify has used both `track` and `item` for the nested object; accept either.
    obj = item.get("track", item.get("item"))
    if obj is None:
        return _err(LOCAL_TRACK if item.get("is_local") else NULL_TRACK)
    if not isinstance(obj, dict):
        return _err(SCHEMA_ERROR, "nested track is not an object")

    if item.get("is_local") or obj.get("is_local"):
        return _err(LOCAL_TRACK)
    if obj.get("type", "track") != "track":
        return _err(NOT_A_TRACK, str(obj.get("type")))

    issues: list[Issue] = []

    track_id = obj.get("id")
    if not track_id:
        return _err(MISSING_ID)
    if not isinstance(track_id, str) or not SPOTIFY_ID_RE.match(track_id):
        return _err(BAD_ID_FORMAT, str(track_id)[:40])

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return _err(MISSING_TITLE)

    artists = [a for a in (obj.get("artists") or []) if isinstance(a, dict) and a.get("name")]
    if not artists:
        return _err(MISSING_ARTIST)

    duration = obj.get("duration_ms")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or not MIN_DURATION_MS <= duration <= MAX_DURATION_MS
    ):
        return _err(BAD_DURATION, str(duration))

    title_norm, version_tag = normalize_title(name)
    artist_norm = normalize_artist(artists[0]["name"])
    if not title_norm or not artist_norm:
        return _err(MISSING_TITLE if not title_norm else MISSING_ARTIST, "empty after normalizing")

    raw_isrc = (obj.get("external_ids") or {}).get("isrc")
    isrc = clean_isrc(raw_isrc)
    if raw_isrc and isrc is None:
        issues.append(Issue(BAD_ISRC, "warning", str(raw_isrc)[:20]))

    raw_added = item.get("added_at")
    added_at = _parse_added_at(raw_added)
    if raw_added and added_at is None:
        issues.append(Issue(BAD_ADDED_AT, "warning", str(raw_added)[:40]))

    explicit = obj.get("explicit")
    try:
        track = ParsedTrack(
            spotify_track_id=track_id,
            title_norm=title_norm,
            artist_norm=artist_norm,
            version_tag=version_tag,
            duration_ms=duration,
            isrc=isrc,
            explicit=explicit if isinstance(explicit, bool) else None,
            added_at=added_at,
        )
    except ValidationError as exc:  # defensive: should be unreachable after the checks above
        return _err(SCHEMA_ERROR, re.sub(r"\s+", " ", str(exc))[:200])
    return ParseResult(track, issues)
