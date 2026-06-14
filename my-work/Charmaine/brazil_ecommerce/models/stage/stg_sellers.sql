SELECT
    COALESCE(LOWER(TRIM(CAST(seller_id AS STRING))), '!!') AS seller_id,
    CAST(seller_zip_code_prefix AS INT64) AS seller_zip_code_prefix,
    LOWER(TRIM(CAST(seller_city AS STRING))) AS seller_city,
    LOWER(TRIM(CAST(seller_state AS STRING))) AS seller_state
FROM {{ source('brazil_ecommerce', 'olist_sellers_dataset') }}
--WHERE seller_id IS NOT NULL //not needed since we are using COALESCE 
--                              //to replace NULL values with '!!'
QUALIFY ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY seller_id DESC) = 1 --dedup