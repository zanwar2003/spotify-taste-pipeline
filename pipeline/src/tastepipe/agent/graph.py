"""LangGraph orchestration for generating and refining a playlist.

    START ─► route ─┬─ generate ─► propose ──────────────┐
                    └─ refine ───► plan_edit ─┬─► verify ┤
                                              └► reference ─► verify
    verify ─► assemble ─┬─ short and rounds left ─► propose (top-up)
                        └─ done ─► END

Nothing the LLM says reaches the playlist unverified: `verify` only keeps suggestions
that match a real Spotify search result (see match.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from ..silver.resolve import resolve
from .fit import fit_length, is_short, total_ms
from .llm import LLM, EditContext, ProposeContext, ReferenceContext
from .match import build_loose_query, build_query, pick_match, to_match
from .models import PlaylistRequest, Suggestion, TrackRef
from .profile import TasteProfile

AVG_TRACK_MS = 3.5 * 60_000
OVERSHOOT = 1.4  # ask for extra suggestions: some will fail verification
MAX_ROUNDS = 3
MAX_REFERENCE_TRACKS = 100


class SpotifyLike(Protocol):
    def search_tracks(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
    def search_playlists(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
    def playlist_tracks(self, playlist_id: str) -> Any: ...


class AgentState(TypedDict, total=False):
    mode: str  # 'generate' | 'refine'
    request: PlaylistRequest
    profile: TasteProfile
    feedback: str
    kept: list[TrackRef]
    pending: list[Suggestion]
    new: list[TrackRef]
    chosen: list[TrackRef]
    dropped: list[dict[str, str]]
    round: int
    prefer_new: bool
    title: str | None
    summary: str
    reference_query: str | None
    notes: list[str]
    stats: dict[str, int]


@dataclass
class Deps:
    llm: LLM
    spotify: SpotifyLike
    max_rounds: int = MAX_ROUNDS


def _bump(state: AgentState, **deltas: int) -> dict[str, int]:
    stats = dict(state.get("stats") or {})
    for k, v in deltas.items():
        stats[k] = stats.get(k, 0) + v
    return stats


def _label(t: TrackRef) -> str:
    return f"{t.artist} - {t.title}"


def build_graph(deps: Deps):
    llm, spotify = deps.llm, deps.spotify

    def route(state: AgentState) -> str:
        return "propose" if state["mode"] == "generate" else "plan_edit"

    def propose(state: AgentState) -> dict[str, Any]:
        req = state["request"]
        kept = state.get("kept", [])
        remaining_ms = max(req.target_ms - total_ms(kept), 0)
        needed = max(math.ceil(remaining_ms / AVG_TRACK_MS), 1)
        ask = math.ceil(needed * OVERSHOOT) + 2
        result = llm.propose(
            ProposeContext(
                request=req,
                profile=state["profile"],
                avoid=[_label(t) for t in kept],
                count=ask,
                first_round=state.get("round", 0) == 0 and not kept,
            )
        )
        update: dict[str, Any] = {
            "pending": result.suggestions,
            "round": state.get("round", 0) + 1,
            "stats": _bump(state, llm_calls=1, suggested=len(result.suggestions)),
        }
        if result.playlist_title and not state.get("title"):
            update["title"] = result.playlist_title
        return update

    def plan_edit(state: AgentState) -> dict[str, Any]:
        current = state["kept"]
        plan = llm.plan_edit(
            EditContext(
                request=state["request"],
                profile=state["profile"],
                current=current,
                feedback=state["feedback"],
            )
        )
        # Ignore positions the model made up; dedupe the rest.
        remove = {p for p in plan.remove_positions if 1 <= p <= len(current)}
        kept = [t for i, t in enumerate(current, start=1) if i not in remove]
        return {
            "kept": kept,
            "pending": plan.add,
            "reference_query": plan.reference_query,
            "summary": plan.summary,
            "round": state.get("round", 0) + 1,
            "stats": _bump(state, llm_calls=1, suggested=len(plan.add)),
        }

    def after_plan(state: AgentState) -> str:
        return "reference" if state.get("reference_query") else "verify"

    def reference(state: AgentState) -> dict[str, Any]:
        query = state["reference_query"] or ""
        notes = list(state.get("notes", []))
        candidates: list[TrackRef] = []
        ref_name = ""
        for playlist in spotify.search_playlists(query, limit=5):
            pid = playlist.get("id")
            if not pid:
                continue
            found: list[TrackRef] = []
            for page in spotify.playlist_tracks(pid):
                for item in page.get("items", []):
                    obj = (item or {}).get("track", (item or {}).get("item"))
                    m = to_match(obj) if isinstance(obj, dict) else None
                    if m:
                        found.append(
                            TrackRef(m.parsed.spotify_track_id, m.title, m.artist, m.parsed)
                        )
                if len(found) >= MAX_REFERENCE_TRACKS:
                    break
            if found:
                candidates, ref_name = found[:MAX_REFERENCE_TRACKS], playlist.get("name", query)
                break  # first playlist we can actually read wins

        if not candidates:
            notes.append(f"Couldn't find a readable Spotify playlist for '{query}'.")
            return {"notes": notes}

        req = state["request"]
        want = max(math.ceil(req.target_ms / AVG_TRACK_MS) // 3, 3)
        picks = llm.pick_from_reference(
            ReferenceContext(
                request=req,
                profile=state["profile"],
                feedback=state["feedback"],
                reference_name=ref_name,
                candidates=[(c.artist, c.title) for c in candidates],
                count=want,
            )
        )
        chosen: list[TrackRef] = []
        for pick in picks.picks:
            if 1 <= pick.index <= len(candidates):
                c = candidates[pick.index - 1]
                chosen.append(
                    TrackRef(c.spotify_track_id, c.title, c.artist, c.parsed, pick.reason, "reference")
                )
        notes.append(f"Drew ideas from '{ref_name}'.")
        return {
            "new": list(state.get("new", [])) + chosen,
            "notes": notes,
            "stats": _bump(state, llm_calls=1),
        }

    def verify(state: AgentState) -> dict[str, Any]:
        verified: list[TrackRef] = list(state.get("new", []))
        dropped = list(state.get("dropped", []))
        n_ok = n_missing = n_low = 0
        for s in state.get("pending", []):
            results = spotify.search_tracks(build_query(s))
            if not results:  # field-filtered search can miss; try once more, loosely
                results = spotify.search_tracks(build_loose_query(s))
            match = pick_match(s, results)
            if match is not None:
                verified.append(
                    TrackRef(
                        match.parsed.spotify_track_id, match.title, match.artist,
                        match.parsed, s.reason, s.origin,
                    )
                )  # fmt: skip
                n_ok += 1
            else:
                code = "not_found" if not results else "low_confidence"
                dropped.append({"title": s.title, "artist": s.artist, "reason": code})
                n_missing += code == "not_found"
                n_low += code == "low_confidence"
        return {
            "new": verified,
            "pending": [],
            "dropped": dropped,
            "stats": _bump(
                state, verified=n_ok, dropped_not_found=n_missing, dropped_low_confidence=n_low
            ),
        }

    def assemble(state: AgentState) -> dict[str, Any]:
        req = state["request"]
        kept, new = state.get("kept", []), state.get("new", [])

        # Collapse duplicate recordings (remaster + original, same ISRC) across everything.
        merged = kept + new
        resolution = resolve([t.parsed for t in merged])
        seen: set[str] = set()
        unique: list[TrackRef] = []
        for t in merged:
            key = resolution.aliases[t.spotify_track_id][0]
            if key in seen:
                continue
            seen.add(key)
            unique.append(t)
        removed = len(merged) - len(unique)
        kept_ids = {t.spotify_track_id for t in kept}
        kept_u = [t for t in unique if t.spotify_track_id in kept_ids]
        new_u = [t for t in unique if t.spotify_track_id not in kept_ids]

        chosen = fit_length(kept_u, new_u, req.target_ms, prefer_new=state.get("prefer_new", False))
        return {
            "chosen": chosen,
            "kept": chosen,  # becomes the base for any top-up round
            "new": [],
            "prefer_new": False,
            "stats": _bump(state, duplicates_removed=removed),
        }

    def after_assemble(state: AgentState) -> str:
        if is_short(state["chosen"], state["request"].target_ms) and state["round"] < deps.max_rounds:
            return "propose"
        return END

    g = StateGraph(AgentState)
    g.add_node("propose", propose)
    g.add_node("plan_edit", plan_edit)
    g.add_node("reference", reference)
    g.add_node("verify", verify)
    g.add_node("assemble", assemble)
    g.add_conditional_edges(START, route, {"propose": "propose", "plan_edit": "plan_edit"})
    g.add_edge("propose", "verify")
    g.add_conditional_edges("plan_edit", after_plan, {"reference": "reference", "verify": "verify"})
    g.add_edge("reference", "verify")
    g.add_edge("verify", "assemble")
    g.add_conditional_edges("assemble", after_assemble, {"propose": "propose", END: END})
    return g.compile()


@dataclass
class AgentResult:
    tracks: list[TrackRef]
    title: str | None
    summary: str
    dropped: list[dict[str, str]]
    notes: list[str]
    stats: dict[str, Any]


def _finish(state: AgentState) -> AgentResult:
    stats: dict[str, Any] = dict(state.get("stats") or {})
    suggested = stats.get("suggested", 0)
    failed = stats.get("dropped_not_found", 0) + stats.get("dropped_low_confidence", 0)
    stats["rounds"] = state.get("round", 0)
    stats["unverified_rate"] = round(failed / suggested, 4) if suggested else 0.0
    return AgentResult(
        tracks=state.get("chosen", []),
        title=state.get("title"),
        summary=state.get("summary", ""),
        dropped=state.get("dropped", []),
        notes=state.get("notes", []),
        stats=stats,
    )


def generate(deps: Deps, request: PlaylistRequest, profile: TasteProfile) -> AgentResult:
    graph = build_graph(deps)
    state = graph.invoke(
        {"mode": "generate", "request": request, "profile": profile, "kept": [], "new": []}
    )
    return _finish(state)


def refine(
    deps: Deps,
    request: PlaylistRequest,
    profile: TasteProfile,
    current: list[TrackRef],
    feedback: str,
) -> AgentResult:
    graph = build_graph(deps)
    state = graph.invoke(
        {
            "mode": "refine",
            "request": request,
            "profile": profile,
            "feedback": feedback,
            "kept": current,
            "new": [],
            "prefer_new": True,
        }
    )
    return _finish(state)

