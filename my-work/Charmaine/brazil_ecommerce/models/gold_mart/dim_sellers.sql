WITH joined AS (
    SELECT
        seller_id AS id,
        seller_zip_code_prefix,
        seller_city,
        seller_state,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        geolocation_zip_code_prefix,
/*
        LOWER(TRIM(CAST(seller_id AS STRING))) AS id,
        CAST(seller_zip_code_prefix AS INT64) AS seller_zip_code_prefix,
        LOWER(TRIM(CAST(seller_city AS STRING))) AS seller_city,
        LOWER(TRIM(CAST(seller_state AS STRING))) AS seller_state,
        CAST(geolocation_lat AS FLOAT64) AS geolocation_lat,
        CAST(geolocation_lng AS FLOAT64) AS geolocation_lng,
        LOWER(TRIM(CAST(geolocation_city AS STRING))) AS geolocation_city,
        LOWER(TRIM(CAST(geolocation_state AS STRING))) AS geolocation_state,
        geolocation.geolocation_zip_code_prefix AS geolocation_zip_code_prefix,
*/        
        -- Create reusable condition for zip code match
        (seller_zip_code_prefix = geolocation_zip_code_prefix) AS zip_codes_match
        
    FROM {{ ref('stg_sellers') }} sellers
    LEFT JOIN {{ ref('stg_geolocation') }} geolocation 
        ON sellers.seller_zip_code_prefix = geolocation.geolocation_zip_code_prefix
--    WHERE seller_id IS NOT NULL 
    QUALIFY ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY seller_id DESC) = 1  --dedup
)

SELECT
    id,
    seller_zip_code_prefix,

    zip_codes_match,
    
    -- Update seller_city and seller_state using geolocation data when zip codes match
    CASE WHEN zip_codes_match THEN geolocation_city ELSE seller_city END AS seller_city,
    CASE WHEN zip_codes_match THEN geolocation_state ELSE seller_state END AS seller_state,
    
 FROM joined
