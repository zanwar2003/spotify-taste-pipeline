"""Build silver from bronze: parse, validate, resolve, then load idempotently.

Everything is computed in memory first. If the reject rate is above the quality
gate (a sign the upstream API changed shape) nothing is written to silver; only
an 'aborted' run_log row is recorded so the failure is visible.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .parse import Issue, ParsedTrack, parse_item
from .resolve import Resolution, resolve

PLAYLIST_PAGE_KEY = re.compile(r"^playlist:(?P<pid>[0-9A-Za-z]+):page:(?P<page>\d+)$")
PAGE_SIZE = 50
DEFAULT_MAX_REJECT_RATE = 0.5

LATEST_PAGES_SQL = """
SELECT DISTINCT ON (request_key) id, request_key, endpoint, payload
  FROM bronze.raw_api_response
 WHERE source = 'spotify' AND http_status = 200
 ORDER BY request_key, fetched_at DESC, id DESC
"""


class QualityGateError(RuntimeError):
    """Raised when too many records were rejected to trust this run."""


@dataclass
class Rejection:
    bronze_id: int
    item_index: int
    entity: str
    issue: Issue
    raw: Any


@dataclass
class PlaylistRow:
    spotify_playlist_id: str
    owner_spotify_id: str | None
    is_public: bool | None
    track_total: int | None
    source_profile_id: str | None = None


@dataclass
class Placement:
    spotify_playlist_id: str
    position: int
    track: ParsedTrack


@dataclass
class Extracted:
    playlists: list[PlaylistRow] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    items_in: int = 0

    @property
    def errors(self) -> list[Rejection]:
        return [r for r in self.rejections if r.issue.severity == "error"]

    @property
    def warnings(self) -> list[Rejection]:
        return [r for r in self.rejections if r.issue.severity == "warning"]


@dataclass
class RunSummary:
    status: str
    items_in: int
    items_valid: int
    items_rejected: int
    warnings: int
    canonical_tracks: int
    aliases_merged: int
    review_pairs: int
    reject_rate: float
    reject_reasons: dict[str, int]


def extract(pages: list[dict[str, Any]]) -> Extracted:
    """Pure function: bronze pages in, validated rows and rejections out."""
    out = Extracted()
    for page in pages:
        payload = page["payload"]
        key = page["request_key"]
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            out.items_in += 1
            out.rejections.append(
                Rejection(page["id"], 0, "playlist", Issue("SCHEMA_ERROR", "error", "no items[]"), None)
            )
            continue

        if key.startswith("user:"):
            profile = key.split(":")[1]
            for idx, item in enumerate(items):
                out.items_in += 1
                pid = item.get("id") if isinstance(item, dict) else None
                if not pid:
                    out.rejections.append(
                        Rejection(page["id"], idx, "playlist", Issue("MISSING_ID", "error"), item)
                    )
                    continue
                total = (item.get("tracks") or item.get("items") or {}).get("total")
                out.playlists.append(
                    PlaylistRow(
                        pid,
                        (item.get("owner") or {}).get("id"),
                        item.get("public"),
                        total if isinstance(total, int) and total >= 0 else None,
                        profile,
                    )
                )
        elif (m := PLAYLIST_PAGE_KEY.match(key)) is not None:
            base = payload.get("offset")
            base = base if isinstance(base, int) else int(m["page"]) * PAGE_SIZE
            for idx, item in enumerate(items):
                out.items_in += 1
                result = parse_item(item)
                for issue in result.issues:
                    out.rejections.append(Rejection(page["id"], idx, "track", issue, item))
                if result.track is not None:
                    out.placements.append(Placement(m["pid"], base + idx, result.track))
    return out


def summarize(extracted: Extracted, resolution: Resolution, status: str) -> RunSummary:
    errors = extracted.errors
    rate = len(errors) / extracted.items_in if extracted.items_in else 0.0
    return RunSummary(
        status=status,
        items_in=extracted.items_in,
        items_valid=extracted.items_in - len(errors),
        items_rejected=len(errors),
        warnings=len(extracted.warnings),
        canonical_tracks=len(resolution.tracks),
        aliases_merged=resolution.aliases_merged,
        review_pairs=len(resolution.review),
        reject_rate=round(rate, 4),
        reject_reasons=dict(Counter(r.issue.code for r in errors)),
    )


def _log_run(conn: psycopg.Connection, s: RunSummary) -> None:
    conn.execute(
        """INSERT INTO silver.run_log
           (status, items_in, items_valid, items_rejected, warnings, canonical_tracks,
            aliases_merged, review_pairs, reject_rate, reject_reasons)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            s.status, s.items_in, s.items_valid, s.items_rejected, s.warnings,
            s.canonical_tracks, s.aliases_merged, s.review_pairs, s.reject_rate,
            Jsonb(s.reject_reasons),
        ),
    )  # fmt: skip


def build_silver(
    conn: psycopg.Connection,
    max_reject_rate: float = DEFAULT_MAX_REJECT_RATE,
    *,
    commit: bool = True,
) -> RunSummary:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(LATEST_PAGES_SQL)
        pages = cur.fetchall()

    extracted = extract(pages)
    resolution = resolve([p.track for p in extracted.placements])

    summary = summarize(extracted, resolution, "ok")
    if summary.reject_rate > max_reject_rate:
        summary.status = "aborted"
        _log_run(conn, summary)
        if commit:
            conn.commit()
        raise QualityGateError(
            f"reject rate {summary.reject_rate:.1%} exceeds {max_reject_rate:.0%}; "
            f"silver left unchanged. Reasons: {summary.reject_reasons}"
        )

    _write(conn, extracted, resolution)
    _log_run(conn, summary)
    if commit:
        conn.commit()
    return summary


def _write(conn: psycopg.Connection, extracted: Extracted, resolution: Resolution) -> None:
    with conn.cursor() as cur:
        # quarantine (append-only; unique key makes reruns no-ops)
        for r in extracted.rejections:
            cur.execute(
                """INSERT INTO silver.rejected_record
                   (bronze_id, item_index, entity, reason_code, severity, detail, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (bronze_id, item_index, reason_code) DO NOTHING""",
                (r.bronze_id, r.item_index, r.entity, r.issue.code, r.issue.severity,
                 r.issue.detail or None, Jsonb(r.raw) if r.raw is not None else None),
            )  # fmt: skip

        for p in extracted.playlists:
            cur.execute(
                """INSERT INTO silver.playlist
                   (spotify_playlist_id, owner_spotify_id, is_public, track_total, source_profile_id)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (spotify_playlist_id) DO UPDATE
                     SET owner_spotify_id = EXCLUDED.owner_spotify_id,
                         is_public = EXCLUDED.is_public,
                         track_total = EXCLUDED.track_total,
                         source_profile_id = EXCLUDED.source_profile_id,
                         last_seen_at = now()""",
                (p.spotify_playlist_id, p.owner_spotify_id, p.is_public, p.track_total,
                 p.source_profile_id),
            )

        # Playlists whose tracks we have but whose listing page we did not ingest.
        known = {p.spotify_playlist_id for p in extracted.playlists}
        for pid in {pl.spotify_playlist_id for pl in extracted.placements} - known:
            cur.execute(
                "INSERT INTO silver.playlist (spotify_playlist_id) VALUES (%s) "
                "ON CONFLICT DO NOTHING",
                (pid,),
            )

        for t in resolution.tracks.values():
            cur.execute(
                """INSERT INTO silver.track
                   (canonical_key, isrc, title_norm, artist_norm, version_tag, duration_ms, explicit)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (canonical_key) DO UPDATE
                     SET isrc = EXCLUDED.isrc, title_norm = EXCLUDED.title_norm,
                         artist_norm = EXCLUDED.artist_norm, version_tag = EXCLUDED.version_tag,
                         duration_ms = EXCLUDED.duration_ms, explicit = EXCLUDED.explicit,
                         updated_at = now()""",
                (t.canonical_key, t.isrc, t.title_norm, t.artist_norm, t.version_tag,
                 t.duration_ms, t.explicit),
            )  # fmt: skip

        for tid, (key, reason) in resolution.aliases.items():
            cur.execute(
                """INSERT INTO silver.track_alias (spotify_track_id, canonical_key, match_reason)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (spotify_track_id) DO UPDATE
                     SET canonical_key = EXCLUDED.canonical_key,
                         match_reason = EXCLUDED.match_reason""",
                (tid, key, reason),
            )

        # Replace each reloaded playlist's contents wholesale so removed tracks disappear.
        by_playlist: dict[str, list[Placement]] = {}
        for pl in extracted.placements:
            by_playlist.setdefault(pl.spotify_playlist_id, []).append(pl)
        for pid, placements in by_playlist.items():
            cur.execute("DELETE FROM silver.playlist_track WHERE spotify_playlist_id = %s", (pid,))
            for pl in placements:
                cur.execute(
                    """INSERT INTO silver.playlist_track
                       (spotify_playlist_id, position, spotify_track_id, added_at)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (spotify_playlist_id, position) DO NOTHING""",
                    (pid, pl.position, pl.track.spotify_track_id, pl.track.added_at),
                )

        # The review queue reflects the current state, so rebuild it.
        cur.execute("DELETE FROM silver.review_queue")
        for rp in resolution.review:
            cur.execute(
                "INSERT INTO silver.review_queue (key_a, key_b, score, reason) VALUES (%s,%s,%s,%s)",
                (rp.key_a, rp.key_b, rp.score, rp.reason),
            )

        # Drop recordings that no alias points to any more (e.g. after a re-cluster).
        cur.execute(
            "DELETE FROM silver.track t WHERE NOT EXISTS "
            "(SELECT 1 FROM silver.track_alias a WHERE a.canonical_key = t.canonical_key)"
        )
