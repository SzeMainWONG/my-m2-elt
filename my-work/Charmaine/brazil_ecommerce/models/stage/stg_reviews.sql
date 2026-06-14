SELECT 
    LOWER(TRIM(CAST(review_id AS STRING))) AS review_id,
    LOWER(TRIM(CAST(order_id AS STRING))) AS order_id,
    CAST(review_score AS INT64) AS review_score,
    COALESCE(LOWER(TRIM(CAST(review_comment_title AS STRING))), 'N/A') AS review_comment_title,
    COALESCE(LOWER(TRIM(CAST(review_comment_message AS STRING))), 'N/A') AS review_comment_message,
    CAST(review_creation_date AS TIMESTAMP) AS review_creation_date,
    CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_timestamp
FROM {{ source('brazil_ecommerce', 'olist_order_reviews_dataset') }}
WHERE review_id IS NOT NULL
    AND order_id IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY review_answer_timestamp DESC) = 1
--dedup on review_id which must be unique, but in case of duplicates, keep the most recent one based on review_answer_timestamp
--order_id is not unique, as one order can have multiple reviews
--unless we want to keep only one review per order, then we can dedup on order_id instead, 
--but that would mean losing some reviews if there are multiple reviews for the same order
--alternatively, 
--we can create composite key of order_id and review_answer_timestamp and QUALIFY both to dedup, 
--assuming there are no reviews with same order_id and review_answer_timestamp