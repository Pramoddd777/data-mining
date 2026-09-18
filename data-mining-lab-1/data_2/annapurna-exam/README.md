# Annapurna Stores --- Data Engineering Exam

## Overview

This project implements a reproducible data platform for Annapurna
Stores, a 12-store supermarket chain.

The solution addresses:

-   Daily sales-file ingestion
-   Multiple CSV dialects and timestamp formats
-   Duplicate and partial resend handling
-   Partitioned analytical storage
-   Dashboard-ready revenue tables
-   Historical product identity and price handling
-   Cross-system queries
-   Monthly finance reconciliation

## Architecture

``` text
Daily Sales CSV Files
        |
        v
  Canonical Ingestion
        |
        v
Deduplication using
(bill_no, line_no)
        |
        v
Partitioned Parquet
        |
        v
MinIO Object Store
        |
        +--------------------+
        |                    |
        v                    v
     DuckDB           PostgreSQL
 Analytical Engine   Master Data
        |             - stores
        |             - products
        |             - categories
        |             - price_revisions
        +--------------------+
                 |
                 v
          Dashboard Queries
                 |
                 v
       Finance Reconciliation
```

## Project Structure

``` text
annapurna-exam/
├── docker/
│   └── docker-compose.yml
├── output/
│   └── sales_partitioned/
├── scripts/
│   └── ingest_sales.sql
├── sql/
├── annapurna.duckdb
└── README.md
```

## Services

### MinIO

Object store for analytical sales data.

-   Bucket: `annapurna-sales`
-   Prefix: `sales_partitioned/`
-   Console: `http://localhost:9001`

Partition layout:

``` text
annapurna-sales/
└── sales_partitioned/
    ├── store_id=S01/
    │   └── sale_year=2024/
    │       └── sale_month=1/
    │           └── data_0.parquet
    ├── ...
    └── store_id=S12/
```

The partitioning uses:

-   `store_id`
-   `sale_year`
-   `sale_month`

This allows queries for a specific store and month to target the
corresponding partition.

### PostgreSQL

Relational master data database.

-   Database: `annapurna`
-   Port: `5433`

Main tables:

-   `stores`
-   `product_categories`
-   `products`
-   `price_revisions`

Loaded master-data counts:

-   Stores: 12
-   Product categories: 14
-   Products: 1,224
-   Price revisions: 4,320

### DuckDB

Analytical query engine used for:

-   Sales normalization
-   Deduplication
-   Parquet creation
-   MinIO queries
-   PostgreSQL attachment
-   Dashboard aggregations
-   Reconciliation
-   `EXPLAIN ANALYZE`

## Source Data

The original source folder is kept untouched.

Source path:

``` text
C:\Users\ub02-glab-053\Downloads\data_2\data
```

Sales source statistics:

-   CSV files: 4,457
-   Parquet files supplied: 0
-   Original sales size: 68,706,877 bytes

The source contains different file formats:

-   S01--S05: comma CSV, ISO timestamps
-   S06--S09: semicolon CSV, `dd-mm-yyyy HH:MM:SS`
-   S10--S12: comma CSV with UTF-8 BOM and epoch timestamps

Business date is taken from the filename, as required by the billing
notes.

## Ingestion and Normalization

The ingestion script is:

``` text
scripts/ingest_sales.sql
```

It creates:

1.  `sales_normalized`
2.  `sales_deduplicated`
3.  `sales_final`

Canonical sales fields include:

-   `bill_no`
-   `line_no`
-   `store_id`
-   `product_code`
-   `business_date`
-   `ts`
-   `qty`
-   `unit_price`
-   `line_type`
-   `revenue_amount`
-   `source_file`

Revenue amount is calculated as:

``` text
qty * unit_price
```

Revenue-bearing line types are:

``` text
SALE
RETURN
DISCOUNT
VOID
```

`TAX` and `TENDER` are excluded from revenue reporting.

## Idempotency

The safe line identity is:

``` text
(bill_no, line_no)
```

Resends are deduplicated using this key rather than selecting the newest
file.

Observed ingestion results:

``` text
normalized_rows   = 1,137,585
deduplicated_rows = 1,120,924
final_rows        = 1,120,924
distinct_bills    = 165,704
source_files      = 4,389
```

Duplicate/resend rows removed:

``` text
1,137,585 - 1,120,924 = 16,661
```

### Three-run idempotency proof

All three runs produced:

``` text
Rows:     1,120,924
Checksum: 3f184c09e14ecca75bd1fb35bd1ac24c
```

Therefore repeated execution does not increase the final row count or
change the resulting dataset.

## Partitioned Analytical Storage

The normalized sales data was written to ZSTD-compressed Parquet.

Partition command:

``` sql
COPY (
    SELECT *,
           year(business_date) AS sale_year,
           month(business_date) AS sale_month
    FROM sales_final
)
TO 'output/sales_partitioned'
(
    FORMAT PARQUET,
    PARTITION_BY (store_id, sale_year, sale_month),
    COMPRESSION ZSTD
);
```

Results:

  Metric                             Result
  ---------------------- ------------------
  Original CSV files                  4,457
  Original size            68,706,877 bytes
  Parquet files                         144
  Parquet size             12,591,754 bytes
  Final canonical rows            1,120,924

The 144 files correspond to:

``` text
12 stores × 12 months = 144 partitions
```

Example targeted query:

``` sql
SELECT COUNT(*)
FROM read_parquet(
    's3://annapurna-sales/sales_partitioned/store_id=S03/sale_year=2024/sale_month=10/*.parquet'
);
```

Result:

``` text
13,924 rows
```

S03 October 2024 revenue in the canonical sales data:

``` text
₹14,197,078.02
```

## Dashboard Tables

The following DuckDB tables were created:

### `dashboard_store_month`

Revenue by:

-   Store
-   Year
-   Month

### `dashboard_category_month`

Revenue by:

-   Year
-   Month
-   Product category

### `dashboard_day_of_week`

Revenue by:

-   Day of week

### `dashboard_monthly_revenue`

Revenue by:

-   Year
-   Month

Store descriptive information is kept separately in the
`store_dimension` view rather than repeated on every sales row.

## Historical Product Identity

Product codes are not treated as globally unique.

The product join uses:

``` text
product_code
+
business_date
```

against:

``` text
products.valid_from
products.valid_to
```

This handles product-code reissues correctly.

For example, product codes can refer to different products before and
after the June 2024 catalogue cleanup.

Non-item lines such as `TAX`, `TENDER`, and `DISC` do not require
product-master matching.

## Historical Pricing

Historical selling prices come from:

``` text
price_revisions
```

using:

``` text
product_sk
effective_from
effective_to
```

The March 2024 query selects a price revision whose effective date
contains the sale date.

Conceptually:

``` text
effective_from <= business_date <= effective_to
```

This avoids incorrectly using a current price when answering historical
questions.

## Cross-System Query

DuckDB queries sales directly from MinIO and joins PostgreSQL master
data without copying sales into PostgreSQL.

Example:

``` sql
SELECT
    s.store_id,
    d.store_name,
    d.city,
    SUM(s.revenue_amount) AS revenue
FROM read_parquet(
    's3://annapurna-sales/sales_partitioned/**/*.parquet'
) s
JOIN pg.public.stores d
    ON s.store_id = d.store_id
WHERE s.business_date >= DATE '2024-10-01'
  AND s.business_date < DATE '2024-11-01'
  AND s.line_type IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY
    s.store_id,
    d.store_name,
    d.city
ORDER BY
    s.store_id;
```

The `EXPLAIN ANALYZE` evidence showed:

-   `READ_PARQUET` reading sales from the MinIO S3 path
-   PostgreSQL `stores` table scanned as the master side
-   Hash join on `store_id`
-   Aggregation to 12 store rows
-   October date and revenue-line filters applied in the analytical plan

The captured execution reported 144 Parquet files read for the all-store
October cross-system query.

## Finance Reconciliation

Finance source:

``` text
finance_monthly.csv
```

The pipeline was compared against Finance's signed-off monthly revenue.

Results:

  Month         Difference
  --------- --------------
  2024-01            ₹0.00
  2024-02            ₹0.00
  2024-03     -₹486,250.00
  2024-04            ₹0.00
  2024-05            ₹0.00
  2024-06            ₹0.00
  2024-07     -₹232,131.70
  2024-08            ₹0.00
  2024-09            ₹0.00
  2024-10            ₹0.00
  2024-11            ₹0.00
  2024-12          +₹50.48

Nine months match Finance exactly.

The remaining differences require investigation rather than being
automatically classified as pipeline bugs.

Important source note:

-   S07 (Pune) had a three-day export gap in July 2024.
-   Finance received those figures from the store by phone.
-   Therefore the July difference must be considered in the context of
    missing source files.

The reconciliation should be taken back to Finance with the affected
months and supporting source-data investigation.

## Reproducibility

Start the services:

``` cmd
docker compose up -d
```

Open DuckDB:

``` cmd
duckdb annapurna.duckdb
```

Load extensions:

``` sql
LOAD httpfs;
LOAD postgres;
```

Configure MinIO:

``` sql
SET s3_endpoint='localhost:9000';
SET s3_access_key_id='minioadmin';
SET s3_secret_access_key='minioadmin123';
SET s3_use_ssl=false;
SET s3_url_style='path';
```

Attach PostgreSQL:

``` sql
ATTACH 'host=localhost port=5433 dbname=annapurna user=annapurna password=annapurna123'
AS pg (TYPE postgres, READ_ONLY);
```

Run ingestion:

``` cmd
duckdb annapurna.duckdb -f scripts\ingest_sales.sql
```

## Key Evidence

### Final row count

``` text
1,120,924
```

### Idempotency checksum

``` text
3f184c09e14ecca75bd1fb35bd1ac24c
```

### Source to analytical storage

``` text
4,457 CSV files
        ↓
1,137,585 normalized rows
        ↓
1,120,924 deduplicated rows
        ↓
144 partitioned Parquet files
        ↓
MinIO
        ↓
DuckDB analytical queries
```

## Exam Conclusion

The implemented platform replaces manual file opening and spreadsheet
aggregation with a reproducible analytical workflow.

The design provides:

-   Partitioned object storage
-   Safe resend handling
-   Deterministic ingestion
-   Historical product identity
-   Historical price lookup
-   Separate fact and dimension data
-   Cross-system analytical queries
-   Dashboard-ready aggregations
-   Monthly reconciliation against Finance

The remaining Finance differences are explicitly surfaced for
investigation instead of being silently hidden.
