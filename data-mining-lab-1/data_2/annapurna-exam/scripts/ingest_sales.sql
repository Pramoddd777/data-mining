-- Annapurna Stores - Sales Ingestion

-- S01-S05: comma CSV, ISO timestamps
CREATE OR REPLACE TABLE sales_normalized AS
SELECT
    bill_no,
    CAST(line_no AS INTEGER) AS line_no,
    product_code,
    CAST(qty AS DECIMAL(18,3)) AS qty,
    CAST(unit_price AS DECIMAL(18,2)) AS unit_price,
    line_type,
    CAST(ts AS TIMESTAMP) AS ts,
    regexp_extract(filename, 'SALES_(S[0-9]{2})_', 1) AS store_id,
    strptime(
        regexp_extract(filename, 'SALES_S[0-9]{2}_([0-9]{8})', 1),
        '%Y%m%d'
    )::DATE AS business_date,
    filename AS source_file
FROM read_csv(
    '../data/sales/SALES_S0[1-5]_*.csv',
    header = true,
    union_by_name = true,
    filename = true
)

UNION ALL

-- S06-S09: semicolon CSV, different column names
SELECT
    bill_no,
    CAST(line_no AS INTEGER) AS line_no,
    item_code AS product_code,
    CAST(quantity AS DECIMAL(18,3)) AS qty,
    CAST(rate AS DECIMAL(18,2)) AS unit_price,
    type AS line_type,
    CAST(txn_time AS TIMESTAMP) AS ts,
    regexp_extract(filename, 'SALES_(S[0-9]{2})_', 1) AS store_id,
    strptime(
        regexp_extract(filename, 'SALES_S[0-9]{2}_([0-9]{8})', 1),
        '%Y%m%d'
    )::DATE AS business_date,
    filename AS source_file
FROM read_csv(
    '../data/sales/SALES_S0[6-9]_*.csv',
    header = true,
    delim = ';',
    union_by_name = true,
    filename = true
)

UNION ALL

-- S10-S12: comma CSV, epoch timestamps, different column order
SELECT
    bill_no,
    CAST(line_no AS INTEGER) AS line_no,
    product_code,
    CAST(qty AS DECIMAL(18,3)) AS qty,
    CAST(unit_price AS DECIMAL(18,2)) AS unit_price,
    line_type,
    to_timestamp(CAST(ts AS BIGINT))::TIMESTAMP AS ts,
    regexp_extract(filename, 'SALES_(S[0-9]{2})_', 1) AS store_id,
    strptime(
        regexp_extract(filename, 'SALES_S[0-9]{2}_([0-9]{8})', 1),
        '%Y%m%d'
    )::DATE AS business_date,
    filename AS source_file
FROM read_csv(
    '../data/sales/SALES_S1[0-2]_*.csv',
    header = true,
    union_by_name = true,
    filename = true
);

-- Deduplicate resend files using the safe line identity.
CREATE OR REPLACE TABLE sales_deduplicated AS
SELECT
    bill_no,
    line_no,
    product_code,
    qty,
    unit_price,
    line_type,
    ts,
    store_id,
    business_date,
    source_file
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY bill_no, line_no
            ORDER BY source_file
        ) AS rn
    FROM sales_normalized
)
WHERE rn = 1;

-- Final canonical sales table.
CREATE OR REPLACE TABLE sales_final AS
SELECT
    bill_no,
    line_no,
    store_id,
    product_code,
    business_date,
    ts,
    qty,
    unit_price,
    line_type,
    CAST(qty * unit_price AS DECIMAL(18,2)) AS revenue_amount,
    source_file
FROM sales_deduplicated;

-- Verification.
SELECT 'normalized_rows' AS check_name, COUNT(*) AS value
FROM sales_normalized

UNION ALL

SELECT 'deduplicated_rows', COUNT(*)
FROM sales_deduplicated

UNION ALL

SELECT 'final_rows', COUNT(*)
FROM sales_final

UNION ALL

SELECT 'distinct_bills', COUNT(DISTINCT bill_no)
FROM sales_final

UNION ALL

SELECT 'source_files', COUNT(DISTINCT source_file)
FROM sales_final;