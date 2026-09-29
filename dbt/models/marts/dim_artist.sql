select distinct
    md5(artist_norm) as artist_key,
    artist_norm as artist_name_norm
from {{ ref('stg_silver__tracks') }}
