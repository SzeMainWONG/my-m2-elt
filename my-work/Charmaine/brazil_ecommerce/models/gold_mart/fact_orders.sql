WITH joined AS (
    SELECT
        orders.order_id                                     AS id,
        orders.customer_id,
        COALESCE(orders.order_status, 'unavailable')        AS order_status,
        orders.order_purchase_timestamp,
        orders.order_approved_at,
        orders.order_delivered_carrier_date,
        orders.order_delivered_customer_date,
        orders.order_estimated_delivery_date,
        items.order_item_id,
        items.product_id,
        items.seller_id,
        items.shipping_limit_date,
        items.price,
        items.freight_value,
        payments.payment_sequential,
        COALESCE(payments.payment_type, 'not_defined')      AS payment_type,
        payments.payment_installments,
        payments.payment_value,
        payments.total_paid

    FROM {{ ref('stg_orders') }} orders
    LEFT JOIN {{ ref('stg_order_items') }}    items    ON orders.order_id = items.order_id
    LEFT JOIN {{ ref('stg_order_payments') }} payments ON orders.order_id = payments.order_id
    WHERE orders.customer_id IS NOT NULL AND orders.customer_id != ''
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY orders.order_id, COALESCE(items.order_item_id, 0)
        ORDER BY orders.customer_id
    ) = 1
),

validated_data AS (
    SELECT
        id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        order_item_id,
        product_id,
        seller_id,
        shipping_limit_date,
        CASE WHEN price <= 0        THEN NULL ELSE price         END AS price,
        CASE WHEN freight_value < 0 THEN NULL ELSE freight_value END AS freight_value,
        payment_sequential,
        payment_type,
        payment_installments,
        payment_value,
        total_paid
    FROM joined
),

quality_checks AS (
    SELECT
        *,
        CASE
            WHEN order_delivered_customer_date IS NOT NULL
                 AND order_purchase_timestamp IS NOT NULL
                 AND order_delivered_customer_date < order_purchase_timestamp
            THEN TRUE ELSE FALSE
        END AS has_invalid_delivery_date,

        CASE
            WHEN order_estimated_delivery_date IS NOT NULL
                 AND CURRENT_TIMESTAMP() > order_estimated_delivery_date
                 AND order_delivered_customer_date IS NULL
            THEN TRUE ELSE FALSE
        END AS is_overdue_delivery,

        CASE WHEN price > 10000 THEN TRUE ELSE FALSE
        END AS is_high_value_product,

        CASE
            WHEN order_delivered_customer_date IS NULL
                 AND order_status = 'delivered'
            THEN TRUE ELSE FALSE
        END AS has_missing_delivery_date,

        CASE
            WHEN order_delivered_customer_date IS NOT NULL
                 AND order_purchase_timestamp IS NOT NULL
                 AND DATE_DIFF(order_delivered_customer_date, order_purchase_timestamp, DAY) > 30
            THEN TRUE ELSE FALSE
        END AS is_long_delivery,

        CASE
            WHEN payment_type = 'not_defined' OR payment_value IS NULL
            THEN TRUE ELSE FALSE
        END AS has_missing_payment_info,

        CASE WHEN order_item_id IS NULL THEN TRUE ELSE FALSE
        END AS has_no_items

    FROM validated_data
)

SELECT
    id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value,
    --AGGREGATED FIELDS
    total_paid,
    --QUALITY CHECKS
    has_invalid_delivery_date,
    is_overdue_delivery,
    is_high_value_product,
    has_missing_delivery_date,
    is_long_delivery,
    has_missing_payment_info,
    has_no_items,
    CURRENT_TIMESTAMP() AS cleaned_at
FROM quality_checks
ORDER BY order_purchase_timestamp DESC, id