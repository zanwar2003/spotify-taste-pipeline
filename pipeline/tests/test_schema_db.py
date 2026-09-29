"""Schema integration tests: row-level security and cascade deletes.

Needs a Postgres initialised from db/init/*.sql. Skipped unless both
DATABASE_URL (owner) and APP_DATABASE_URL (restricted app role) are set.
"""

import os

import psycopg
import pytest

OWNER = os.environ.get("DATABASE_URL")
APP = os.environ.get("APP_DATABASE_URL")

pytestmark = pytest.mark.skipif(not (OWNER and APP), reason="DATABASE_URL/APP_DATABASE_URL not set")


@pytest.fixture()
def two_users():
    with psycopg.connect(OWNER, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE id IN ('rls_alice', 'rls_bob')")
        conn.execute("INSERT INTO users (id) VALUES ('rls_alice'), ('rls_bob')")
        conn.execute(
            "INSERT INTO playlists (owner_id, title) VALUES ('rls_alice', 'A'), ('rls_bob', 'B')"
        )
    yield
    with psycopg.connect(OWNER, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE id IN ('rls_alice', 'rls_bob')")


def as_user(conn, user_id):
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))


def test_app_role_cannot_bypass_rls():
    with psycopg.connect(APP) as conn:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    assert row == (False, False)


def test_user_only_sees_own_playlists(two_users):
    with psycopg.connect(APP) as conn:
        as_user(conn, "rls_alice")
        titles = [r[0] for r in conn.execute("SELECT title FROM playlists")]
    assert titles == ["A"]


def test_no_user_context_sees_nothing(two_users):
    with psycopg.connect(APP) as conn:
        assert conn.execute("SELECT count(*) FROM playlists").fetchone() == (0,)


def test_user_cannot_write_rows_for_someone_else(two_users):
    with psycopg.connect(APP) as conn:
        as_user(conn, "rls_alice")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO playlists (owner_id, title) VALUES ('rls_bob', 'forged')")


def test_deleting_a_user_cascades_everything(two_users):
    with psycopg.connect(OWNER, autocommit=True) as conn:
        pid = conn.execute(
            "SELECT id FROM playlists WHERE owner_id = 'rls_alice'"
        ).fetchone()[0]
        vid = conn.execute(
            "INSERT INTO playlist_versions (playlist_id, owner_id, version_no)"
            " VALUES (%s, 'rls_alice', 1) RETURNING id",
            (pid,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO playlist_tracks (version_id, owner_id, position, spotify_track_id)"
            " VALUES (%s, 'rls_alice', 0, 'trk')",
            (vid,),
        )
        conn.execute("DELETE FROM users WHERE id = 'rls_alice'")
        for table in ("playlists", "playlist_versions", "playlist_tracks"):
            count = conn.execute(
                f"SELECT count(*) FROM {table} WHERE owner_id = 'rls_alice'"
            ).fetchone()[0]
            assert count == 0, table
