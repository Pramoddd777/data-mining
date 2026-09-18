-- Reconciliation and historical price queries used by README.md.

-- Finance reconciliation. A zero delta is an exact match to the signed-off
-- target; non-zero rows need an operational explanation.
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

-- The only inputs that change between reporting periods are these dates.
-- The same query returns the product and price valid during each period.
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