select
    spotify_track_id,
    canonical_key as track_key,
    match_reason
from {{ source('silver', 'track_alias') }}
