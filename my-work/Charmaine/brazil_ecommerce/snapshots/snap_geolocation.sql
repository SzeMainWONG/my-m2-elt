{% snapshot snap_geolocation %}

/*
  dbt-managed SCD Type 2 history of geolocation, one row per zip prefix.

  Snapshots the staging model (NOT raw bronze): raw olist_geolocation_raw has no
  natural key (many lat/lng points per zip, loaded append-only), whereas
  stg_geolocation collapses to ONE current row per geolocation_zip_code_prefix —
  giving the unique_key a snapshot requires. Each run dbt detects changes via
  updated_at (timestamp strategy) and maintains dbt_valid_from / dbt_valid_to /
  dbt_scd_id.

  If updated_at isn't reliably bumped when lat/lng change, switch to the check
  strategy instead:
    strategy='check',
    check_cols=['geolocation_lat','geolocation_lng','geolocation_city','geolocation_state']
*/

{{
  config(
    target_schema='snapshots',
    unique_key='geolocation_zip_code_prefix',
    strategy='check',
    check_cols=['geolocation_zip_code_prefix', 'geolocation_lat','geolocation_lng','geolocation_city','geolocation_state']
  )
}}

SELECT * FROM {{ ref('stg_geolocation') }}

{% endsnapshot %}
