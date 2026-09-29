"""Minimal Spotify Web API client for reading *public* profile data.

Uses the client-credentials flow, which can only see public resources. That is
exactly the boundary we want: private playlists and listening history of other
users are never reachable.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

API_BASE = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PAGE_SIZE = 50
MAX_RETRIES = 5


class SpotifyError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Spotify API error {status}: {message}")
        self.status = status


class SpotifyClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
        sleep=time.sleep,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15.0)
        self._sleep = sleep
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        resp = self._http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if resp.status_code != 200:
            raise SpotifyError(resp.status_code, "could not obtain client-credentials token")
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def get(self, url: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """GET with bearer auth and Retry-After handling. Returns (status, json)."""
        for attempt in range(MAX_RETRIES):
            resp = self._http.get(
                url, params=params, headers={"Authorization": f"Bearer {self._ensure_token()}"}
            )
            if resp.status_code == 429:
                self._sleep(min(int(resp.headers.get("Retry-After", "1")), 30) + attempt)
                continue
            if resp.status_code in (404, 403):
                # Missing or private: a valid, recordable outcome rather than a crash.
                return resp.status_code, {}
            if resp.status_code >= 400:
                raise SpotifyError(resp.status_code, resp.text[:200])
            return resp.status_code, resp.json()
        raise SpotifyError(429, "rate limited after retries")

    def paginate(self, url: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield each page of a Spotify paging object, following `next` links."""
        page_params = {"limit": PAGE_SIZE, **(params or {})}
        next_url: str | None = url
        while next_url:
            status, body = self.get(next_url, page_params if next_url == url else None)
            if status != 200:
                return
            yield body
            next_url = body.get("next")

    def user_playlists(self, user_id: str) -> Iterator[dict[str, Any]]:
        yield from self.paginate(f"{API_BASE}/users/{user_id}/playlists")

    def playlist_tracks(self, playlist_id: str) -> Iterator[dict[str, Any]]:
        yield from self.paginate(f"{API_BASE}/playlists/{playlist_id}/tracks")

    # -- search and lookup (used to verify and display agent suggestions) -----------------

    def search_tracks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return raw track objects for a free-text query (empty list on any miss)."""
        _, body = self.get(f"{API_BASE}/search", {"q": query, "type": "track", "limit": limit})
        return [t for t in (body.get("tracks") or {}).get("items", []) if isinstance(t, dict)]

    def search_playlists(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        _, body = self.get(f"{API_BASE}/search", {"q": query, "type": "playlist", "limit": limit})
        # Spotify returns null entries for unavailable playlists; drop them.
        return [p for p in (body.get("playlists") or {}).get("items", []) if isinstance(p, dict)]

    def tracks(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch track objects by ID (batches of 50). Missing IDs are simply absent."""
        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(ids), 50):
            batch = ids[start : start + 50]
            _, body = self.get(f"{API_BASE}/tracks", {"ids": ",".join(batch)})
            for t in body.get("tracks") or []:
                if isinstance(t, dict) and t.get("id"):
                    found[t["id"]] = t
        return found
