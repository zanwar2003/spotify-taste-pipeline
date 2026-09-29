-- Third-party usernames and playlist owners are deliberately not carried into gold:
-- profiles are identified only by a hash.
select
    spotify_playlist_id as source_playlist_id,
    is_public,
    track_total,
    md5(source_profile_id) as source_profile_key,
    first_seen_at,
    last_seen_at
from {{ source('silver', 'playlist') }}
