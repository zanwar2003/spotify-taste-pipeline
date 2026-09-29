"""Service integration tests: real Postgres, fake Spotify and fake LLM.

These COMMIT data (ingestion and playlist writes), so they are opt-in and wipe the
pipeline tables first. Run only against a disposable database:

    TASTEPIPE_TEST_ALLOW_WRITES=1 DATABASE_URL=... APP_DATABASE_URL=... pytest
"""

import os
from uuid import UUID

import psycopg
import pytest
from fakes import FakeLLM, FakeSpotify, cat, sug

from tastepipe.agent.models import EditPlan, PlaylistRequest, ProposeResult
from tastepipe.agent.service import AgentService, GenerationFailedError, ProfileNotFoundError
from tastepipe.agent.store import NotFoundError

OWNER = os.environ.get("DATABASE_URL")
APP = os.environ.get("APP_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (OWNER and APP and os.environ.get("TASTEPIPE_TEST_ALLOW_WRITES") == "1"),
    reason="set DATABASE_URL, APP_DATABASE_URL and TASTEPIPE_TEST_ALLOW_WRITES=1 (destructive)",
)

ALICE, BOB = "svc_alice", "svc_bob"
REQ = PlaylistRequest(source_username="friend", intent="workout", mood="upbeat", target_minutes=10)


@pytest.fixture(autouse=True)
def clean_db():
    with psycopg.connect(OWNER, autocommit=True) as c:
        c.execute(
            "TRUNCATE silver.review_queue, silver.playlist_track, silver.track_alias, silver.track, "
            "silver.playlist, silver.rejected_record, silver.run_log, bronze.raw_api_response, "
            "users CASCADE"
        )


def make_spotify() -> FakeSpotify:
    songs = [cat(i, f"Song {i}", "Artist") for i in range(1, 13)]
    sp = FakeSpotify(songs, playlists={"SVCTEST1": ("Friend Mix", songs[:6])})
    sp.profiles["friend"] = ["SVCTEST1"]
    return sp


def suggestions(*nums: int) -> ProposeResult:
    return ProposeResult(playlist_title="Gym Fuel", suggestions=[sug(f"Song {n}", "Artist") for n in nums])


def service(llm: FakeLLM, sp: FakeSpotify | None = None) -> tuple[AgentService, FakeSpotify]:
    sp = sp or make_spotify()
    return AgentService(owner_dsn=OWNER, app_dsn=APP, spotify=sp, llm=llm), sp  # type: ignore[arg-type]


def app_rows(user: str, sql: str, params=()):
    with psycopg.connect(APP) as c:
        c.execute("SELECT set_config('app.user_id', %s, true)", (user,))
        return c.execute(sql, params).fetchall()


def test_create_ingests_the_profile_and_persists_version_one():
    svc, _sp = service(FakeLLM([suggestions(1, 2, 3)]))
    view = svc.create(ALICE, REQ)

    assert view.title == "Gym Fuel" and view.version == 1 and view.status == "draft"
    assert [t.title for t in view.tracks] == ["Song 1", "Song 2", "Song 3"]
    assert view.stats["unverified_rate"] == 0.0

    # the friend's public data went through bronze -> silver on demand
    with psycopg.connect(OWNER) as c:
        assert c.execute("SELECT count(*) FROM silver.playlist WHERE source_profile_id='friend'").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM silver.track").fetchone() == (6,)

    # persisted as ids + reasons only: no titles or artwork in the app tables
    rows = app_rows(ALICE, "SELECT position, spotify_track_id, rationale FROM playlist_tracks ORDER BY position")
    assert [r[0] for r in rows] == [0, 1, 2] and rows[0][1] == f"{1:022d}"
    (stats,) = app_rows(ALICE, "SELECT stats FROM playlist_versions")[0]
    assert stats["suggested"] == 3 and "unverified_rate" in stats


def test_profile_is_only_ingested_once_while_fresh():
    svc, sp = service(FakeLLM([suggestions(1, 2, 3), suggestions(4, 5, 6)]))
    svc.create(ALICE, REQ)
    svc.create(ALICE, REQ)
    assert sp.user_playlist_calls == ["friend"]


def test_profile_without_public_playlists_is_a_clear_error():
    svc, _ = service(FakeLLM())
    with pytest.raises(ProfileNotFoundError):
        svc.create(ALICE, REQ.model_copy(update={"source_username": "ghost"}))


def test_nothing_verifiable_persists_nothing():
    svc, _ = service(FakeLLM([ghosts()] * 3))
    with pytest.raises(GenerationFailedError):
        svc.create(ALICE, REQ)
    assert app_rows(ALICE, "SELECT count(*) FROM playlists") == [(0,)]


def ghosts() -> ProposeResult:
    return ProposeResult(suggestions=[sug("Ghost", "Nobody")])


def test_refine_appends_a_version_and_never_edits_history():
    llm = FakeLLM(
        [suggestions(1, 2, 3)],
        edits=[EditPlan(remove_positions=[2], add=[sug("Song 9", "Artist")], summary="Swapped one.")],
    )
    svc, _ = service(llm)
    v1 = svc.create(ALICE, REQ)
    v2 = svc.refine(ALICE, UUID(v1.id), "swap the second song for something faster")

    assert v2.version == 2 and v2.summary == "Swapped one."
    assert v2.added == ["Artist - Song 9"] and v2.removed == ["Artist - Song 2"]

    versions = app_rows(ALICE, "SELECT version_no, feedback_text, diff FROM playlist_versions ORDER BY version_no")
    assert [v[0] for v in versions] == [1, 2]
    assert versions[1][1] == "swap the second song for something faster"
    assert versions[1][2] == {"added": [f"{9:022d}"], "removed": [f"{2:022d}"]}
    v1_tracks = app_rows(
        ALICE,
        "SELECT spotify_track_id FROM playlist_tracks t JOIN playlist_versions v ON v.id=t.version_id "
        "WHERE v.version_no=1 ORDER BY position",
    )
    assert [r[0] for r in v1_tracks] == [f"{i:022d}" for i in (1, 2, 3)]  # untouched


def test_other_users_cannot_read_or_change_a_playlist():
    svc, _ = service(FakeLLM([suggestions(1, 2, 3)], edits=[EditPlan()]))
    view = svc.create(ALICE, REQ)
    pid = UUID(view.id)
    with pytest.raises(NotFoundError):
        svc.get(BOB, pid)
    with pytest.raises(NotFoundError):
        svc.refine(BOB, pid, "make it mine")
    with pytest.raises(NotFoundError):
        svc.approve(BOB, pid)
    assert app_rows(ALICE, "SELECT status FROM playlists") == [("draft",)]
    assert app_rows(BOB, "SELECT count(*) FROM playlists") == [(0,)]


def test_approve_then_refine_reopens_as_a_draft():
    svc, _ = service(FakeLLM([suggestions(1, 2, 3)], edits=[EditPlan(add=[sug("Song 8", "Artist")])]))
    view = svc.create(ALICE, REQ)
    assert svc.approve(ALICE, UUID(view.id)).status == "approved"
    assert svc.refine(ALICE, UUID(view.id), "add one more").status == "draft"
    assert app_rows(ALICE, "SELECT status FROM playlists") == [("draft",)]


def test_get_rehydrates_titles_from_spotify_and_notes_missing_songs():
    svc, sp = service(FakeLLM([suggestions(1, 2, 3)]))
    view = svc.create(ALICE, REQ)
    sp.catalog = [t for t in sp.catalog if t["id"] != f"{2:022d}"]
    sp.playlists["SVCTEST1"] = ("Friend Mix", [t for t in sp.playlists["SVCTEST1"][1] if t["id"] != f"{2:022d}"])

    again = svc.get(ALICE, UUID(view.id))
    assert [t.title for t in again.tracks] == ["Song 1", "Song 3"]
    assert any("no longer available" in n for n in again.notes)


def test_deleting_a_user_removes_their_playlists_and_versions():
    svc, _ = service(FakeLLM([suggestions(1, 2, 3)]))
    svc.create(ALICE, REQ)
    with psycopg.connect(OWNER, autocommit=True) as c:
        c.execute("DELETE FROM users WHERE id = %s", (ALICE,))
        for table in ("playlists", "playlist_versions", "playlist_tracks"):
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_user_ids_are_validated():
    svc, _ = service(FakeLLM())
    with pytest.raises(ValueError):
        svc.create("bad user; drop", REQ)
