select
    to_char(d, 'YYYYMMDD')::int as date_key,
    d::date as full_date,
    extract(year from d)::int as year,
    extract(month from d)::int as month,
    to_char(d, 'YYYY-MM') as year_month,
    extract(isodow from d)::int as iso_weekday,
    extract(isodow from d) >= 6 as is_weekend
from generate_series('2024-01-01'::date, '2030-12-31'::date, interval '1 day') as d
