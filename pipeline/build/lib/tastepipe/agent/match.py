"""Verification: turn an LLM suggestion into a real Spotify track, or reject it.

This is the guard against hallucinated songs. A suggestion is accepted only if a
Spotify search result matches both title and artist closely, and is the same
kind of recording (a live take is never accepted for a studio request).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ..silver.normalize import normalize_artist, normalize_title
from ..silver.parse import ParsedTrack, parse_item
from .models import Suggestion

TITLE_MIN = 0.9
ARTIST_MIN = 0.85


@dataclass(frozen=True)
class Match:
    raw: dict[str, Any]
    parsed: ParsedTrack
    title: str
    artist: str
    score: float


def build_query(s: Suggestion) -> str:
    """Field-filtered Spotify query; quotes are stripped so they can't break the syntax."""
    title = s.title.replace('"', " ")
    artist = s.artist.replace('"', " ")
    return f'track:"{title}" artist:"{artist}"'


def build_loose_query(s: Suggestion) -> str:
    return f"{s.title} {s.artist}".replace('"', " ")


def _ratio(a: str, b: str) -> float:
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


_COLLAB_SPLIT = re.compile(r"\s*(?:,|&|/|\band\b|\bfeat\.?|\bft\.?|\bfeaturing\b|\bwith\b|\bx\b)\s*")


def _artist_score(suggested_raw: str, credited: list[str]) -> float:
    """Best similarity between the suggested artist (or any collaborator named in it)
    and any credited artist. Whole-string comparison comes first so names that contain
    'and' or '&' (Simon & Garfunkel) still match themselves."""
    suggested_names = {normalize_artist(suggested_raw)}
    suggested_names.update(
        normalize_artist(part) for part in _COLLAB_SPLIT.split(suggested_raw.casefold()) if part
    )
    suggested_names.discard("")
    best = 0.0
    for name in credited:
        norm = normalize_artist(name)
        if not norm:
            continue
        for candidate in suggested_names:
            best = max(best, _ratio(candidate, norm))
    return best


def to_match(candidate: dict[str, Any]) -> Match | None:
    """Parse a raw Spotify track object; None if it fails validation."""
    result = parse_item({"track": candidate})
    if result.track is None:
        return None
    artists = [a["name"] for a in candidate.get("artists", []) if a.get("name")]
    return Match(candidate, result.track, candidate.get("name", ""), ", ".join(artists), 1.0)


def pick_match(s: Suggestion, candidates: list[dict[str, Any]]) -> Match | None:
    title_norm, tag = normalize_title(s.title)
    artist_norm = normalize_artist(s.artist)
    if not title_norm or not artist_norm:
        return None

    best: Match | None = None
    for cand in candidates:
        m = to_match(cand)
        if m is None or m.parsed.version_tag != tag:
            continue
        title_score = _ratio(title_norm, m.parsed.title_norm)
        artist_score = _artist_score(s.artist, [a.get("name", "") for a in cand.get("artists", [])])
        if title_score < TITLE_MIN or artist_score < ARTIST_MIN:
            continue
        score = round(0.6 * title_score + 0.4 * artist_score, 4)
        if best is None or score > best.score:
            best = Match(m.raw, m.parsed, m.title, m.artist, score)
    return best
