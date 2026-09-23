USE retail_sales_db;

-- 1. Total revenue
SELECT 
    ROUND(SUM(TotalPrice), 2) AS total_revenue
FROM retail_sales;


-- 2. Total number of orders
SELECT 
    COUNT(DISTINCT InvoiceNo) AS total_orders
FROM retail_sales;


-- 3. Total unique customers
SELECT 
    COUNT(DISTINCT CustomerID) AS unique_customers
FROM retail_sales;
