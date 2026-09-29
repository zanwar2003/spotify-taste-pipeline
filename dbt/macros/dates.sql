{# All dates are UTC so facts and dim_date always agree, whatever the server timezone. #}
{% macro utc_date(ts) -%}
    (({{ ts }}) at time zone 'UTC')::date
{%- endmacro %}

{% macro date_key(ts) -%}
    to_char({{ utc_date(ts) }}, 'YYYYMMDD')::int
{%- endmacro %}

{# Free-text cleanup: trim, lowercase, collapse whitespace, empty -> 'unknown'. #}
{% macro clean_text(col) -%}
    coalesce(nullif(regexp_replace(lower(btrim({{ col }})), '\s+', ' ', 'g'), ''), 'unknown')
{%- endmacro %}
