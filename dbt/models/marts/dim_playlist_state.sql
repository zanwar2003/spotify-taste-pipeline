-- SCD2 history of playlist status / favourite / export flags.
select
    playlist_id,
    status,
    is_favorite,
    is_exported,
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to is null as is_current
from {{ ref('playlist_state_snapshot') }}
