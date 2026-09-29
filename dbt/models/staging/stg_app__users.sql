-- Identity, display name and the encrypted refresh token never leave the app schema.
select
    md5(id) as listener_key,
    created_at as signed_up_at
from {{ source('app', 'users') }}
