"""HTTP API for the playlist agent. Only the Next.js server calls this.

Auth model: the browser never talks to this service. The web server verifies the
user's session cookie, then calls here with a shared secret (X-Internal-Token) and the
verified Spotify user ID (X-User-Id). Bind to 127.0.0.1 and keep the token secret.
"""

import hmac
import logging
import os
from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..spotify import SpotifyError
from .llm import LLMOutputError
from .models import PlaylistRequest
from .service import AgentService, GenerationFailedError, ProfileNotFoundError
from .store import NotFoundError

log = logging.getLogger("tastepipe.agent.api")


class FeedbackBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(service: AgentService, internal_token: str) -> FastAPI:
    if len(internal_token) < 16:
        raise ValueError("AGENT_INTERNAL_TOKEN must be at least 16 characters")

    app = FastAPI(title="Taste Pipeline agent", docs_url=None, redoc_url=None, openapi_url=None)

    def authed_user(
        x_internal_token: Annotated[str | None, Header()] = None,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> str:
        if not x_internal_token or not hmac.compare_digest(x_internal_token, internal_token):
            raise HTTPException(status_code=401, detail="unauthorized")
        if not x_user_id:
            raise HTTPException(status_code=401, detail="missing user")
        return x_user_id

    User = Annotated[str, Depends(authed_user)]

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return error(exc.status_code, "unauthorized" if exc.status_code == 401 else "error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return error(422, "invalid_request", "Check the playlist details and try again.")

    @app.exception_handler(ValueError)
    async def _value(_: Request, exc: ValueError):
        return error(422, "invalid_request", str(exc))

    @app.exception_handler(ProfileNotFoundError)
    async def _no_profile(_: Request, exc: ProfileNotFoundError):
        return error(
            404,
            "no_public_playlists",
            "That profile has no public playlists we can read. Try another username.",
        )

    @app.exception_handler(GenerationFailedError)
    async def _failed(_: Request, exc: GenerationFailedError):
        return error(422, "could_not_build", f"Couldn't build that playlist: {exc}. Try different wording.")

    @app.exception_handler(NotFoundError)
    async def _missing(_: Request, exc: NotFoundError):
        return error(404, "playlist_not_found", "That playlist doesn't exist in your library.")

    @app.exception_handler(LLMOutputError)
    async def _llm(_: Request, exc: LLMOutputError):
        log.error("LLM output error: %s", exc)
        return error(502, "ai_unavailable", "The playlist assistant hit a problem. Please try again.")

    @app.exception_handler(SpotifyError)
    async def _spotify(_: Request, exc: SpotifyError):
        log.error("Spotify error: %s", exc)
        return error(502, "spotify_unavailable", "Spotify isn't responding right now. Try again shortly.")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/playlists")
    def create_playlist(body: PlaylistRequest, user: User):
        return asdict(service.create(user, body))

    @app.get("/playlists/{playlist_id}")
    def get_playlist(playlist_id: UUID, user: User):
        return asdict(service.get(user, playlist_id))

    @app.post("/playlists/{playlist_id}/feedback")
    def feedback(playlist_id: UUID, body: FeedbackBody, user: User):
        return asdict(service.refine(user, playlist_id, body.message))

    @app.post("/playlists/{playlist_id}/approve")
    def approve(playlist_id: UUID, user: User):
        return asdict(service.approve(user, playlist_id))

    return app


def create_default_app() -> FastAPI:
    """Build the real service from environment variables."""
    from ..config import Settings
    from .llm import AnthropicLLM

    settings = Settings.from_env()
    app_dsn = os.environ.get("APP_DATABASE_URL")
    token = os.environ.get("AGENT_INTERNAL_TOKEN")
    if not app_dsn or not token:
        raise RuntimeError("APP_DATABASE_URL and AGENT_INTERNAL_TOKEN must be set")
    from ..spotify import SpotifyClient

    service = AgentService(
        owner_dsn=settings.database_url,
        app_dsn=app_dsn,
        spotify=SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret),
        llm=AnthropicLLM(),
    )
    return create_app(service, token)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(create_default_app(), host="127.0.0.1", port=int(os.environ.get("AGENT_PORT", "8000")))


if __name__ == "__main__":
    main()
