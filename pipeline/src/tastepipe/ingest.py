"""Ingest a Spotify user's public playlists (and their tracks) into bronze.

    python -m tastepipe.ingest <spotify_username>
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

import psycopg

from . import bronze
from .config import Settings
from .spotify import SpotifyClient

log = logging.getLogger("tastepipe.ingest")


@dataclass
class IngestResult:
    playlists_seen: int = 0
    pages_written: int = 0
    pages_unchanged: int = 0

    def record(self, written: bool) -> None:
        if written:
            self.pages_written += 1
        else:
            self.pages_unchanged += 1


def ingest_user(
    spotify: SpotifyClient, conn: psycopg.Connection, username: str
) -> IngestResult:
    result = IngestResult()
    playlist_ids: list[str] = []

    for n, page in enumerate(spotify.user_playlists(username)):
        written = bronze.land(
            conn,
            source="spotify",
            endpoint="users/{id}/playlists",
            request_key=f"user:{username}:page:{n}",
            http_status=200,
            payload=page,
        )
        result.record(written)
        playlist_ids.extend(
            item["id"] for item in page.get("items", []) if item and item.get("public") is not False
        )

    result.playlists_seen = len(playlist_ids)

    for playlist_id in playlist_ids:
        for n, page in enumerate(spotify.playlist_tracks(playlist_id)):
            written = bronze.land(
                conn,
                source="spotify",
                endpoint="playlists/{id}/tracks",
                request_key=f"playlist:{playlist_id}:page:{n}",
                http_status=200,
                payload=page,
            )
            result.record(written)

    conn.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Spotify username whose public playlists to ingest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    spotify = SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret)

    with psycopg.connect(settings.database_url) as conn:
        result = ingest_user(spotify, conn, args.username)

    if result.playlists_seen == 0:
        log.warning("No public playlists found for %s", args.username)
    log.info(
        "playlists=%d pages_written=%d pages_unchanged=%d",
        result.playlists_seen,
        result.pages_written,
        result.pages_unchanged,
    )


if __name__ == "__main__":
    main()
