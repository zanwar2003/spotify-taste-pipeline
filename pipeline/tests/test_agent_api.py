"""HTTP layer: auth, validation and error mapping, with a fake service (no DB, no network)."""

import pytest
from fastapi.testclient import TestClient

from tastepipe.agent.api import create_app
from tastepipe.agent.llm import LLMOutputError
from tastepipe.agent.service import (
    GenerationFailedError,
    PlaylistView,
    ProfileNotFoundError,
    ViewTrack,
)
from tastepipe.agent.store import NotFoundError
from tastepipe.spotify import SpotifyError

TOKEN = "t" * 32
PID = "3f1d2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f"
HEADERS = {"X-Internal-Token": TOKEN, "X-User-Id": "zara"}
BODY = {"source_username": "friend", "intent": "workout", "mood": "upbeat", "target_minutes": 30}


def view() -> PlaylistView:
    return PlaylistView(
        id=PID, title="Gym Fuel", status="draft", version=1, target_minutes=30, total_minutes=30.0,
        tracks=[ViewTrack(0, "a" * 22, "Song", "Artist", 200_000, "Great tempo.")],
    )  # fmt: skip


class FakeService:
    def __init__(self, raises: Exception | None = None):
        self.raises = raises
        self.calls: list[tuple] = []

    def _do(self, name, *args):
        self.calls.append((name, *args))
        if self.raises:
            raise self.raises
        return view()

    def create(self, user, req):
        return self._do("create", user, req)

    def get(self, user, pid):
        return self._do("get", user, pid)

    def refine(self, user, pid, message):
        return self._do("refine", user, pid, message)

    def approve(self, user, pid):
        return self._do("approve", user, pid)


def client(service=None) -> tuple[TestClient, FakeService]:
    svc = service or FakeService()
    return TestClient(create_app(svc, TOKEN), raise_server_exceptions=False), svc


def test_requires_the_internal_token():
    c, svc = client()
    assert c.post("/playlists", json=BODY).status_code == 401
    assert c.post("/playlists", json=BODY, headers={**HEADERS, "X-Internal-Token": "wrong"}).status_code == 401
    assert svc.calls == []


def test_requires_a_user_id():
    c, _ = client()
    r = c.post("/playlists", json=BODY, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_healthz_is_open_and_docs_are_off():
    c, _ = client()
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_create_passes_the_verified_user_and_returns_the_view():
    c, svc = client()
    r = c.post("/playlists", json=BODY, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["title"] == "Gym Fuel" and r.json()["tracks"][0]["reason"] == "Great tempo."
    name, user, req = svc.calls[0]
    assert (name, user, req.source_username) == ("create", "zara", "friend")


@pytest.mark.parametrize(
    "patch",
    [
        {"target_minutes": 0},
        {"target_minutes": 10_000},
        {"source_username": "../etc/passwd"},
        {"source_username": ""},
        {"intent": ""},
        {"mood": "x" * 500},
    ],
)
def test_invalid_playlist_requests_are_rejected_before_the_service(patch):
    c, svc = client()
    r = c.post("/playlists", json={**BODY, **patch}, headers=HEADERS)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert svc.calls == []


def test_feedback_is_length_limited_and_forwarded():
    c, svc = client()
    url = f"/playlists/{PID}/feedback"
    assert c.post(url, json={"message": "x" * 501}, headers=HEADERS).status_code == 422
    assert c.post(url, json={"message": ""}, headers=HEADERS).status_code == 422
    assert c.post(url, json={"message": "more upbeat"}, headers=HEADERS).status_code == 200
    assert svc.calls[-1][0] == "refine" and svc.calls[-1][3] == "more upbeat"


def test_playlist_id_must_be_a_uuid():
    c, _ = client()
    assert c.get("/playlists/not-a-uuid", headers=HEADERS).status_code == 422


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ProfileNotFoundError("x"), 404, "no_public_playlists"),
        (GenerationFailedError("nothing verified"), 422, "could_not_build"),
        (NotFoundError("x"), 404, "playlist_not_found"),
        (LLMOutputError("bad"), 502, "ai_unavailable"),
        (SpotifyError(500, "boom"), 502, "spotify_unavailable"),
        (ValueError("feedback must be 1-500 characters"), 422, "invalid_request"),
    ],
)
def test_service_errors_map_to_friendly_responses(exc, status, code):
    c, _ = client(FakeService(raises=exc))
    r = c.post("/playlists", json=BODY, headers=HEADERS)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert "Traceback" not in r.text and "boom" not in r.text  # internals never leak


def test_a_weak_shared_secret_is_refused_at_startup():
    with pytest.raises(ValueError):
        create_app(FakeService(), "short")
