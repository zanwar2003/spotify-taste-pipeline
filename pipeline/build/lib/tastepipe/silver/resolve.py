"""Entity resolution: collapse many Spotify track IDs into one canonical recording.

Decisions are explicit and explainable, in three tiers:

* **match**    same ISRC, or same normalized (artist, title, version) with durations
               within DURATION_TOL_MS. Merged automatically.
* **review**   near-misses (similar title, or same name with a modest duration gap).
               NOT merged; written to a review queue for a human.
* **distinct** everything else. Different version tags (live, remix, ...) never merge.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from statistics import median_low

from .parse import ParsedTrack

DURATION_TOL_MS = 3_000  # same recording: encoders and remasters differ by a second or two
REVIEW_DURATION_GAP_MS = 10_000
TITLE_REVIEW_THRESHOLD = 0.88
TITLE_REVIEW_DURATION_MS = 5_000


@dataclass(frozen=True)
class CanonicalTrack:
    canonical_key: str
    isrc: str | None
    title_norm: str
    artist_norm: str
    version_tag: str
    duration_ms: int
    explicit: bool | None


@dataclass(frozen=True)
class ReviewPair:
    key_a: str
    key_b: str
    score: float
    reason: str


@dataclass
class Resolution:
    tracks: dict[str, CanonicalTrack]
    aliases: dict[str, tuple[str, str]]  # spotify_track_id -> (canonical_key, match_reason)
    review: list[ReviewPair]

    @property
    def aliases_merged(self) -> int:
        return len(self.aliases) - len(self.tracks)


class _UnionFind:
    def __init__(self, items: list[str]):
        self._parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic: smaller ID becomes the root.
            self._parent[max(ra, rb)] = min(ra, rb)


def _name_key(artist: str, title: str, tag: str) -> str:
    return "nk:" + hashlib.sha1(f"{artist}|{title}|{tag}".encode()).hexdigest()[:20]


def resolve(tracks: list[ParsedTrack]) -> Resolution:
    # One record per Spotify ID (first occurrence wins; the same ID recurs across playlists).
    by_id: dict[str, ParsedTrack] = {}
    for t in tracks:
        by_id.setdefault(t.spotify_track_id, t)
    ids = sorted(by_id)
    uf = _UnionFind(ids)

    # match tier 1: shared ISRC
    by_isrc: dict[str, list[str]] = defaultdict(list)
    for tid in ids:
        if by_id[tid].isrc:
            by_isrc[by_id[tid].isrc].append(tid)  # type: ignore[index]
    for members in by_isrc.values():
        for other in members[1:]:
            uf.union(members[0], other)

    # match tier 2: same normalized name + version, durations chained within tolerance
    blocks: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for tid in ids:
        t = by_id[tid]
        blocks[(t.artist_norm, t.title_norm, t.version_tag)].append(tid)
    for members in blocks.values():
        members.sort(key=lambda i: (by_id[i].duration_ms, i))
        for prev, cur in pairwise(members):
            if by_id[cur].duration_ms - by_id[prev].duration_ms <= DURATION_TOL_MS:
                uf.union(prev, cur)

    clusters: dict[str, list[str]] = defaultdict(list)
    for tid in ids:
        clusters[uf.find(tid)].append(tid)

    # Assign canonical keys. Name-key clusters that share a block are numbered by duration.
    canonical: dict[str, CanonicalTrack] = {}
    aliases: dict[str, tuple[str, str]] = {}
    block_seen: Counter[tuple[str, str, str]] = Counter()

    for root in sorted(clusters, key=lambda r: (min(by_id[i].duration_ms for i in clusters[r]), r)):
        members = clusters[root]
        rep = by_id[members[0]]
        isrcs = Counter(by_id[i].isrc for i in members if by_id[i].isrc)
        chosen_isrc = min(isrcs.items(), key=lambda kv: (-kv[1], kv[0]))[0] if isrcs else None
        if chosen_isrc:
            key = f"isrc:{chosen_isrc}"
        else:
            block = (rep.artist_norm, rep.title_norm, rep.version_tag)
            block_seen[block] += 1
            n = block_seen[block]
            key = _name_key(*block) + ("" if n == 1 else f"#{n}")

        explicit_votes = Counter(by_id[i].explicit for i in members if by_id[i].explicit is not None)
        explicit = explicit_votes.most_common(1)[0][0] if explicit_votes else None
        canonical[key] = CanonicalTrack(
            canonical_key=key,
            isrc=chosen_isrc,
            title_norm=rep.title_norm,
            artist_norm=rep.artist_norm,
            version_tag=rep.version_tag,
            duration_ms=median_low(by_id[i].duration_ms for i in members),
            explicit=explicit,
        )
        for tid in members:
            if len(members) == 1:
                reason = "canonical"
            elif chosen_isrc and by_id[tid].isrc == chosen_isrc:
                reason = "same_isrc"
            else:
                reason = "normalized_match"
            aliases[tid] = (key, reason)

    return Resolution(tracks=canonical, aliases=aliases, review=_review_pairs(canonical))


def _review_pairs(tracks: dict[str, CanonicalTrack]) -> list[ReviewPair]:
    by_artist: dict[tuple[str, str], list[CanonicalTrack]] = defaultdict(list)
    for t in tracks.values():
        by_artist[(t.artist_norm, t.version_tag)].append(t)

    pairs: dict[tuple[str, str], ReviewPair] = {}
    for group in by_artist.values():
        group.sort(key=lambda t: t.canonical_key)
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                gap = abs(a.duration_ms - b.duration_ms)
                if a.title_norm == b.title_norm:
                    if gap <= REVIEW_DURATION_GAP_MS:
                        pairs[(a.canonical_key, b.canonical_key)] = ReviewPair(
                            a.canonical_key, b.canonical_key, 0.9, "same_name_duration_gap"
                        )
                    continue
                score = SequenceMatcher(None, a.title_norm, b.title_norm).ratio()
                if score >= TITLE_REVIEW_THRESHOLD and gap <= TITLE_REVIEW_DURATION_MS:
                    pairs[(a.canonical_key, b.canonical_key)] = ReviewPair(
                        a.canonical_key, b.canonical_key, round(score, 3), "similar_title"
                    )
    return sorted(pairs.values(), key=lambda p: (p.key_a, p.key_b))
