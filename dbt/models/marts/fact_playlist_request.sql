-- Grain: one row per playlist a listener asked for (latest state).
with latest as (
    select distinct on (playlist_id) version_id, playlist_id, version_no
    from {{ ref('stg_app__playlist_versions') }}
    order by playlist_id, version_no desc
),
size as (
    select
        l.playlist_id,
        count(*) as track_count,
        coalesce(sum(t.duration_ms), 0) / 60000.0 as total_minutes
    from latest l
    join {{ ref('stg_app__playlist_tracks') }} pt using (version_id)
    left join {{ ref('stg_silver__track_aliases') }} a on a.spotify_track_id = pt.spotify_track_id
    left join {{ ref('stg_silver__tracks') }} t on t.track_key = a.track_key
    group by 1
)
select
    p.playlist_id,
    p.listener_key,
    md5(p.mood) as mood_key,
    md5(p.intent) as intent_key,
    p.source_profile_key,
    {{ date_key('p.created_at') }} as created_date_key,
    p.target_minutes,
    l.version_no as version_count,
    coalesce(s.track_count, 0) as track_count,
    round(coalesce(s.total_minutes, 0), 1) as total_minutes,
    p.status,
    p.is_favorite,
    p.is_exported
from {{ ref('stg_app__playlists') }} p
left join latest l using (playlist_id)
left join size s using (playlist_id)
