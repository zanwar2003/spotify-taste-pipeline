select
    track_key,
    isrc,
    md5(artist_norm) as artist_key,
    title_norm,
    version_tag,
    duration_ms,
    explicit
from {{ ref('stg_silver__tracks') }}
