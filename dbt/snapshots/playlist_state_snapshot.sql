{% snapshot playlist_state_snapshot %}
{{ config(unique_key='playlist_id', strategy='check', check_cols=['status', 'is_favorite', 'is_exported']) }}
select playlist_id, status, is_favorite, is_exported from {{ ref('stg_app__playlists') }}
{% endsnapshot %}
