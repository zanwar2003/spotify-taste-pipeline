"""Application service: profile -> agent -> versioned persistence.

Two database roles are used on purpose:
* the owner role (`owner_dsn`) writes bronze/silver, which hold public Spotify data;
* the restricted app role (`app_dsn`) writes user playlists under row-level security.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg

from ..ingest import ingest_user
from ..silver.load import QualityGateError, build_silver
from ..silver.parse import parse_item
from ..spotify import SpotifyClient
from .graph import AgentResult, Deps, generate, refine
from .llm import LLM, MAX_FEEDBACK_CHARS
from .models import PlaylistRequest, TrackRef
from .profile import TasteProfile, load_profile
from .store import (
    StoredPlaylist,
    add_version,
    create_playlist,
    get_playlist,
    set_status,
    user_tx,
)

log = logging.getLogger("tastepipe.agent")

PROFILE_MAX_AGE = timedelta(hours=24)
USER_ID_RE = re.compile(r"^[\w.\-]{1,100}$")


class ProfileNotFoundError(RuntimeError):
    """The profile has no public playlists we can read."""


class GenerationFailedError(RuntimeError):
    """The agent could not produce a playlist we can stand behind."""


@dataclass
class ViewTrack:
    position: int
    spotify_track_id: str
    title: str
    artist: str
    duration_ms: int
    reason: str
    origin: str | None = None


@dataclass
class PlaylistView:
    id: str
    title: str
    status: str
    version: int
    target_minutes: int
    total_minutes: float
    tracks: list[ViewTrack]
    summary: str = ""
    added: list[str] = field(default_factory=list)  # "Artist - Title", transient display
    removed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def _label(t: TrackRef) -> str:
    return f"{t.artist} - {t.title}"


def _track_payload(t: TrackRef) -> dict[str, Any]:
    return {"spotify_track_id": t.spotify_track_id, "isrc": t.parsed.isrc, "rationale": t.reason or None}


def _view(
    playlist_id: UUID | str,
    title: str,
    status: str,
    version: int,
    req: PlaylistRequest,
    tracks: list[TrackRef],
    **extra: Any,
) -> PlaylistView:
    return PlaylistView(
        id=str(playlist_id),
        title=title,
        status=status,
        version=version,
        target_minutes=req.target_minutes,
        total_minutes=round(sum(t.duration_ms for t in tracks) / 60_000, 1),
        tracks=[
            ViewTrack(i, t.spotify_track_id, t.title, t.artist, t.duration_ms, t.reason, t.origin)
            for i, t in enumerate(tracks)
        ],
        **extra,
    )


class AgentService:
    def __init__(
        self,
        *,
        owner_dsn: str,
        app_dsn: str,
        spotify: SpotifyClient,
        llm: LLM,
        profile_max_age: timedelta = PROFILE_MAX_AGE,
    ):
        self._owner_dsn = owner_dsn
        self._app_dsn = app_dsn
        self._spotify = spotify
        self._deps = Deps(llm=llm, spotify=spotify)
        self._max_age = profile_max_age

    # ------------------------------------------------------------------ profile

    def ensure_profile(self, username: str) -> TasteProfile:
        """Load the taste profile, ingesting and cleaning the user's public data if needed."""
        with psycopg.connect(self._owner_dsn) as conn:
            profile = load_profile(conn, username)
            if profile.is_empty or self._is_stale(conn, username):
                log.info("refreshing profile %s", username)
                ingest_user(self._spotify, conn, username)
                try:
                    build_silver(conn)
                except QualityGateError as exc:
                    log.error("silver quality gate failed during profile refresh: %s", exc)
                    if profile.is_empty:
                        raise ProfileNotFoundError(username) from exc
                profile = load_profile(conn, username)
        if profile.is_empty:
            raise ProfileNotFoundError(username)
        return profile

    def _is_stale(self, conn: psycopg.Connection, username: str) -> bool:
        row = conn.execute(
            "SELECT now() - max(last_seen_at) FROM silver.playlist WHERE source_profile_id = %s",
            (username,),
        ).fetchone()
        return row is None or row[0] is None or row[0] > self._max_age

    # ---------------------------------------------------------------- hydration

    def _hydrate(self, stored: StoredPlaylist) -> tuple[list[TrackRef], int]:
        """Stored IDs -> live titles/artists/durations from Spotify (we don't persist them)."""
        found = self._spotify.tracks([t.spotify_track_id for t in stored.tracks])
        refs: list[TrackRef] = []
        missing = 0
        for st in stored.tracks:
            obj = found.get(st.spotify_track_id)
            parsed = parse_item({"track": obj}).track if obj else None
            if parsed is None:
                missing += 1
                continue
            artists = ", ".join(a["name"] for a in obj.get("artists", []) if a.get("name"))
            refs.append(TrackRef(st.spotify_track_id, obj.get("name", ""), artists, parsed, st.rationale or ""))
        return refs, missing

    # ------------------------------------------------------------------- create

    def create(self, user_id: str, req: PlaylistRequest) -> PlaylistView:
        _check_user(user_id)
        profile = self.ensure_profile(req.source_username)
        result = generate(self._deps, req, profile)
        if not result.tracks:
            raise GenerationFailedError("none of the suggested songs could be verified on Spotify")

        title = result.title or f"{req.mood.title()} {req.intent.title()}"
        with user_tx(self._app_dsn, user_id) as conn:
            pid = create_playlist(conn, user_id, req, title)
            version = add_version(
                conn, user_id, pid, [_track_payload(t) for t in result.tracks],
                feedback=None,
                diff={"added": [t.spotify_track_id for t in result.tracks], "removed": []},
                stats=result.stats,
            )  # fmt: skip
        return _view(
            pid, title, "draft", version, req, result.tracks,
            added=[_label(t) for t in result.tracks], notes=self._length_notes(req, result),
            stats=result.stats,
        )  # fmt: skip

    # ------------------------------------------------------------------- refine

    def refine(self, user_id: str, playlist_id: UUID, feedback: str) -> PlaylistView:
        _check_user(user_id)
        feedback = feedback.strip()
        if not feedback or len(feedback) > MAX_FEEDBACK_CHARS:
            raise ValueError(f"feedback must be 1-{MAX_FEEDBACK_CHARS} characters")

        with user_tx(self._app_dsn, user_id) as conn:
            stored = get_playlist(conn, playlist_id)
        req = stored.request()
        profile = self.ensure_profile(req.source_username)
        current, missing = self._hydrate(stored)

        result = refine(self._deps, req, profile, current, feedback)
        if not result.tracks:
            raise GenerationFailedError("that change would leave the playlist empty")

        before = {t.spotify_track_id for t in current}
        after = {t.spotify_track_id for t in result.tracks}
        added = [t for t in result.tracks if t.spotify_track_id not in before]
        removed = [t for t in current if t.spotify_track_id not in after]

        with user_tx(self._app_dsn, user_id) as conn:
            version = add_version(
                conn, user_id, playlist_id, [_track_payload(t) for t in result.tracks],
                feedback=feedback,
                diff={
                    "added": [t.spotify_track_id for t in added],
                    "removed": [t.spotify_track_id for t in removed],
                },
                stats=result.stats,
            )  # fmt: skip
            if stored.status == "approved":  # editing an approved playlist reopens it
                set_status(conn, playlist_id, "draft")

        notes = self._length_notes(req, result) + result.notes
        if missing:
            notes.append(f"{missing} song(s) are no longer available on Spotify and were dropped.")
        return _view(
            playlist_id, stored.title, "draft" if stored.status == "approved" else stored.status,
            version, req, result.tracks, summary=result.summary,
            added=[_label(t) for t in added], removed=[_label(t) for t in removed],
            notes=notes, stats=result.stats,
        )  # fmt: skip

    # ------------------------------------------------------------ read / approve

    def get(self, user_id: str, playlist_id: UUID) -> PlaylistView:
        _check_user(user_id)
        with user_tx(self._app_dsn, user_id) as conn:
            stored = get_playlist(conn, playlist_id)
        refs, missing = self._hydrate(stored)
        notes = [f"{missing} song(s) are no longer available on Spotify."] if missing else []
        return _view(
            stored.id, stored.title, stored.status, stored.version_no, stored.request(), refs,
            notes=notes,
        )  # fmt: skip

    def approve(self, user_id: str, playlist_id: UUID) -> PlaylistView:
        _check_user(user_id)
        with user_tx(self._app_dsn, user_id) as conn:
            set_status(conn, playlist_id, "approved")
        return self.get(user_id, playlist_id)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _length_notes(req: PlaylistRequest, result: AgentResult) -> list[str]:
        total = sum(t.duration_ms for t in result.tracks)
        if total < req.target_ms * 0.9:
            return [
                (
                    f"Only found about {round(total / 60_000)} of the {req.target_minutes} minutes "
                    "you asked for. Ask for more songs or a different mood to fill it out."
                )
            ]
        return []


def _check_user(user_id: str) -> None:
    if not USER_ID_RE.match(user_id):
        raise ValueError("invalid user id")
