-- Annapurna exam query pack.
-- Run from annapurna-exam with:
--   duckdb annapurna.duckdb -f sql\all_queries.sql

-- A1. Object-store connectivity and total landed rows.
INSTALL httpfs;
LOAD httpfs;
SET s3_endpoint = 'localhost:9000';
SET s3_access_key_id = 'minioadmin';
SET s3_secret_access_key = 'minioadmin123';
SET s3_use_ssl = false;
SET s3_url_style = 'path';

SELECT 's3_all_rows' AS check_name,
       COUNT(*) AS value
FROM read_parquet('s3://annapurna-sales/sales_partitioned/**/*.parquet');

-- A2. Partition-pruned S03 October query.
SELECT 's03_october_rows' AS check_name,
       COUNT(*) AS rows,
       SUM(revenue_amount) AS revenue
FROM read_parquet(
    's3://annapurna-sales/sales_partitioned/store_id=S03/sale_year=2024/sale_month=10/*.parquet'
);

-- B1. Canonical row count and deterministic checksum. Repeat the ingestion
-- command three times and run this query after each run.
SELECT COUNT(*) AS rows,
       md5(string_agg(
           concat_ws('|', bill_no, CAST(line_no AS VARCHAR), product_code,
                     CAST(qty AS VARCHAR), CAST(unit_price AS VARCHAR),
                     line_type, CAST(business_date AS VARCHAR)),
           '|' ORDER BY bill_no, line_no
       )) AS checksum
FROM sales_final;

-- C1. Dashboard aggregate table sizes and sample reads.
SELECT 'store_month_rows' AS check_name, COUNT(*) AS value
FROM dashboard_store_month;
SELECT 'category_month_rows' AS check_name, COUNT(*) AS value
FROM dashboard_category_month;
SELECT 'day_of_week_rows' AS check_name, COUNT(*) AS value
FROM dashboard_day_of_week;
SELECT 'monthly_rows' AS check_name, COUNT(*) AS value
FROM dashboard_monthly_revenue;

SELECT d.store_id, d.store_name, d.city,
       f.sale_year, f.sale_month, f.revenue
FROM dashboard_store_month AS f
JOIN store_dimension AS d USING (store_id)
WHERE f.sale_year = 2024 AND f.sale_month = 10
ORDER BY d.store_id;

SELECT sale_year, sale_month, category_id, revenue
FROM dashboard_category_month
WHERE sale_year = 2024 AND sale_month = 10
ORDER BY category_id;

SELECT *
FROM dashboard_day_of_week
ORDER BY day_of_week_number;

SELECT *
FROM dashboard_monthly_revenue
ORDER BY sale_year, sale_month;

-- C2. Line-type control showing why TAX and TENDER are excluded.
SELECT line_type, COUNT(*) AS rows, SUM(revenue_amount) AS revenue
FROM sales_final
GROUP BY line_type
ORDER BY line_type;

-- D1. One period-driven historical price query. Change only the dates in the
-- periods CTE to answer for another reporting period.
INSTALL postgres;
LOAD postgres;
ATTACH 'host=localhost port=5433 dbname=annapurna user=annapurna password=annapurna123'
    AS pg (TYPE postgres, READ_ONLY);

WITH periods(report_month, start_date, end_date) AS (
    VALUES ('2024-03', DATE '2024-03-01', DATE '2024-04-01'),
           ('2024-10', DATE '2024-10-01', DATE '2024-11-01')
)
SELECT pr.report_month,
       p.product_code,
       p.product_name,
       p.product_sk,
       r.selling_price,
       r.effective_from,
       r.effective_to
FROM periods AS pr
JOIN pg.public.products AS p
  ON p.product_code = 'P100049'
 AND p.valid_from < pr.end_date
 AND p.valid_to > pr.start_date
JOIN pg.public.price_revisions AS r
  ON r.product_sk = p.product_sk
 AND r.effective_from < pr.end_date
 AND r.effective_to > pr.start_date
ORDER BY pr.report_month, r.effective_from;

-- E1. Cross-system join: local DuckDB sales + PostgreSQL product master.
SELECT s.store_id,
       p.category_id,
       SUM(s.revenue_amount) AS revenue
FROM sales_final AS s
LEFT JOIN pg.public.products AS p
  ON s.product_code = p.product_code
 AND s.business_date >= p.valid_from
 AND s.business_date < p.valid_to
WHERE s.store_id = 'S03'
  AND s.business_date >= DATE '2024-10-01'
  AND s.business_date < DATE '2024-11-01'
  AND s.line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY s.store_id, p.category_id
ORDER BY p.category_id;

EXPLAIN
SELECT s.store_id,
       p.category_id,
       SUM(s.revenue_amount) AS revenue
FROM sales_final AS s
LEFT JOIN pg.public.products AS p
  ON s.product_code = p.product_code
 AND s.business_date >= p.valid_from
 AND s.business_date < p.valid_to
WHERE s.store_id = 'S03'
  AND s.business_date >= DATE '2024-10-01'
  AND s.business_date < DATE '2024-11-01'
  AND s.line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY s.store_id, p.category_id;

-- F1. Finance reconciliation. Delta is canonical revenue minus finance.
WITH actual AS (
    SELECT strftime(business_date, '%Y-%m') AS month,
           SUM(revenue_amount) AS actual_revenue
    FROM sales_final
    WHERE line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
    GROUP BY 1
), finance AS (
    SELECT *
    FROM read_csv_auto('../data/finance_monthly.csv')
)
SELECT f.month,
       f.revenue_inr AS finance_revenue,
       a.actual_revenue,
       CAST(a.actual_revenue AS DECIMAL(18,2))
         - CAST(f.revenue_inr AS DECIMAL(18,2)) AS delta
FROM finance AS f
LEFT JOIN actual AS a ON a.month = f.month
ORDER BY f.month;

-- F2. Source coverage by store/month, useful for explaining missing exports.
SELECT strftime(business_date, '%Y-%m') AS month,
       store_id,
       COUNT(DISTINCT business_date) AS days,
       COUNT(DISTINCT source_file) AS files,
       MIN(business_date) AS first_day,
       MAX(business_date) AS last_day
FROM sales_final
GROUP BY 1, 2
ORDER BY 1, 2;