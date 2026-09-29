-- Grain: one row per track slot in a public source playlist.
-- Tracks that never resolved to a canonical track (rejected upstream) are not present.
select
    pt.source_playlist_id,
    pt.position,
    p.source_profile_key,
    a.track_key,
    {{ date_key('pt.added_at') }} as added_date_key
from {{ ref('stg_silver__playlist_tracks') }} pt
join {{ ref('stg_silver__playlists') }} p using (source_playlist_id)
join {{ ref('stg_silver__track_aliases') }} a using (spotify_track_id)
where p.is_public
