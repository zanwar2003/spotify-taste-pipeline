-- Every playlist's versions must be numbered 1..n with no gaps.
select playlist_id
from {{ ref('fact_playlist_version') }}
group by 1
having min(version_no) <> 1 or max(version_no) <> count(*)
