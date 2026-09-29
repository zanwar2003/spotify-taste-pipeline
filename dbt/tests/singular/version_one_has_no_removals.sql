select version_id from {{ ref('fact_playlist_version') }}
where version_no = 1 and removed_count > 0
