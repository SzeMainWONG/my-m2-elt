Here's how to implement the **exact EDA cleaning sequence** in **dbt (Data Build Tool)**:

---

## **dbt Project Structure for the Cleaning Sequence**

```
your_dbt_project/
├── models/
│   ├── staging/
│   │   ├── stg_raw_data.sql
│   │   └── stg_raw_data.yml
│   ├── intermediate/
│   │   ├── int_cleaned_data.sql
│   │   └── int_deduplicated.sql
│   └── marts/
│       └── dim_clean_table.sql
├── macros/
│   ├── clean_strings.sql
│   ├── handle_nulls.sql
│   └── validate_timestamps.sql
└── tests/
    ├── not_null_important_columns.sql
    └── unique_key_test.sql
```

---

## **Step-by-Step dbt Implementation**

### **Step 1: Staging Layer - Raw ingestion with string standardization**

```sql
-- models/staging/stg_raw_data.sql

WITH source AS (
    SELECT * FROM {{ source('raw_database', 'raw_table') }}
),

-- 2.1 Strip whitespace from all string columns
stripped AS (
    SELECT
        * EXCEPT(
            {%- for col in adapter.get_columns_in_relation(source) 
               if col.dtype in ['STRING', 'TEXT', 'VARCHAR'] %}
                {{ col.name }}{% if not loop.last %},{% endif %}
            {%- endfor %}
        ),
        {%- for col in adapter.get_columns_in_relation(source) 
           if col.dtype in ['STRING', 'TEXT', 'VARCHAR'] %}
            TRIM(CAST({{ col.name }} AS STRING)) AS {{ col.name }}{% if not loop.last %},{% endif %}
        {%- endfor %}
    FROM source
),

-- 2.2 Convert to consistent case for categorical columns
standardized_case AS (
    SELECT
        *,
        -- Lowercase specific categorical columns
        LOWER(TRIM(category)) AS category_clean,
        LOWER(TRIM(status)) AS status_clean,
        LOWER(TRIM(country)) AS country_clean,
        -- Keep original case for free text
        customer_name,
        comments
    FROM stripped
),

-- 2.3 Replace common null placeholders with actual NULL
null_placeholders_replaced AS (
    SELECT
        * EXCEPT(category_clean, status_clean, country_clean),
        -- Replace null placeholders in string columns
        NULLIF(category_clean, 'null') AS category_clean,
        NULLIF(status_clean, 'N/A') AS status_clean,
        NULLIF(country_clean, 'unknown') AS country_clean,
        NULLIF(TRIM(customer_name), '') AS customer_name,
        -- Handle multiple placeholders
        CASE 
            WHEN LOWER(TRIM(comments)) IN ('null', 'n/a', 'none', 'missing', '') 
            THEN NULL 
            ELSE comments 
        END AS comments
    FROM standardized_case
)

SELECT * FROM null_placeholders_replaced
```

---

### **Step 2: Staging Configuration**

```yaml
# models/staging/stg_raw_data.yml

version: 2

models:
  - name: stg_raw_data
    description: "Staging model with string standardization and null placeholder handling"
    columns:
      - name: category_clean
        tests:
          - accepted_values:
              values: ['electronics', 'clothing', 'books', 'home']
      - name: status_clean
        tests:
          - not_null:
              severity: warn
      - name: customer_name
        tests:
          - not_null
      - name: order_date
        tests:
          - not_null

sources:
  - name: raw_database
    tables:
      - name: raw_table
        loaded_at_field: _loaded_at
```

---

### **Step 3: Macro for reusable string cleaning**

```sql
-- macros/clean_strings.sql

{% macro clean_string_column(column_name, null_placeholders=none) %}
    {% set default_placeholders = ['null', 'n/a', 'none', 'missing', 'unknown', ''] %}
    {% set placeholders = null_placeholders or default_placeholders %}
    
    NULLIF(
        TRIM(LOWER({{ column_name }})),
        {{ placeholders[0] if placeholders|length > 0 else 'null' }}
    )
{% endmacro %}

{% macro standardize_timestamp(column_name, format='auto') %}
    {% if format == 'auto' %}
        SAFE_CAST({{ column_name }} AS TIMESTAMP)
    {% else %}
        PARSE_TIMESTAMP('{{ format }}', {{ column_name }})
    {% endif %}
{% endmacro %}

{% macro clean_numeric(column_name, min_val=none, max_val=none) %}
    CASE
        WHEN {{ column_name }} IS NULL THEN NULL
        WHEN {{ column_name }} = -999 THEN NULL  -- Special missing code
        WHEN {{ column_name }} < 0 THEN NULL
        {% if min_val %}
            WHEN {{ column_name }} < {{ min_val }} THEN NULL
        {% endif %}
        {% if max_val %}
            WHEN {{ column_name }} > {{ max_val }} THEN NULL
        {% endif %}
        ELSE {{ column_name }}
    END
{% endmacro %}
```

---

### **Step 4: Intermediate - Handling nulls and duplicates**

```sql
-- models/intermediate/int_cleaned_data.sql

WITH cleaned_staging AS (
    SELECT * FROM {{ ref('stg_raw_data') }}
),

-- Step 6: Structured null handling
null_analysis AS (
    SELECT
        COUNT(*) AS total_rows,
        COUNT(customer_name) AS name_populated,
        COUNT(order_date) AS date_populated,
        COUNT(category_clean) AS category_populated,
        SUM(CASE WHEN category_clean IS NULL THEN 1 ELSE 0 END) AS null_categories
    FROM cleaned_staging
),

-- Imputation strategy
imputed AS (
    SELECT
        *,
        -- Fill categorical nulls with mode
        COALESCE(
            category_clean,
            FIRST_VALUE(category_clean) OVER (
                PARTITION BY 1 
                ORDER BY COUNT(category_clean) OVER() DESC
            )
        ) AS category_filled,
        
        -- Fill numeric nulls with median
        COALESCE(
            amount,
            PERCENTILE_CONT(0.5) OVER() 
        ) AS amount_filled,
        
        -- Add null flags for ML
        CASE WHEN category_clean IS NULL THEN 1 ELSE 0 END AS category_is_null_flag,
        CASE WHEN amount IS NULL THEN 1 ELSE 0 END AS amount_is_null_flag
        
    FROM cleaned_staging
),

-- Step 8: Data type validation
typed_data AS (
    SELECT
        -- Convert to proper types
        SAFE_CAST(order_id AS INT64) AS order_id,
        customer_name,
        category_filled AS category,
        status_clean AS status,
        country_clean AS country,
        
        -- Timestamp handling
        SAFE_CAST(order_date AS DATE) AS order_date,
        PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', created_at) AS created_at,
        
        -- Numeric validation
        {{ clean_numeric('amount_filled', min_val=0, max_val=1000000) }} AS amount,
        
        -- Boolean conversion
        CASE 
            WHEN LOWER(is_active) = 'true' THEN TRUE
            WHEN LOWER(is_active) = 'false' THEN FALSE
            ELSE NULL
        END AS is_active,
        
        -- Metadata
        category_is_null_flag,
        amount_is_null_flag,
        CURRENT_TIMESTAMP() AS cleaned_at
    FROM imputed
)

SELECT * FROM typed_data
```

---

### **Step 5: Deduplication at intermediate layer**

```sql
-- models/intermediate/int_deduplicated.sql

WITH ranked_data AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY 
                order_id,
                customer_name,
                DATE(order_date)
            ORDER BY 
                cleaned_at DESC,
                amount DESC
        ) AS duplicate_rank
    FROM {{ ref('int_cleaned_data') }}
)

-- Step 3: Remove duplicates
SELECT 
    * EXCEPT(duplicate_rank)
FROM ranked_data
WHERE duplicate_rank = 1
```

---

### **Step 6: Final mart layer - clean table**

```sql
-- models/marts/dim_clean_table.sql

{{ config(
    materialized='table',
    unique_key='order_id',
    sort=['order_date'],
    dist='order_id',
    tags=['clean', 'production']
) }}

WITH final_cleaned AS (
    SELECT 
        order_id,
        customer_name,
        category,
        status,
        country,
        order_date,
        created_at,
        amount,
        is_active,
        
        -- Derived fields from Step 4
        COALESCE(amount, 0) AS amount_clean,
        CASE 
            WHEN amount >= 1000 THEN 'high_value'
            WHEN amount >= 100 THEN 'medium_value'
            WHEN amount > 0 THEN 'low_value'
            ELSE 'no_amount'
        END AS value_tier,
        
        -- Cross-field validation (Step 9)
        CASE 
            WHEN created_at IS NOT NULL 
                 AND order_date IS NOT NULL 
                 AND created_at < order_date 
            THEN TRUE 
            ELSE FALSE 
        END AS is_valid_timeline,
        
        -- Cleaning metadata
        cleaned_at,
        {{ dbt_utils.current_timestamp() }} as dbt_loaded_at
        
    FROM {{ ref('int_deduplicated') }}
    
    -- Step 10: Final sanity filters
    WHERE 
        customer_name IS NOT NULL
        AND order_date >= '2020-01-01'  -- Domain filter
)

SELECT 
    *,
    -- Step 7: Outlier flagging (not removal)
    CASE 
        WHEN amount_clean > (SELECT PERCENTILE_CONT(amount_clean, 0.99) FROM final_cleaned)
        THEN TRUE ELSE FALSE 
    END AS is_potential_outlier
        
FROM final_cleaned
```

---

### **Step 7: Mart Configuration**

```yaml
# models/marts/dim_clean_table.yml

version: 2

models:
  - name: dim_clean_table
    description: "Final cleaned table with all EDA steps applied"
    
    columns:
      - name: order_id
        tests:
          - unique
          - not_null
          
      - name: amount_clean
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1000000
              
      - name: is_valid_timeline
        description: "Cross-field validation flag"
        tests:
          - dbt_utils.expression_is_true:
              expression: "= TRUE OR = FALSE"  # Must be boolean
              
      - name: value_tier
        tests:
          - accepted_values:
              values: ['high_value', 'medium_value', 'low_value', 'no_amount']
              
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - order_id
            - customer_name
            - order_date
```

---

### **Step 8: Custom Tests for Data Quality**

```sql
-- tests/assert_cleaning_quality.sql

-- Test 1: Check duplicate removal worked
WITH duplicate_check AS (
    SELECT 
        order_id,
        COUNT(*) AS dup_count
    FROM {{ ref('dim_clean_table') }}
    GROUP BY order_id
    HAVING COUNT(*) > 1
)
SELECT COUNT(*) FROM duplicate_check
-- Should return 0

-- Test 2: Check null placeholders eliminated
SELECT 
    COUNT(*) as remaining_null_placeholders
FROM {{ ref('dim_clean_table') }}
WHERE 
    LOWER(customer_name) IN ('null', 'n/a', 'none', 'unknown')
    OR customer_name = ''
-- Should return 0

-- Test 3: Validate date consistency
SELECT 
    COUNT(*) as invalid_dates
FROM {{ ref('dim_clean_table') }}
WHERE 
    order_date > CURRENT_DATE()
    OR (created_at IS NOT NULL AND created_at > order_date)
-- Should return 0
```

---

### **Step 9: dbt Macros for Each Cleaning Step**

```sql
-- macros/cleaning_pipeline.sql

{% macro step1_strip_whitespace(relation) %}
    {% set columns = adapter.get_columns_in_relation(relation) %}
    {% set string_cols = [] %}
    
    {% for col in columns %}
        {% if col.dtype in ('string', 'text', 'varchar') %}
            {% do string_cols.append(col.name) %}
        {% endif %}
    {% endfor %}
    
    SELECT 
        {% for col in columns %}
            {% if col.name in string_cols %}
                TRIM(CAST({{ col.name }} AS STRING)) AS {{ col.name }}
            {% else %}
                {{ col.name }}
            {% endif %}
            {% if not loop.last %},{% endif %}
        {% endfor %}
    FROM {{ relation }}
{% endmacro %}

{% macro step2_standardize_case(column_name) %}
    LOWER(TRIM({{ column_name }}))
{% endmacro %}

{% macro step3_replace_null_placeholders(column_name, placeholders=['null', 'n/a', 'none']) %}
    CASE 
        WHEN LOWER(TRIM({{ column_name }})) IN ('{{ placeholders|join("', '") }}')
        THEN NULL
        ELSE {{ column_name }}
    END
{% endmacro %}

{% macro step4_deduplicate(table_ref, partition_cols, order_col='created_at') %}
    WITH ranked AS (
        SELECT 
            *,
            ROW_NUMBER() OVER (
                PARTITION BY {{ partition_cols|join(', ') }}
                ORDER BY {{ order_col }} DESC
            ) AS rn
        FROM {{ table_ref }}
    )
    SELECT * EXCEPT(rn) FROM ranked WHERE rn = 1
{% endmacro %}

{% macro step5_validate_timestamps(date_col) %}
    CASE 
        WHEN SAFE_CAST({{ date_col }} AS DATE) IS NOT NULL 
        THEN SAFE_CAST({{ date_col }} AS DATE)
        ELSE NULL
    END
{% endmacro %}
```

---

### **Step 10: Run the Pipeline**

```bash
# Run entire cleaning pipeline
dbt run --models +stg_raw_data+ --full-refresh

# Run with specific tags
dbt run --select tag:clean

# Test data quality
dbt test --models dim_clean_table

# Generate documentation
dbt docs generate
dbt docs serve

# Run with cleaning macros
dbt run --vars '{"clean_mode": "strict"}'
```

---

### **Step 11: dbt Snapshots for Version Control**

```sql
-- snapshots/cleaned_data_snapshot.sql

{% snapshot cleaned_data_snapshot %}

{{
    config(
        target_schema='snapshots',
        unique_key='order_id',
        strategy='timestamp',
        updated_at='cleaned_at',
        invalidate_hard_deletes=True
    )
}}

SELECT * FROM {{ ref('dim_clean_table') }}

{% endsnapshot %}
```

---

### **Step 12: Production Schedule (dbt Cloud/CLI)**

```yaml
# dbt_project.yml

name: 'data_cleaning_pipeline'
version: '1.0.0'
config-version: 2

# Cleaning sequence configuration
vars:
  clean_sequence:
    - step: "strip_whitespace"
      enabled: true
    - step: "standardize_case"
      columns: ['category', 'status', 'country']
    - step: "null_placeholders"
      placeholders: ['null', 'n/a', 'none', 'unknown', '']
    - step: "timestamp_standardization"
      format: "%Y-%m-%d"
    - step: "deduplication"
      keys: ['order_id', 'customer_email']
    - step: "null_handling"
      strategy: "impute"
    - step: "outlier_detection"
      method: "iqr"

models:
  data_cleaning_pipeline:
    staging:
      +materialized: view
    intermediate:
      +materialized: ephemeral
    marts:
      +materialized: table
      +schema: cleaned_data
      
tests:
  +store_failures: true
  +schema: test_failures
```

---

## **Key dbt Benefits for This Cleaning Sequence:**

1. **Lineage tracking** - Automatically documents which cleaning step affects which column
2. **Idempotent runs** - Same cleaning logic every time
3. **Testing built-in** - Assert data quality at each step
4. **Version controlled** - Entire cleaning pipeline in Git
5. **Documentation auto-generated** - Data catalog with cleaning rules
6. **Incremental processing** - Only clean new data
7. **Environment separation** - Dev/Prod with same logic

This dbt implementation ensures the **exact cleaning sequence runs consistently** every time, with full auditability and testing.