SELECT 
    * EXCEPT(review_id),
    review_id AS id

FROM {{ ref('stg_reviews') }}
--WHERE review_id IS NOT NULL
--    AND order_id IS NOT NULL
--QUALIFY ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY review_answer_timestamp DESC) = 1
--QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY review_answer_timestamp DESC) = 1