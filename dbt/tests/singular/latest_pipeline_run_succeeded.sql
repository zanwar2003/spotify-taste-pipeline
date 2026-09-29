{{ config(severity='warn') }}
select run_id, status from {{ ref('mart_pipeline_quality') }}
where run_id = (select max(run_id) from {{ ref('mart_pipeline_quality') }}) and status <> 'ok'
