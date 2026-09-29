-- Is the agent's output trustworthy? Verification rate, dropped suggestions and cost per version.
select
    created_date_key as date_key,
    count(*) as versions,
    sum(suggested) as suggested,
    sum(verified) as verified,
    sum(dropped_not_found) as dropped_not_found,
    sum(dropped_low_confidence) as dropped_low_confidence,
    round(sum(verified)::numeric / nullif(sum(suggested), 0), 3) as verify_rate,
    round(avg(llm_calls), 2) as avg_llm_calls,
    round(avg(rounds), 2) as avg_rounds
from {{ ref('fact_playlist_version') }}
group by 1
