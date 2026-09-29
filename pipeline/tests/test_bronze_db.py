"""Integration test against a real Postgres. Skipped unless DATABASE_URL is set."""

import os

import psycopg
import pytest

from tastepipe import bronze

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


def test_landing_same_payload_twice_is_idempotent():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        kwargs = {
            "source": "spotify",
            "endpoint": "users/{id}/playlists",
            "request_key": "test:idempotency",
            "http_status": 200,
            "payload": {"items": [{"id": "x"}], "next": None},
        }
        first = bronze.land(conn, **kwargs)
        second = bronze.land(conn, **kwargs)
        conn.rollback()
    assert second is False
    assert first in (True, False)  # False only if a prior run committed the same row
