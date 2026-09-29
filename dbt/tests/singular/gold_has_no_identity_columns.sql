-- Privacy guard: none of these columns may ever appear in the gold schema.
select table_name, column_name
from information_schema.columns
where table_schema = 'gold'
  and column_name in ('refresh_token_enc', 'display_name', 'feedback_text', 'owner_id',
                      'owner_spotify_id', 'title', 'source_profile_id', 'rationale', 'raw')
