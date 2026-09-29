"""End-to-end silver build against a real Postgres.

Skipped unless DATABASE_URL is set. Every test runs inside a transaction that is
rolled back (TRUNCATE is transactional in Postgres), so a developer's real data
is never touched.
"""

import os

import psycopg
import pytest
from helpers import raw_item, sid

from tastepipe import bronze
from tastepipe.silver.load import QualityGateError, build_silver

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")

PLAYLIST = "37i9dQZF1DXcBWIGoYBM5M"


@pytest.fixture()
def conn():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        c.execute(
            "TRUNCATE silver.review_queue, silver.playlist_track, silver.track_alias, "
            "silver.track, silver.playlist, silver.rejected_record, silver.run_log, "
            "bronze.raw_api_response CASCADE"
        )
        yield c
        c.rollback()


def land(conn, key, payload):
    bronze.land(
        conn, source="spotify", endpoint="test", request_key=key, http_status=200, payload=payload
    )


def land_fixture(conn):
    land(
        conn,
        "user:zara:page:0",
        {
            "items": [
                {"id": PLAYLIST, "owner": {"id": "zara"}, "public": True, "tracks": {"total": 6}}
            ]
        },
    )
    deleted = {"added_at": None, "is_local": False, "track": None}
    local = raw_item(4, name="My Demo")
    local["is_local"] = True
    land(
        conn,
        f"playlist:{PLAYLIST}:page:0",
        {
            "offset": 0,
            "items": [
                raw_item(1, name="Under Pressure", isrc="GBUM71029601", duration_ms=248_000),
                raw_item(
                    2,
                    name="Under Pressure - Remastered 2011",
                    isrc="GBUM71100001",
                    duration_ms=249_000,
                ),
                raw_item(3, name="Under Pressure - Live", isrc="GBUM71300002", duration_ms=250_000),
                deleted,
                local,
                raw_item(6, name="Other Song", artist="Someone", isrc="bad-isrc"),
            ],
            "next": None,
        },
    )


def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_build_silver_end_to_end(conn):
    land_fixture(conn)
    s = build_silver(conn, commit=False)

    assert (s.status, s.items_in, s.items_rejected, s.warnings) == ("ok", 7, 2, 1)
    assert s.reject_reasons == {"NULL_TRACK": 1, "LOCAL_TRACK": 1}
    assert s.canonical_tracks == 3 and s.aliases_merged == 1

    # remaster merged into the studio cut; live stays separate
    assert scalar(conn, "SELECT count(DISTINCT canonical_key) FROM silver.track_alias") == 3
    merged = conn.execute(
        "SELECT count(*) FROM silver.track_alias a JOIN silver.track_alias b "
        "ON a.canonical_key = b.canonical_key AND a.spotify_track_id < b.spotify_track_id"
    ).fetchone()[0]
    assert merged == 1

    # positions keep the item's original index even when neighbours were rejected
    positions = [
        r[0]
        for r in conn.execute("SELECT position FROM silver.playlist_track ORDER BY position")
    ]
    assert positions == [0, 1, 2, 5]

    # quarantine keeps the reason; a bad ISRC is a warning, not a rejection
    rows = conn.execute(
        "SELECT reason_code, severity FROM silver.rejected_record ORDER BY reason_code"
    ).fetchall()
    assert rows == [
        ("BAD_ISRC", "warning"),
        ("LOCAL_TRACK", "error"),
        ("NULL_TRACK", "error"),
    ]
    assert scalar(conn, "SELECT count(*) FROM silver.track WHERE isrc IS NULL") == 1
    assert scalar(conn, "SELECT status FROM silver.run_log") == "ok"


def test_rerunning_is_idempotent(conn):
    land_fixture(conn)
    build_silver(conn, commit=False)

    def snapshot():
        return {
            t: scalar(conn, f"SELECT count(*) FROM silver.{t}")
            for t in ("track", "track_alias", "playlist", "playlist_track", "rejected_record")
        }

    first = snapshot()
    build_silver(conn, commit=False)
    assert snapshot() == first
    assert scalar(conn, "SELECT count(*) FROM silver.run_log") == 2


def test_quality_gate_aborts_and_leaves_silver_untouched(conn):
    land_fixture(conn)
    build_silver(conn, commit=False)
    before = scalar(conn, "SELECT count(*) FROM silver.track")

    # Upstream "changes shape": the same page now contains only junk.
    land(conn, f"playlist:{PLAYLIST}:page:0", {"offset": 0, "items": [None] * 10, "next": None})
    with pytest.raises(QualityGateError):
        build_silver(conn, max_reject_rate=0.5, commit=False)

    assert scalar(conn, "SELECT count(*) FROM silver.track") == before
    assert scalar(conn, "SELECT status FROM silver.run_log ORDER BY id DESC LIMIT 1") == "aborted"


def test_review_queue_flags_near_matches(conn):
    land(
        conn,
        f"playlist:{PLAYLIST}:page:0",
        {
            "offset": 0,
            "items": [
                raw_item(1, name="Dont Stop Believing", isrc="AAAA00000001"),
                raw_item(2, name="Dont Stop Believin", isrc="AAAA00000002"),
            ],
        },
    )
    s = build_silver(conn, commit=False)
    assert s.canonical_tracks == 2 and s.review_pairs == 1
    assert scalar(conn, "SELECT reason FROM silver.review_queue") == "similar_title"
    assert sid(1) != sid(2)
