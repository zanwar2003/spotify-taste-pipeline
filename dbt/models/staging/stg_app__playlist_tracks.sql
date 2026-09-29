select
    version_id,
    position,
    spotify_track_id,
    isrc,
    rationale is not null as has_rationale
from {{ source('app', 'playlist_tracks') }}
