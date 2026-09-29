-- Feedback text is reduced to its length. Diff and agent stats are unpacked from jsonb.
select
    id as version_id,
    playlist_id,
    md5(owner_id) as listener_key,
    version_no,
    feedback_text is not null as has_feedback,
    coalesce(char_length(feedback_text), 0) as feedback_length,
    coalesce(jsonb_array_length(diff -> 'added'), 0) as added_count,
    coalesce(jsonb_array_length(diff -> 'removed'), 0) as removed_count,
    coalesce((stats ->> 'suggested')::int, 0) as suggested,
    coalesce((stats ->> 'verified')::int, 0) as verified,
    coalesce((stats ->> 'dropped_not_found')::int, 0) as dropped_not_found,
    coalesce((stats ->> 'dropped_low_confidence')::int, 0) as dropped_low_confidence,
    coalesce((stats ->> 'duplicates_removed')::int, 0) as duplicates_removed,
    coalesce((stats ->> 'llm_calls')::int, 0) as llm_calls,
    coalesce((stats ->> 'rounds')::int, 0) as rounds,
    coalesce((stats ->> 'unverified_rate')::numeric, 0) as unverified_rate,
    created_at
from {{ source('app', 'playlist_versions') }}
