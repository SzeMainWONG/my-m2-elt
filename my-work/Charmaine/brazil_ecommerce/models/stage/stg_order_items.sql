SELECT
    TRIM(CAST(order_id AS STRING))    AS order_id,
    CAST(order_item_id AS INT64)      AS order_item_id,
    TRIM(CAST(product_id AS STRING))  AS product_id,
    TRIM(CAST(seller_id AS STRING))   AS seller_id,
    CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
    CAST(price AS FLOAT64)            AS price,
    CAST(freight_value AS FLOAT64)    AS freight_value

FROM {{ source('brazil_ecommerce', 'olist_order_items_dataset') }}
WHERE order_id IS NOT NULL
    AND order_item_id IS NOT NULL
    AND seller_id IS NOT NULL
    AND product_id IS NOT NULL