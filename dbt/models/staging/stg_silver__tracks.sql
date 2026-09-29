select
    canonical_key as track_key,
    isrc,
    title_norm,
    artist_norm,
    version_tag,
    duration_ms,
    explicit
from {{ source('silver', 'track') }}
