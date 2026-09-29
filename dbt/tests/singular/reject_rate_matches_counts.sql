select run_id from {{ ref('mart_pipeline_quality') }}
where recomputed_reject_rate is not null and abs(recomputed_reject_rate - reject_rate) > 0.0001
