select
    source_profile_key,
    count(*) as playlist_count,
    sum(track_total) as track_total,
    min(first_seen_at) as first_seen_at,
    max(last_seen_at) as last_seen_at
from {{ ref('stg_silver__playlists') }}
where is_public
group by source_profile_key
