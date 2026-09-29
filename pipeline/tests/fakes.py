"""Test doubles for the agent: a scripted LLM and an in-memory Spotify."""

from __future__ import annotations

import re
from typing import Any

from helpers import raw_item, sid

from tastepipe.agent.llm import EditContext, ProposeContext, ReferenceContext
from tastepipe.agent.models import (
    EditPlan,
    ProposeResult,
    ReferencePicks,
    Suggestion,
    TrackRef,
)
from tastepipe.agent.profile import TasteProfile
from tastepipe.silver.parse import parse_item


def cat(n: int, name: str, artist: str, *, duration_ms: int = 200_000, isrc: str | None = None):
    """A raw Spotify track object for the fake catalog."""
    return raw_item(
        n, name=name, artist=artist, duration_ms=duration_ms, isrc=isrc or f"USAAA{n:07d}"
    )["track"]


def sug(title: str, artist: str, reason: str = "fits", origin: str = "similar") -> Suggestion:
    return Suggestion(title=title, artist=artist, reason=reason, origin=origin)


def ref(n: int, title: str = "Song", artist: str = "Artist", **kw) -> TrackRef:
    """A verified TrackRef built the same way the pipeline builds them."""
    obj = cat(n, title, artist, **kw)
    parsed = parse_item({"track": obj}).track
    assert parsed is not None
    return TrackRef(sid(n), title, artist, parsed)


_FIELD_RE = re.compile(r'track:"(.*?)" artist:"(.*?)"')

PROFILE = TasteProfile(
    username="zara",
    n_playlists=2,
    n_tracks=40,
    top_artists=[("artist a", 9)],
    sample_tracks=[("artist a", "song one")],
)


class FakeSpotify:
    def __init__(
        self,
        catalog: list[dict[str, Any]],
        playlists: dict[str, tuple[str, list[dict[str, Any]]]] | None = None,
    ):
        self.catalog = catalog
        self.playlists = playlists or {}  # id -> (name, raw track objects)
        self.profiles: dict[str, list[str]] = {}  # username -> playlist ids
        self.queries: list[str] = []
        self.user_playlist_calls: list[str] = []
        self.track_lookups: list[list[str]] = []

    def search_tracks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Fuzzy like the real thing: a field query returns tracks matching title OR artist,
        exact-title hits first; a loose query needs both terms present."""
        self.queries.append(query)
        m = _FIELD_RE.search(query)
        if m:
            title, artist = m.group(1).lower(), m.group(2).lower()
            hits = [
                t
                for t in self.catalog
                if t["name"].lower() == title or any(a["name"].lower() == artist for a in t["artists"])
            ]
            hits.sort(key=lambda t: t["name"].lower() != title)
        else:
            q = query.lower()
            hits = [
                t
                for t in self.catalog
                if t["name"].lower() in q and any(a["name"].lower() in q for a in t["artists"])
            ]
        return hits[:limit]

    def search_playlists(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return [{"id": pid, "name": name} for pid, (name, _) in self.playlists.items()][:limit]

    def playlist_tracks(self, playlist_id: str):
        _, tracks = self.playlists.get(playlist_id, ("", []))
        if tracks:
            yield {
                "offset": 0,
                "items": [{"track": t, "added_at": "2024-01-01T00:00:00Z"} for t in tracks],
                "next": None,
            }

    # -- used by ingestion and the service (real SpotifyClient has the same methods) -----

    def user_playlists(self, username: str):
        """Playlist listing for a profile: every playlist id registered under `profiles`."""
        self.user_playlist_calls.append(username)
        ids = self.profiles.get(username, [])
        if ids:
            yield {
                "items": [
                    {
                        "id": pid,
                        "name": self.playlists[pid][0],
                        "public": True,
                        "owner": {"id": username},
                        "tracks": {"total": len(self.playlists[pid][1])},
                    }
                    for pid in ids
                ],
                "next": None,
            }

    def tracks(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        self.track_lookups.append(list(ids))
        everything = list(self.catalog) + [t for _, ts in self.playlists.values() for t in ts]
        by_id = {t["id"]: t for t in everything}
        return {i: by_id[i] for i in ids if i in by_id}


class FakeLLM:
    def __init__(self, proposals=None, edits=None, picks=None):
        self.proposals = list(proposals or [])
        self.edits = list(edits or [])
        self.picks = list(picks or [])
        self.propose_ctx: list[ProposeContext] = []
        self.edit_ctx: list[EditContext] = []
        self.pick_ctx: list[ReferenceContext] = []

    def propose(self, ctx: ProposeContext) -> ProposeResult:
        self.propose_ctx.append(ctx)
        if not self.proposals:
            return ProposeResult(suggestions=[])
        return self.proposals.pop(0)

    def plan_edit(self, ctx: EditContext) -> EditPlan:
        self.edit_ctx.append(ctx)
        return self.edits.pop(0)

    def pick_from_reference(self, ctx: ReferenceContext) -> ReferencePicks:
        self.pick_ctx.append(ctx)
        return self.picks.pop(0)
