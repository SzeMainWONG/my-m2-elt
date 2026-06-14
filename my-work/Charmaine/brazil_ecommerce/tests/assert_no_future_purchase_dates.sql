-- tests/assert_no_future_purchase_dates.sql
-- No order should be purchased in the future
{{ config(severity = 'warn') }}

SELECT id
FROM {{ ref('fact_orders') }}
WHERE order_purchase_timestamp > CURRENT_TIMESTAMP()