-- dim_customer need update to handle customer zip code update to use this SCD
-- snapshots/snap_customers.sql

{% snapshot snap_customers %}
{{
    config(
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='check',
        check_cols=['customer_id', 'customer_zip_code_prefix', 'customer_city', 'customer_state', 'zip_codes_match'],
    )
}}
SELECT * FROM {{ ref('stg_customers') }}
{% endsnapshot %}