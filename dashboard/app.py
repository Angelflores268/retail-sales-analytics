import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# -------------------------
# 1. Page setup
# -------------------------
st.set_page_config(
    page_title="Retail Sales Dashboard",
    layout="wide"
)

st.title("Retail Sales Analytics Dashboard")


# -------------------------
# 2. Load database settings
# -------------------------
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path, override=True)

db_url = URL.create(
    drivername="mysql+pymysql",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME")
)


# -------------------------
# 3. Connect to MySQL
# -------------------------
@st.cache_resource
def get_engine():
    return create_engine(
        db_url,
        pool_pre_ping=True
    )


engine = get_engine()


# -------------------------
# 4. Country filter
# -------------------------
country_list_query = """
SELECT DISTINCT Country
FROM retail_sales
WHERE Country IS NOT NULL
ORDER BY Country;
"""

country_list_df = pd.read_sql(
    country_list_query,
    engine
)

country_options = (
    ["All Countries"]
    + country_list_df["Country"].tolist()
)

selected_country = st.sidebar.selectbox(
    "Filter by Country",
    country_options
)

if selected_country == "All Countries":
    country_where = ""
    country_and = ""
    query_params = {}
else:
    country_where = "WHERE Country = :country"
    country_and = "AND Country = :country"
    query_params = {
        "country": selected_country
    }

st.caption(
    f"Showing data for: {selected_country}"
)


# -------------------------
# 5. KPI data
# -------------------------
kpi_query = text(f"""
SELECT
    ROUND(SUM(TotalPrice), 2) AS total_revenue,
    COUNT(DISTINCT InvoiceNo) AS total_orders,
    COUNT(DISTINCT CustomerID) AS unique_customers,
    ROUND(
        SUM(TotalPrice) / COUNT(DISTINCT InvoiceNo),
        2
    ) AS average_order_value
FROM retail_sales
{country_where};
""")

kpi_df = pd.read_sql(
    kpi_query,
    engine,
    params=query_params
)

total_revenue = kpi_df.loc[0, "total_revenue"]
total_orders = kpi_df.loc[0, "total_orders"]
unique_customers = kpi_df.loc[0, "unique_customers"]
average_order_value = kpi_df.loc[0, "average_order_value"]


# -------------------------
# 6. Display KPI cards
# -------------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Revenue",
    f"£{total_revenue:,.2f}"
)

col2.metric(
    "Total Orders",
    f"{total_orders:,}"
)

col3.metric(
    "Unique Customers",
    f"{unique_customers:,}"
)

col4.metric(
    "Average Order Value",
    f"£{average_order_value:,.2f}"
)


# -------------------------
# 7. Monthly revenue trend
# -------------------------
st.subheader("Monthly Revenue Trend")

monthly_query = text(f"""
SELECT
    DATE_FORMAT(InvoiceDate, '%Y-%m') AS month,
    ROUND(SUM(TotalPrice), 2) AS monthly_revenue
FROM retail_sales
{country_where}
GROUP BY DATE_FORMAT(InvoiceDate, '%Y-%m')
ORDER BY month;
""")

monthly_df = pd.read_sql(
    monthly_query,
    engine,
    params=query_params
)

monthly_df["month"] = pd.to_datetime(
    monthly_df["month"] + "-01"
)

monthly_fig = px.line(
    monthly_df,
    x="month",
    y="monthly_revenue",
    markers=True,
    labels={
        "month": "Month",
        "monthly_revenue": "Revenue (£)"
    }
)

monthly_fig.update_layout(
    xaxis_title="Month",
    yaxis_title="Revenue (£)"
)

st.plotly_chart(
    monthly_fig,
    use_container_width=True
)


# -------------------------
# 8. Top products + countries
# -------------------------
left_col, right_col = st.columns(2)


# Top 10 products by revenue
product_query = text(f"""
SELECT
    Description,
    ROUND(SUM(TotalPrice), 2) AS product_revenue
FROM retail_sales
WHERE Description IS NOT NULL
{country_and}
GROUP BY Description
ORDER BY product_revenue DESC
LIMIT 10;
""")

product_df = pd.read_sql(
    product_query,
    engine,
    params=query_params
)

product_fig = px.bar(
    product_df,
    x="product_revenue",
    y="Description",
    orientation="h",
    title="Top 10 Products by Revenue",
    labels={
        "product_revenue": "Revenue (£)",
        "Description": "Product"
    }
)

product_fig.update_layout(
    yaxis={
        "categoryorder": "total ascending"
    }
)

left_col.plotly_chart(
    product_fig,
    use_container_width=True
)


# -------------------------
# Top 10 countries by revenue
# Remains global even when filter is selected
# -------------------------
country_query = """
SELECT
    Country,
    ROUND(SUM(TotalPrice), 2) AS country_revenue
FROM retail_sales
WHERE Country IS NOT NULL
GROUP BY Country
ORDER BY country_revenue DESC
LIMIT 10;
"""

country_df = pd.read_sql(
    country_query,
    engine
)

country_fig = px.bar(
    country_df,
    x="country_revenue",
    y="Country",
    orientation="h",
    title="Top 10 Countries by Revenue",
    labels={
        "country_revenue": "Revenue (£)",
        "Country": "Country"
    }
)

country_fig.update_layout(
    yaxis={
        "categoryorder": "total ascending"
    }
)

right_col.plotly_chart(
    country_fig,
    use_container_width=True
)


# -------------------------
# 9. Top customers
# -------------------------
st.subheader("Top 10 Customers by Revenue")

customer_query = text(f"""
SELECT
    CustomerID,
    ROUND(SUM(TotalPrice), 2) AS customer_revenue
FROM retail_sales
WHERE CustomerID IS NOT NULL
{country_and}
GROUP BY CustomerID
ORDER BY customer_revenue DESC
LIMIT 10;
""")

customer_df = pd.read_sql(
    customer_query,
    engine,
    params=query_params
)

customer_df["CustomerID"] = (
    customer_df["CustomerID"]
    .astype("Int64")
    .astype(str)
)

customer_fig = px.bar(
    customer_df,
    x="CustomerID",
    y="customer_revenue",
    title="Top 10 Customers by Revenue",
    labels={
        "CustomerID": "Customer ID",
        "customer_revenue": "Revenue (£)"
    }
)

st.plotly_chart(
    customer_fig,
    use_container_width=True
)


# -------------------------
# 10. Revenue by day of week
# -------------------------
st.subheader("Revenue by Day of Week")

weekday_query = text(f"""
SELECT
    DAYNAME(InvoiceDate) AS day_of_week,
    ROUND(SUM(TotalPrice), 2) AS revenue
FROM retail_sales
{country_where}
GROUP BY DAYNAME(InvoiceDate);
""")

weekday_df = pd.read_sql(
    weekday_query,
    engine,
    params=query_params
)

weekday_order = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]

# Make sure all 7 days appear, even if revenue is 0
weekday_df = (
    weekday_df
    .set_index("day_of_week")["revenue"]
    .reindex(weekday_order, fill_value=0)
    .rename_axis("day_of_week")
    .reset_index()
)

weekday_fig = px.bar(
    weekday_df,
    x="day_of_week",
    y="revenue",
    title="Revenue by Day of Week",
    labels={
        "day_of_week": "Day",
        "revenue": "Revenue (£)"
    },
    category_orders={
        "day_of_week": weekday_order
    }
)

st.plotly_chart(
    weekday_fig,
    use_container_width=True
)

