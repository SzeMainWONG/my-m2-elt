-- tests/assert_delivered_orders_have_delivery_date.sql
-- Every delivered order must have a delivery timestamp

{{ config(severity = 'warn') }}

SELECT id
FROM {{ ref('fact_orders') }}
WHERE order_status = 'delivered'
    AND order_delivered_customer_date IS NULL