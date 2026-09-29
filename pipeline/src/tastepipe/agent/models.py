from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..silver.parse import ParsedTrack

MAX_TARGET_MINUTES = 480


class PlaylistRequest(BaseModel):
    source_username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    intent: str = Field(min_length=1, max_length=120)
    mood: str = Field(min_length=1, max_length=120)
    target_minutes: int = Field(gt=0, le=MAX_TARGET_MINUTES)

    @property
    def target_ms(self) -> int:
        return self.target_minutes * 60_000


class Suggestion(BaseModel):
    """One song the LLM wants on the playlist. Unverified until matched on Spotify."""

    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=200)
    origin: Literal["liked", "similar", "reference"] = "similar"

    @field_validator("title", "artist", "reason", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class ProposeResult(BaseModel):
    playlist_title: str | None = Field(default=None, max_length=100)
    suggestions: list[Suggestion] = Field(max_length=80)


class EditPlan(BaseModel):
    """What the LLM wants to change in response to user feedback."""

    remove_positions: list[int] = Field(default_factory=list, max_length=100)  # 1-based
    add: list[Suggestion] = Field(default_factory=list, max_length=60)
    reference_query: str | None = Field(default=None, max_length=120)
    summary: str = Field(default="", max_length=300)


class ReferencePick(BaseModel):
    index: int  # 1-based index into the candidate list shown to the LLM
    reason: str = Field(default="", max_length=200)


class ReferencePicks(BaseModel):
    picks: list[ReferencePick] = Field(max_length=60)


@dataclass(frozen=True)
class TrackRef:
    """A verified, real Spotify track. `parsed` carries the normalized match fields."""

    spotify_track_id: str
    title: str  # display only, fetched live from Spotify, never persisted
    artist: str  # display only
    parsed: ParsedTrack
    reason: str = ""
    origin: str = "similar"

    @property
    def duration_ms(self) -> int:
        return self.parsed.duration_ms
