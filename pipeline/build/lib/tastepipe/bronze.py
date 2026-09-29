"""Bronze layer: land raw API responses exactly as received, idempotently."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def canonical_json(payload: Any) -> str:
    """Stable serialization so identical payloads always hash identically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


INSERT_SQL = """
INSERT INTO bronze.raw_api_response
    (source, endpoint, request_key, http_status, payload, payload_sha256)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source, request_key, payload_sha256) DO NOTHING
RETURNING id
"""


def land(
    conn: psycopg.Connection,
    *,
    source: str,
    endpoint: str,
    request_key: str,
    http_status: int,
    payload: Any,
) -> bool:
    """Insert one raw response. Returns True if a new row was written, False if it was a duplicate."""
    with conn.cursor() as cur:
        cur.execute(
            INSERT_SQL,
            (
                source,
                endpoint,
                request_key,
                http_status,
                Jsonb(payload),
                payload_sha256(payload),
            ),
        )
        return cur.fetchone() is not None
