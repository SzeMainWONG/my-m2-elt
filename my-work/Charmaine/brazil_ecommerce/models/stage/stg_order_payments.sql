SELECT
    TRIM(CAST(order_id AS STRING))        AS order_id,
    CAST(payment_sequential AS INT64)     AS payment_sequential,
    LOWER(TRIM(CAST(payment_type AS STRING))) AS payment_type,
    CAST(payment_installments AS INT64)   AS payment_installments,
    CAST(payment_value AS FLOAT64)        AS payment_value,
    --AGGREGATION
    SUM(payment_value) OVER (PARTITION BY order_id) AS total_paid

FROM {{ source('brazil_ecommerce', 'olist_order_payments_dataset') }}
WHERE order_id IS NOT NULL
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY payment_sequential DESC  -- keep last payment attempt
) = 1