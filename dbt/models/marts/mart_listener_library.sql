select
    l.listener_key,
    count(f.playlist_id) as playlists,
    count(*) filter (where f.status in ('approved', 'exported')) as approved,
    count(*) filter (where f.is_favorite) as favorites,
    count(*) filter (where f.is_exported) as exported,
    coalesce(round(avg(f.version_count), 2), 0) as avg_versions
from {{ ref('dim_listener') }} l
left join {{ ref('fact_playlist_request') }} f using (listener_key)
group by 1
