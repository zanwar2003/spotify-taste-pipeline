select distinct md5(mood) as mood_key, mood as mood_name
from {{ ref('stg_app__playlists') }}
