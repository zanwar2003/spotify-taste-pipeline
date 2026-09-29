select
    id as run_id,
    started_at,
    status,
    items_in,
    items_valid,
    items_rejected,
    warnings,
    canonical_tracks,
    aliases_merged,
    review_pairs,
    reject_rate,
    reject_reasons
from {{ source('silver', 'run_log') }}
