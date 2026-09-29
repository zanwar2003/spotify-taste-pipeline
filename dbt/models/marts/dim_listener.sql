select
    listener_key,
    signed_up_at,
    {{ date_key('signed_up_at') }} as signed_up_date_key
from {{ ref('stg_app__users') }}
