from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    spotify_client_id: str
    spotify_client_secret: str
    database_url: str

    @classmethod
    def from_env(cls) -> Settings:
        missing = [
            name
            for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "DATABASE_URL")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            spotify_client_id=os.environ["SPOTIFY_CLIENT_ID"],
            spotify_client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
            database_url=os.environ["DATABASE_URL"],
        )
