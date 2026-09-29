-- Grain: one row per saved version of a playlist.
select
    version_id,
    playlist_id,
    listener_key,
    version_no,
    {{ date_key('created_at') }} as created_date_key,
    has_feedback,
    feedback_length,
    added_count,
    removed_count,
    suggested,
    verified,
    dropped_not_found,
    dropped_low_confidence,
    duplicates_removed,
    llm_calls,
    rounds,
    unverified_rate
from {{ ref('stg_app__playlist_versions') }}
