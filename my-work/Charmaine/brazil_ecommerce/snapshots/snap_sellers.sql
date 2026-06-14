-- snapshots/snap_sellers.sql

{% snapshot snap_sellers %}
{{
    config(
        target_schema='snapshots',
        unique_key='seller_id',
        strategy='check',
        check_cols=['seller_id', 'seller_city', 'seller_state', 'seller_zip_code_prefix', 'zip_codes_match'],
    )
}}
SELECT * FROM {{ ref('stg_sellers') }}
{% endsnapshot %}