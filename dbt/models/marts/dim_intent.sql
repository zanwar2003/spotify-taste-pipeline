select distinct md5(intent) as intent_key, intent as intent_name
from {{ ref('stg_app__playlists') }}
