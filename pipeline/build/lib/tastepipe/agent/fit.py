"""Fit a set of verified tracks to the requested playlist length."""

from __future__ import annotations

from .models import TrackRef

LOW = 0.9  # below this fraction of the target the playlist counts as too short
HIGH = 1.1  # never overshoot the target by more than this


def total_ms(tracks: list[TrackRef]) -> int:
    return sum(t.duration_ms for t in tracks)


def is_short(tracks: list[TrackRef], target_ms: int) -> bool:
    return total_ms(tracks) < target_ms * LOW


def _take(seq: list[TrackRef], already_ms: int, target_ms: int) -> list[TrackRef]:
    out: list[TrackRef] = []
    total = already_ms
    for t in seq:
        if total >= target_ms:
            break
        if total + t.duration_ms > target_ms * HIGH:
            continue  # this one would overshoot; a shorter one later may still fit
        out.append(t)
        total += t.duration_ms
    return out


def fit_length(
    kept: list[TrackRef], new: list[TrackRef], target_ms: int, *, prefer_new: bool
) -> list[TrackRef]:
    """Choose tracks up to the target length. Display order is always kept, then new.

    prefer_new: user just asked for additions, so trim older tracks rather than the new ones.
    Otherwise (first generation, top-up rounds) earlier picks win and the new tail is trimmed.
    """
    if prefer_new:
        chosen_new = _take(new, 0, target_ms)
        chosen_kept = _take(kept, total_ms(chosen_new), target_ms)
    else:
        chosen_kept = _take(kept, 0, target_ms)
        chosen_new = _take(new, total_ms(chosen_kept), target_ms)
    return chosen_kept + chosen_new
