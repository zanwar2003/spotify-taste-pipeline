select version_id, spotify_track_id
from {{ ref('stg_app__playlist_tracks') }}
group by 1, 2
having count(*) > 1
