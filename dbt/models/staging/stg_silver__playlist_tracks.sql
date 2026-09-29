select
    spotify_playlist_id as source_playlist_id,
    position,
    spotify_track_id,
    added_at
from {{ source('silver', 'playlist_track') }}
