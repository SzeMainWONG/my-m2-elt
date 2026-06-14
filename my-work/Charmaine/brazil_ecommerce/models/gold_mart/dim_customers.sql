WITH joined AS (
    SELECT
        customer_id AS id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        geolocation_zip_code_prefix,
/*
        LOWER(TRIM(CAST(customer_id AS STRING))) AS id,
        CAST(customer_zip_code_prefix AS INT64) AS customer_zip_code_prefix,
        LOWER(TRIM(CAST(customer_city AS STRING))) AS customer_city,
        LOWER(TRIM(CAST(customer_state AS STRING))) AS customer_state,
        CAST(geolocation_lat AS FLOAT64) AS geolocation_lat,
        CAST(geolocation_lng AS FLOAT64) AS geolocation_lng,
        LOWER(TRIM(CAST(geolocation_city AS STRING))) AS geolocation_city,
        LOWER(TRIM(CAST(geolocation_state AS STRING))) AS geolocation_state,
        geolocation.geolocation_zip_code_prefix AS geolocation_zip_code_prefix,
*/       
        -- Create reusable condition for zip code match
        (customer_zip_code_prefix = geolocation_zip_code_prefix) AS zip_codes_match
        
    FROM {{ ref('stg_customers') }} customers
    LEFT JOIN {{ ref('stg_geolocation') }} geolocation 
        ON customers.customer_zip_code_prefix = geolocation.geolocation_zip_code_prefix
--    WHERE customer_id IS NOT NULL 
--      AND geolocation_zip_code_prefix IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY customer_id DESC) = 1    --dedup
)

SELECT
    id,
    customer_zip_code_prefix,

    zip_codes_match,
    
-- Update customer_city and customer_state using geolocation data when zip codes match
    CASE WHEN zip_codes_match THEN geolocation_city ELSE customer_city END AS customer_city,
    CASE WHEN zip_codes_match THEN geolocation_state ELSE customer_state END AS customer_state,

FROM joined