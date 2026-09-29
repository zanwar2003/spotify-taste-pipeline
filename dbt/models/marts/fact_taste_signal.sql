-- Grain: source profile x canonical track. Signal = how many of the profile's playlists hold it.
with counts as (
    select source_profile_key, track_key, count(distinct source_playlist_id) as playlist_appearances
    from {{ ref('fact_playlist_track') }}
    group by 1, 2
)
select
    source_profile_key,
    track_key,
    playlist_appearances,
    round(playlist_appearances::numeric / sum(playlist_appearances) over (partition by source_profile_key), 4) as share,
    rank() over (partition by source_profile_key order by playlist_appearances desc, track_key) as taste_rank
from counts
