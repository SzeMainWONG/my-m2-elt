SELECT 
    CAST(geolocation_lat AS FLOAT64) AS geolocation_lat,
    CAST(geolocation_lng AS FLOAT64) AS geolocation_lng,
    LOWER(TRIM(CAST(geolocation_city AS STRING))) AS geolocation_city,
    LOWER(TRIM(CAST(geolocation_state AS STRING))) AS geolocation_state,
    CAST(geolocation_zip_code_prefix AS INT64) AS geolocation_zip_code_prefix --unique identifier
FROM {{ source('brazil_ecommerce', 'olist_geolocation_dataset') }}
WHERE geolocation_zip_code_prefix IS NOT NULL
--QUALIFY ROW_NUMBER() OVER (
--    PARTITION BY geolocation_zip_code_prefix
--    ORDER BY updated_at DESC--, _sdc_batched_at DESC
--) = 1