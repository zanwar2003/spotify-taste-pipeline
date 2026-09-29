-- One row per source profile: a compact numeric description of their public taste.
with tracks as (
    select f.source_profile_key, f.track_key, f.playlist_appearances, t.artist_key, t.duration_ms, t.explicit
    from {{ ref('fact_taste_signal') }} f
    join {{ ref('dim_track') }} t using (track_key)
),
artists as (
    select source_profile_key, artist_key, sum(playlist_appearances) as n
    from tracks group by 1, 2
),
top_artist as (
    select source_profile_key, max(n)::numeric / sum(n) as top_artist_share, count(*) as distinct_artists
    from artists group by 1
)
select
    t.source_profile_key,
    count(*) as distinct_tracks,
    a.distinct_artists,
    round(a.top_artist_share, 3) as top_artist_share,
    round(avg(t.duration_ms) / 60000.0, 2) as avg_track_minutes,
    round(avg(t.explicit::int), 3) as explicit_share
from tracks t
join top_artist a using (source_profile_key)
group by t.source_profile_key, a.distinct_artists, a.top_artist_share
