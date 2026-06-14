-- tests/assert_high_value_orders_have_payment.sql
-- Orders over R$1000 should always have payment info

{{ config(severity = 'warn') }}

SELECT id
FROM {{ ref('fact_orders') }}
WHERE price > 1000
    AND has_missing_payment_info = TRUE