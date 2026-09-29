select
    reason_code,
    entity,
    severity,
    count(*) as rejected_count,
    round(count(*)::numeric / sum(count(*)) over (), 4) as share_of_all
from {{ ref('stg_silver__rejected_records') }}
group by 1, 2, 3
