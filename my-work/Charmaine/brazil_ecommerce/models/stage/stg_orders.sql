SELECT
    TRIM(CAST(order_id AS STRING))      AS order_id,
    TRIM(CAST(customer_id AS STRING))   AS customer_id,
    LOWER(TRIM(CAST(order_status AS STRING))) AS order_status,
    CAST(order_purchase_timestamp AS TIMESTAMP)      AS order_purchase_timestamp,
    CAST(order_approved_at AS TIMESTAMP)             AS order_approved_at,
    CAST(order_delivered_carrier_date AS TIMESTAMP)  AS order_delivered_carrier_date,
    CAST(order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
    CAST(order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_date

FROM {{ source('brazil_ecommerce', 'olist_orders_dataset') }}
WHERE order_id IS NOT NULL
    AND customer_id IS NOT NULL
    AND TRIM(CAST(customer_id AS STRING)) != ''