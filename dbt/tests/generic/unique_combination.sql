{% test unique_combination(model, columns) %}
{# Fails for every combination of `columns` that appears more than once (composite grain check). #}
select {{ columns | join(', ') }}, count(*) as occurrences
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
