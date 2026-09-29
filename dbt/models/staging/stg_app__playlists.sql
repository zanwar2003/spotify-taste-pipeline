-- Titles are user-written text and are dropped; mood and intent are cleaned so
-- "Upbeat", "upbeat " and "UPBEAT" become one value.
select
    id as playlist_id,
    md5(owner_id) as listener_key,
    {{ clean_text('mood') }} as mood,
    {{ clean_text('intent') }} as intent,
    target_length_min as target_minutes,
    md5(source_profile_id) as source_profile_key,
    status::text as status,
    is_favorite,
    spotify_playlist_id is not null as is_exported,
    created_at,
    updated_at
from {{ source('app', 'playlists') }}
