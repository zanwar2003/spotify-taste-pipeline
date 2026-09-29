select
    run_id,
    started_at,
    {{ date_key('started_at') }} as run_date_key,
    status,
    items_in,
    items_valid,
    items_rejected,
    warnings,
    canonical_tracks,
    aliases_merged,
    review_pairs,
    reject_rate,
    case when items_in > 0 then round(items_rejected::numeric / items_in, 4) end as recomputed_reject_rate,
    status = 'ok' as passed_gate
from {{ ref('stg_silver__run_log') }}
