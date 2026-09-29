-- `raw` (the quarantined Spotify payload) is intentionally left out of the warehouse layers.
select
    id as rejected_id,
    bronze_id,
    item_index,
    entity,
    reason_code,
    severity,
    rejected_at
from {{ source('silver', 'rejected_record') }}
