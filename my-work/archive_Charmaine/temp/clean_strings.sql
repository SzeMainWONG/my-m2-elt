-- macros/clean_strings.sql

{% macro clean_string_column(column_name, null_placeholders=none) %}
    {% set default_placeholders = ['null', 'n/a', 'none', 'missing', 'unknown', ''] %}
    {% set placeholders = null_placeholders or default_placeholders %}
    
    NULLIF(
        TRIM(LOWER({{ column_name }})),
        {{ placeholders[0] if placeholders|length > 0 else 'null' }}
    )
{% endmacro %}

{% macro standardize_timestamp(column_name, format='auto') %}
    {% if format == 'auto' %}
        SAFE_CAST({{ column_name }} AS TIMESTAMP)
    {% else %}
        PARSE_TIMESTAMP('{{ format }}', {{ column_name }})
    {% endif %}
{% endmacro %}

{% macro clean_numeric(column_name, min_val=none, max_val=none) %}
    CASE
        WHEN {{ column_name }} IS NULL THEN NULL
        WHEN {{ column_name }} = -999 THEN NULL  -- Special missing code
        WHEN {{ column_name }} < 0 THEN NULL
        {% if min_val %}
            WHEN {{ column_name }} < {{ min_val }} THEN NULL
        {% endif %}
        {% if max_val %}
            WHEN {{ column_name }} > {{ max_val }} THEN NULL
        {% endif %}
        ELSE {{ column_name }}
    END
{% endmacro %}