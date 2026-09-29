select
    m.mood_name,
    count(*) as playlists,
    count(*) filter (where f.status in ('approved', 'exported')) as approved,
    round(avg(f.version_count), 2) as avg_versions,
    round(avg(f.total_minutes), 1) as avg_minutes
from {{ ref('fact_playlist_request') }} f
join {{ ref('dim_mood') }} m using (mood_key)
group by 1
