-- Run with DuckDB from annapurna-exam after sales_final exists.
-- PostgreSQL remains the system of record for stores and product masters.

INSTALL postgres;
LOAD postgres;
ATTACH 'host=localhost port=5433 dbname=annapurna user=annapurna password=annapurna123'
    AS pg (TYPE postgres, READ_ONLY);

CREATE OR REPLACE VIEW sales_enriched AS
SELECT
    s.bill_no,
    s.line_no,
    s.store_id,
    s.product_code,
    p.product_sk,
    p.product_name,
    p.category_id,
    s.business_date,
    s.ts,
    s.qty,
    s.unit_price,
    s.line_type,
    s.revenue_amount
FROM sales_final AS s
LEFT JOIN pg.public.products AS p
    ON s.product_code = p.product_code
   AND s.business_date >= p.valid_from
   AND s.business_date < p.valid_to;

-- Revenue includes item sales, returns, discounts, and voids. TAX and TENDER
-- are deliberately excluded; VOID rows remain so cancelled bills net to zero.
CREATE OR REPLACE TABLE dashboard_store_month AS
SELECT store_id, year(business_date) AS sale_year,
       month(business_date) AS sale_month, SUM(revenue_amount) AS revenue
FROM sales_enriched
WHERE line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY store_id, year(business_date), month(business_date);

CREATE OR REPLACE TABLE dashboard_category_month AS
SELECT year(business_date) AS sale_year,
       month(business_date) AS sale_month,
       category_id,
       SUM(revenue_amount) AS revenue
FROM sales_enriched
WHERE line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
  AND product_sk IS NOT NULL
GROUP BY year(business_date), month(business_date), category_id;

CREATE OR REPLACE TABLE dashboard_day_of_week AS
SELECT dayofweek(business_date) AS day_of_week_number,
       dayname(business_date) AS day_of_week,
       SUM(revenue_amount) AS revenue
FROM sales_enriched
WHERE line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY dayofweek(business_date), dayname(business_date);

CREATE OR REPLACE TABLE dashboard_monthly_revenue AS
SELECT year(business_date) AS sale_year,
       month(business_date) AS sale_month,
       SUM(revenue_amount) AS revenue
FROM sales_enriched
WHERE line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY year(business_date), month(business_date);

CREATE OR REPLACE VIEW store_dimension AS
SELECT store_id, store_name, city, address_line AS address
FROM pg.public.stores;