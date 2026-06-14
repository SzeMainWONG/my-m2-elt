"""
Olist E-Commerce Gold Mart Dashboard
=====================================
A Streamlit app for exploring the dbt "gold mart" models:
  - dim_customers
  - dim_products
  - dim_reviews
  - dim_sellers
  - fact_orders

Tabs:
  1. Revenue Performance
  2. Seller Performance Ranking
  3. Product Category Performance
  4. Payment Method Analysis
  5. Delivery Performance
  6. Customer Segmentation (RFM)
  7. Geographic Revenue Heatmap
  8. Review Sentiment vs Sales Impact
  9. Data Quality

Connects to BigQuery using google-cloud-bigquery + pandas.

Run with:
    streamlit run app.py

Configuration:
  Set these in `.streamlit/secrets.toml`:

    [gcp]
    project_id = "your-gcp-project"
    dataset = "your_gold_dataset"

    [gcp_service_account]
    type = "service_account"
    ... (full service account JSON key fields) ...

  If no service account is provided, the app falls back to
  Application Default Credentials (e.g. `gcloud auth application-default login`).
"""

import re
import datetime as dt

import pandas as pd
import streamlit as st
import plotly.express as px
from google.cloud import bigquery
from google.oauth2 import service_account


# ----------------------------------------------------------------------
# Page config
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Olist Gold Mart Dashboard",
    page_icon="📦",
    layout="wide",
)


# ----------------------------------------------------------------------
# BigQuery connection helpers
# ----------------------------------------------------------------------
@st.cache_resource
def get_bq_client() -> bigquery.Client:
    """Create a cached BigQuery client using secrets or default credentials."""
    project_id = st.secrets.get("gcp", {}).get("project_id")

    if "gcp_service_account" in st.secrets:
        credentials = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"])
        )
        return bigquery.Client(credentials=credentials, project=project_id)

    # Falls back to Application Default Credentials
    return bigquery.Client(project=project_id)


def get_dataset() -> str:
    """Return the fully-qualified dataset reference, e.g. `project.dataset`."""
    gcp_cfg = st.secrets.get("gcp", {})
    project_id = gcp_cfg.get("project_id")
    dataset = gcp_cfg.get("dataset")
    if not project_id or not dataset:
        st.error(
            "Missing BigQuery configuration. Please set `gcp.project_id` and "
            "`gcp.dataset` in `.streamlit/secrets.toml`."
        )
        st.stop()
    return f"`{project_id}.{dataset}`"


@st.cache_data(ttl=3600, show_spinner=False)
def run_query(sql: str) -> pd.DataFrame:
    """Run a SQL query against BigQuery and return a DataFrame."""
    client = get_bq_client()
    return client.query(sql).to_dataframe()


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=True)
def load_fact_orders() -> pd.DataFrame:
    ds = get_dataset()
    sql = f"""
        SELECT *
        FROM {ds}.fact_orders
    """
    df = run_query(sql)

    for col in [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
        "shipping_limit_date",
    ]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


@st.cache_data(ttl=3600, show_spinner=True)
def load_dim_products() -> pd.DataFrame:
    ds = get_dataset()
    return run_query(f"SELECT * FROM {ds}.dim_products")


@st.cache_data(ttl=3600, show_spinner=True)
def load_dim_customers() -> pd.DataFrame:
    ds = get_dataset()
    return run_query(f"SELECT * FROM {ds}.dim_customers")


@st.cache_data(ttl=3600, show_spinner=True)
def load_dim_sellers() -> pd.DataFrame:
    ds = get_dataset()
    return run_query(f"SELECT * FROM {ds}.dim_sellers")


@st.cache_data(ttl=3600, show_spinner=True)
def load_dim_reviews() -> pd.DataFrame:
    ds = get_dataset()
    return run_query(f"SELECT * FROM {ds}.dim_reviews")


# ----------------------------------------------------------------------
# Sidebar - global filters
# ----------------------------------------------------------------------
def build_sidebar(fact_orders: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.title("📦 Filters")

    valid_dates = fact_orders["order_purchase_timestamp"].dropna()
    if valid_dates.empty:
        st.sidebar.warning("No order dates found in fact_orders.")
        return fact_orders

    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    date_range = st.sidebar.date_input(
        "Order purchase date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    statuses = sorted(fact_orders["order_status"].dropna().unique().tolist())
    selected_statuses = st.sidebar.multiselect(
        "Order status", options=statuses, default=statuses
    )

    df = fact_orders.copy()

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        mask = (
            df["order_purchase_timestamp"].dt.date >= start_date
        ) & (df["order_purchase_timestamp"].dt.date <= end_date)
        df = df[mask | df["order_purchase_timestamp"].isna()]

    if selected_statuses:
        df = df[df["order_status"].isin(selected_statuses)]

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"Rows after filtering: {len(df):,} / {len(fact_orders):,}"
    )

    return df


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def add_revenue(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["revenue"] = df["price"].fillna(0) + df["freight_value"].fillna(0)
    return df


# ----------------------------------------------------------------------
# 1. Revenue Performance
# ----------------------------------------------------------------------
def render_revenue_performance(df: pd.DataFrame):
    st.subheader("Revenue Performance")

    data = add_revenue(df)

    total_revenue = data["revenue"].sum()
    product_revenue = data["price"].fillna(0).sum()
    freight_revenue = data["freight_value"].fillna(0).sum()
    total_orders = data["id"].nunique()
    aov = total_revenue / total_orders if total_orders else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Revenue (R$)", f"{total_revenue:,.2f}")
    col2.metric("Product Revenue (R$)", f"{product_revenue:,.2f}")
    col3.metric("Freight Revenue (R$)", f"{freight_revenue:,.2f}")
    col4.metric("Avg Order Value (R$)", f"{aov:,.2f}")

    st.markdown("---")

    dated = data.dropna(subset=["order_purchase_timestamp"]).copy()
    dated["order_month"] = dated["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()

    monthly = (
        dated.groupby("order_month")
        .agg(
            revenue=("revenue", "sum"),
            product_revenue=("price", "sum"),
            freight_revenue=("freight_value", "sum"),
            orders=("id", "nunique"),
        )
        .reset_index()
    )
    monthly["aov"] = monthly["revenue"] / monthly["orders"].replace(0, pd.NA)

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.line(monthly, x="order_month", y="revenue", markers=True,
                       title="Monthly Total Revenue (R$)")
        fig.update_layout(xaxis_title="Month", yaxis_title="Revenue (R$)")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.line(monthly, x="order_month", y="aov", markers=True,
                       title="Monthly Average Order Value (R$)")
        fig.update_layout(xaxis_title="Month", yaxis_title="AOV (R$)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Product vs. Freight Revenue Over Time**")
    rev_split = monthly.melt(
        id_vars="order_month",
        value_vars=["product_revenue", "freight_revenue"],
        var_name="component", value_name="value"
    )
    fig = px.bar(rev_split, x="order_month", y="value", color="component",
                  barmode="stack")
    fig.update_layout(xaxis_title="Month", yaxis_title="Revenue (R$)")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View monthly revenue table"):
        st.dataframe(monthly, use_container_width=True)


# ----------------------------------------------------------------------
# 2. Seller Performance Ranking
# ----------------------------------------------------------------------
def render_seller_performance(df: pd.DataFrame, dim_sellers: pd.DataFrame, dim_reviews: pd.DataFrame):
    st.subheader("Seller Performance Ranking")

    data = add_revenue(df.dropna(subset=["seller_id"]).copy())

    # Bring in review scores per order to compute avg review per seller
    if "review_score" in dim_reviews.columns and "order_id" in dim_reviews.columns:
        reviews = dim_reviews[["order_id", "review_score"]].dropna(subset=["order_id"])
        data = data.merge(reviews, left_on="id", right_on="order_id", how="left")

    agg_dict = {
        "revenue": ("revenue", "sum"),
        "orders": ("id", "nunique"),
        "items_sold": ("order_item_id", "count"),
        "avg_price": ("price", "mean"),
        "avg_freight": ("freight_value", "mean"),
    }
    if "review_score" in data.columns:
        agg_dict["avg_review_score"] = ("review_score", "mean")
    if "is_long_delivery" in data.columns:
        agg_dict["pct_long_delivery"] = ("is_long_delivery", "mean")

    seller_perf = data.groupby("seller_id").agg(**agg_dict).reset_index()

    if "pct_long_delivery" in seller_perf.columns:
        seller_perf["pct_long_delivery"] = (seller_perf["pct_long_delivery"] * 100).round(1)
    if "avg_review_score" in seller_perf.columns:
        seller_perf["avg_review_score"] = seller_perf["avg_review_score"].round(2)
    seller_perf["revenue"] = seller_perf["revenue"].round(2)
    seller_perf["avg_price"] = seller_perf["avg_price"].round(2)
    seller_perf["avg_freight"] = seller_perf["avg_freight"].round(2)

    # Merge seller location
    if "seller_state" in dim_sellers.columns:
        loc_cols = ["id", "seller_state"]
        if "seller_city" in dim_sellers.columns:
            loc_cols.append("seller_city")
        seller_perf = seller_perf.merge(
            dim_sellers[loc_cols],
            left_on="seller_id", right_on="id", how="left"
        )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sellers", f"{seller_perf['seller_id'].nunique():,}")
    col2.metric("Avg Revenue / Seller (R$)", f"{seller_perf['revenue'].mean():,.2f}")
    if "avg_review_score" in seller_perf.columns:
        col3.metric("Avg Review Score", f"{seller_perf['avg_review_score'].mean():.2f} / 5")
    if "pct_long_delivery" in seller_perf.columns:
        col4.metric("Avg % Long Deliveries", f"{seller_perf['pct_long_delivery'].mean():.1f}%")

    st.markdown("---")

    n = st.slider("Number of top sellers to show", min_value=5, max_value=50, value=15, key="seller_n")

    rank_options = [c for c in ["revenue", "orders", "items_sold", "avg_review_score"] if c in seller_perf.columns]
    rank_metric = st.selectbox(
        "Rank sellers by",
        options=rank_options,
        format_func=lambda c: {
            "revenue": "Total Revenue",
            "orders": "Order Count",
            "items_sold": "Items Sold",
            "avg_review_score": "Avg Review Score",
        }.get(c, c),
    )

    top_sellers = seller_perf.sort_values(rank_metric, ascending=False).head(n)

    fig = px.bar(
        top_sellers, x="seller_id", y=rank_metric,
        color="seller_state" if "seller_state" in top_sellers.columns else None,
        title=f"Top {n} Sellers by {rank_metric.replace('_', ' ').title()}"
    )
    fig.update_layout(xaxis_title="Seller ID", yaxis_title=rank_metric.replace("_", " ").title())
    fig.update_xaxes(tickangle=45)
    st.plotly_chart(fig, use_container_width=True)

    if {"avg_review_score", "revenue"}.issubset(seller_perf.columns):
        st.markdown("**Revenue vs. Review Score by Seller**")
        fig = px.scatter(
            seller_perf, x="avg_review_score", y="revenue",
            size="orders", hover_data=["seller_id"],
            color="seller_state" if "seller_state" in seller_perf.columns else None,
        )
        fig.update_layout(xaxis_title="Avg Review Score", yaxis_title="Revenue (R$)")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("View full seller performance table"):
        st.dataframe(seller_perf.sort_values(rank_metric, ascending=False), use_container_width=True)


# ----------------------------------------------------------------------
# 3. Product Category Performance
# ----------------------------------------------------------------------
def render_category_performance(df: pd.DataFrame, dim_products: pd.DataFrame):
    st.subheader("Product Category Performance")

    cat_col = "product_category"
    if cat_col not in dim_products.columns:
        st.warning(f"`{cat_col}` column not found in dim_products.")
        return

    data = add_revenue(df.dropna(subset=["product_id"]).copy())

    products = dim_products[["id", cat_col]].rename(columns={cat_col: "category"})
    products["category"] = products["category"].fillna("unknown")

    data = data.merge(products, left_on="product_id", right_on="id", how="left", suffixes=("", "_prod"))
    data["category"] = data["category"].fillna("unknown")

    cat_perf = (
        data.groupby("category")
        .agg(
            revenue=("revenue", "sum"),
            units_sold=("order_item_id", "count"),
            avg_price=("price", "mean"),
            orders=("id", "nunique"),
        )
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    cat_perf["revenue"] = cat_perf["revenue"].round(2)
    cat_perf["avg_price"] = cat_perf["avg_price"].round(2)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Categories", f"{cat_perf['category'].nunique():,}")
    col2.metric("Top Category", cat_perf.iloc[0]["category"] if not cat_perf.empty else "N/A")
    col3.metric("Top Category Revenue (R$)", f"{cat_perf.iloc[0]['revenue']:,.2f}" if not cat_perf.empty else "N/A")

    st.markdown("---")

    n = st.slider("Number of categories to show", min_value=5, max_value=50, value=15, key="cat_n")
    top_cats = cat_perf.head(n)

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(top_cats, x="category", y="revenue", text="units_sold",
                      title=f"Top {n} Categories by Revenue")
        fig.update_layout(xaxis_title="Category", yaxis_title="Revenue (R$)")
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.bar(top_cats.sort_values("units_sold", ascending=False), x="category", y="units_sold",
                      title=f"Top {n} Categories by Units Sold")
        fig.update_layout(xaxis_title="Category", yaxis_title="Units Sold")
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Average Price by Category**")
    fig = px.bar(top_cats.sort_values("avg_price", ascending=False), x="category", y="avg_price")
    fig.update_layout(xaxis_title="Category", yaxis_title="Avg Price (R$)")
    fig.update_xaxes(tickangle=45)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View category performance table"):
        st.dataframe(cat_perf, use_container_width=True)


# ----------------------------------------------------------------------
# 4. Payment Method Analysis
# ----------------------------------------------------------------------
def render_payment_analysis(df: pd.DataFrame):
    st.subheader("Payment Method Analysis")

    data = add_revenue(df.copy())

    pay_summary = (
        data.groupby("payment_type")
        .agg(
            orders=("id", "nunique"),
            total_payment_value=("payment_value", "sum"),
            avg_payment_value=("payment_value", "mean"),
            avg_installments=("payment_installments", "mean"),
        )
        .reset_index()
        .sort_values("total_payment_value", ascending=False)
    )
    pay_summary["total_payment_value"] = pay_summary["total_payment_value"].round(2)
    pay_summary["avg_payment_value"] = pay_summary["avg_payment_value"].round(2)
    pay_summary["avg_installments"] = pay_summary["avg_installments"].round(2)

    col1, col2, col3 = st.columns(3)
    col1.metric("Payment Types", f"{pay_summary['payment_type'].nunique():,}")
    most_common = pay_summary.sort_values("orders", ascending=False).iloc[0]
    col2.metric("Most Common", most_common["payment_type"])
    col3.metric("Avg Installments (overall)", f"{data['payment_installments'].mean():.2f}")

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.pie(pay_summary, names="payment_type", values="orders", hole=0.4,
                      title="Order Share by Payment Type")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.bar(pay_summary, x="payment_type", y="total_payment_value",
                      title="Total Payment Value by Type")
        fig.update_layout(xaxis_title="Payment Type", yaxis_title="Total Payment Value (R$)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Installment Distribution by Payment Type**")
    installments = data.dropna(subset=["payment_installments"])
    fig = px.histogram(
        installments, x="payment_installments", color="payment_type",
        barmode="overlay", nbins=24
    )
    fig.update_layout(xaxis_title="Installments", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Average Order Value by Payment Type**")
    aov_rows = []
    for ptype, group in data.groupby("payment_type"):
        unique_orders = group.drop_duplicates("id")
        n_orders = unique_orders["id"].nunique()
        total_rev = unique_orders["revenue"].sum()
        aov_rows.append({
            "payment_type": ptype,
            "avg_order_value": total_rev / n_orders if n_orders else 0
        })
    aov_pay = pd.DataFrame(aov_rows)
    fig = px.bar(aov_pay, x="payment_type", y="avg_order_value")
    fig.update_layout(xaxis_title="Payment Type", yaxis_title="Avg Order Value (R$)")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View payment summary table"):
        st.dataframe(pay_summary, use_container_width=True)


# ----------------------------------------------------------------------
# 5. Delivery Performance
# ----------------------------------------------------------------------
def render_delivery_performance(df: pd.DataFrame):
    st.subheader("Delivery Performance")

    data = df.copy()
    delivered = data.dropna(subset=["order_delivered_customer_date", "order_purchase_timestamp"]).copy()
    delivered["delivery_days"] = (
        delivered["order_delivered_customer_date"] - delivered["order_purchase_timestamp"]
    ).dt.days

    delivered["estimate_diff_days"] = pd.NA
    has_estimate_mask = delivered["order_estimated_delivery_date"].notna()
    delivered.loc[has_estimate_mask, "estimate_diff_days"] = (
        delivered.loc[has_estimate_mask, "order_delivered_customer_date"]
        - delivered.loc[has_estimate_mask, "order_estimated_delivery_date"]
    ).dt.days

    avg_delivery_days = delivered["delivery_days"].mean()
    pct_long_delivery = (
        data["is_long_delivery"].fillna(False).mean() * 100
        if "is_long_delivery" in data.columns else None
    )
    pct_overdue = (
        data["is_overdue_delivery"].fillna(False).mean() * 100
        if "is_overdue_delivery" in data.columns else None
    )
    pct_missing_date = (
        data["has_missing_delivery_date"].fillna(False).mean() * 100
        if "has_missing_delivery_date" in data.columns else None
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Avg Delivery Time (days)", f"{avg_delivery_days:.1f}" if pd.notna(avg_delivery_days) else "N/A")
    col2.metric("% Long Deliveries (>30d)", f"{pct_long_delivery:.1f}%" if pct_long_delivery is not None else "N/A")
    col3.metric("% Overdue / Never Delivered", f"{pct_overdue:.1f}%" if pct_overdue is not None else "N/A")
    col4.metric("% Missing Delivery Date", f"{pct_missing_date:.1f}%" if pct_missing_date is not None else "N/A")

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.histogram(delivered, x="delivery_days", nbins=40,
                            title="Distribution of Delivery Time (days)")
        fig.update_layout(xaxis_title="Delivery Time (days)", yaxis_title="Orders")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        est_data = delivered.dropna(subset=["estimate_diff_days"])
        if not est_data.empty:
            fig = px.histogram(est_data, x="estimate_diff_days", nbins=40,
                                title="Actual vs Estimated Delivery (days, +=late)")
            fig.update_layout(xaxis_title="Days vs Estimate", yaxis_title="Orders")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No estimated delivery date data available.")

    st.markdown("**Monthly Average Delivery Time**")
    delivered["order_month"] = delivered["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    monthly_delivery = delivered.groupby("order_month")["delivery_days"].mean().reset_index()
    fig = px.line(monthly_delivery, x="order_month", y="delivery_days", markers=True)
    fig.update_layout(xaxis_title="Month", yaxis_title="Avg Delivery Time (days)")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View delivery data sample"):
        cols = [c for c in [
            "id", "order_status", "order_purchase_timestamp", "order_delivered_customer_date",
            "order_estimated_delivery_date", "delivery_days", "estimate_diff_days"
        ] if c in delivered.columns]
        st.dataframe(delivered[cols].head(500), use_container_width=True)


# ----------------------------------------------------------------------
# 6. Customer Segmentation (RFM)
# ----------------------------------------------------------------------
def render_customer_segmentation(df: pd.DataFrame):
    st.subheader("Customer Segmentation (RFM Analysis)")
    st.caption(
        "Recency = days since last order, Frequency = number of distinct orders, "
        "Monetary = total spend (price + freight)."
    )

    data = add_revenue(df.dropna(subset=["order_purchase_timestamp", "customer_id"]).copy())

    snapshot_date = data["order_purchase_timestamp"].max() + dt.timedelta(days=1)

    rfm = (
        data.groupby("customer_id")
        .agg(
            recency=("order_purchase_timestamp", lambda x: (snapshot_date - x.max()).days),
            frequency=("id", "nunique"),
            monetary=("revenue", "sum"),
        )
        .reset_index()
    )

    rfm["r_score"] = pd.qcut(rfm["recency"], 4, labels=[4, 3, 2, 1], duplicates="drop").astype(int)
    rfm["f_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4], duplicates="drop").astype(int)
    rfm["m_score"] = pd.qcut(rfm["monetary"], 4, labels=[1, 2, 3, 4], duplicates="drop").astype(int)
    rfm["rfm_score"] = rfm["r_score"] + rfm["f_score"] + rfm["m_score"]

    def segment(score: int) -> str:
        if score >= 10:
            return "Champions"
        elif score >= 8:
            return "Loyal Customers"
        elif score >= 6:
            return "Potential Loyalists"
        elif score >= 4:
            return "At Risk"
        else:
            return "Lost / Low Value"

    rfm["segment"] = rfm["rfm_score"].apply(segment)

    col1, col2 = st.columns(2)
    with col1:
        seg_counts = rfm["segment"].value_counts().reset_index()
        seg_counts.columns = ["segment", "count"]
        fig = px.pie(seg_counts, names="segment", values="count", hole=0.4,
                      title="Customer Segments")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        seg_value = rfm.groupby("segment")["monetary"].sum().reset_index()
        fig = px.bar(
            seg_value.sort_values("monetary", ascending=False),
            x="segment", y="monetary", text="monetary",
            title="Total Spend by Segment"
        )
        fig.update_layout(xaxis_title="", yaxis_title="Total Spend (R$)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Recency vs. Monetary (bubble size = Frequency)**")
    fig = px.scatter(
        rfm, x="recency", y="monetary", size="frequency", color="segment",
        hover_data=["customer_id", "frequency"]
    )
    fig.update_layout(xaxis_title="Recency (days)", yaxis_title="Monetary (R$)")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View RFM table"):
        st.dataframe(
            rfm.sort_values("rfm_score", ascending=False),
            use_container_width=True
        )


# ----------------------------------------------------------------------
# 7. Geographic Revenue Heatmap (Customer City + State)
# ----------------------------------------------------------------------
def render_geographic_heatmap(df: pd.DataFrame, dim_customers: pd.DataFrame):
    st.subheader("Geographic Revenue Heatmap")

    required_cols = {"customer_city", "customer_state"}
    if not required_cols.issubset(dim_customers.columns):
        st.warning("Customer city/state columns not found in dim_customers.")
        return

    data = add_revenue(df.dropna(subset=["customer_id"]).copy())

    cust_geo = dim_customers[["id", "customer_city", "customer_state"]].copy()
    data = data.merge(cust_geo, left_on="customer_id", right_on="id", how="left", suffixes=("", "_cust"))

    data["customer_city"] = data["customer_city"].fillna("unknown")
    data["customer_state"] = data["customer_state"].fillna("unknown")

    # State-level summary
    state_rev = (
        data.groupby("customer_state")
        .agg(revenue=("revenue", "sum"), orders=("id", "nunique"), customers=("customer_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    state_rev["revenue"] = state_rev["revenue"].round(2)

    col1, col2, col3 = st.columns(3)
    col1.metric("States Covered", f"{state_rev['customer_state'].nunique():,}")
    col2.metric("Top State", state_rev.iloc[0]["customer_state"] if not state_rev.empty else "N/A")
    col3.metric("Top State Revenue (R$)", f"{state_rev.iloc[0]['revenue']:,.2f}" if not state_rev.empty else "N/A")

    st.markdown("---")

    st.markdown("**Revenue by State**")
    fig = px.bar(state_rev, x="customer_state", y="revenue", text="orders",
                  title="Revenue by Customer State")
    fig.update_layout(xaxis_title="State", yaxis_title="Revenue (R$)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("**Top Cities by Revenue (City + State)**")

    n = st.slider("Number of top cities to show", min_value=5, max_value=50, value=15, key="city_n")

    city_rev = (
        data.groupby(["customer_city", "customer_state"])
        .agg(revenue=("revenue", "sum"), orders=("id", "nunique"), customers=("customer_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(n)
    )
    city_rev["revenue"] = city_rev["revenue"].round(2)
    city_rev["label"] = city_rev["customer_city"] + ", " + city_rev["customer_state"]

    fig = px.bar(city_rev, x="label", y="revenue", text="orders",
                  title=f"Top {n} Cities by Revenue")
    fig.update_layout(xaxis_title="City, State", yaxis_title="Revenue (R$)")
    fig.update_xaxes(tickangle=45)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Revenue Heatmap: City vs State (Top Cities)**")
    heat_data = city_rev.pivot_table(
        index="customer_city", columns="customer_state", values="revenue", aggfunc="sum", fill_value=0
    )
    fig = px.imshow(
        heat_data, labels=dict(x="State", y="City", color="Revenue (R$)"),
        aspect="auto", color_continuous_scale="Reds"
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View state-level table"):
        st.dataframe(state_rev, use_container_width=True)

    with st.expander("View city-level table"):
        st.dataframe(city_rev.drop(columns="label"), use_container_width=True)


# ----------------------------------------------------------------------
# 8. Review Sentiment vs Sales Impact
# ----------------------------------------------------------------------
POSITIVE_WORDS = {
    "bom", "boa", "otimo", "ótimo", "excelente", "adorei", "amei", "perfeito",
    "recomendo", "rapido", "rápido", "satisfeito", "satisfeita", "gostei",
    "maravilhoso", "qualidade", "chegou", "antes", "feliz", "lindo", "linda",
    "great", "good", "excellent", "love", "perfect", "fast", "recommend",
}
NEGATIVE_WORDS = {
    "ruim", "pessimo", "péssimo", "horrivel", "horrível", "nao", "não",
    "atraso", "atrasado", "demora", "demorou", "errado", "defeito",
    "quebrado", "cancelado", "problema", "decepcionado", "decepcionada",
    "nunca", "veio", "faltou", "bad", "terrible", "late", "broken", "never",
    "wrong", "problem", "disappointed",
}


def simple_sentiment(text) -> str:
    """Very lightweight keyword-based sentiment for PT/EN review comments."""
    if not isinstance(text, str) or not text.strip():
        return "no_comment"

    words = set(re.findall(r"[a-zà-ú]+", text.lower()))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)

    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    else:
        return "neutral"


def render_review_sentiment(df: pd.DataFrame, dim_reviews: pd.DataFrame):
    st.subheader("Review Sentiment vs Sales Impact")

    if "review_score" not in dim_reviews.columns or "order_id" not in dim_reviews.columns:
        st.warning("dim_reviews missing `review_score` or `order_id` columns.")
        return

    reviews = dim_reviews.copy()

    comment_col = None
    for candidate in ["review_comment_message", "review_comment_title"]:
        if candidate in reviews.columns:
            comment_col = candidate
            break

    if comment_col:
        reviews["text_sentiment"] = reviews[comment_col].apply(simple_sentiment)
    else:
        reviews["text_sentiment"] = "no_comment"

    def combined_sentiment(row):
        score = row.get("review_score")
        text_sent = row.get("text_sentiment")
        if pd.isna(score):
            return text_sent if text_sent != "no_comment" else "unknown"
        if score >= 4:
            base = "positive"
        elif score <= 2:
            base = "negative"
        else:
            base = "neutral"
        if text_sent in ("positive", "negative") and text_sent != base:
            return "mixed"
        return base

    reviews["sentiment"] = reviews.apply(combined_sentiment, axis=1)

    data = add_revenue(df.copy())
    merged = data.merge(
        reviews[["order_id", "review_score", "sentiment"]],
        left_on="id", right_on="order_id", how="left"
    )

    has_review = merged.dropna(subset=["review_score"])
    n_unique_orders = merged["id"].nunique()
    pct_with_review = (
        len(has_review.drop_duplicates("id")) / n_unique_orders * 100 if n_unique_orders else 0
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Avg Review Score", f"{has_review['review_score'].mean():.2f} / 5" if not has_review.empty else "N/A")
    col2.metric("% Orders with Review", f"{pct_with_review:.1f}%")
    col3.metric("Reviews Analyzed", f"{reviews['order_id'].nunique():,}")

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        score_dist = has_review.drop_duplicates("id")["review_score"].value_counts().sort_index().reset_index()
        score_dist.columns = ["review_score", "count"]
        fig = px.bar(score_dist, x="review_score", y="count", title="Distribution of Review Scores")
        fig.update_layout(xaxis_title="Review Score", yaxis_title="Orders")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        sent_dist = has_review.drop_duplicates("id")["sentiment"].value_counts().reset_index()
        sent_dist.columns = ["sentiment", "count"]
        fig = px.pie(sent_dist, names="sentiment", values="count", hole=0.4,
                      title="Sentiment Distribution (score + text)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Average Order Value by Review Score**")
    rev_by_score_rows = []
    for score, group in has_review.groupby("review_score"):
        unique_orders = group.drop_duplicates("id")
        n_orders = unique_orders["id"].nunique()
        total_rev = unique_orders["revenue"].sum()
        rev_by_score_rows.append({
            "review_score": score,
            "orders": n_orders,
            "avg_order_value": total_rev / n_orders if n_orders else 0,
        })
    rev_by_score = pd.DataFrame(rev_by_score_rows)
    fig = px.bar(rev_by_score, x="review_score", y="avg_order_value",
                  text="orders", title="Average Order Value by Review Score")
    fig.update_layout(xaxis_title="Review Score", yaxis_title="Avg Order Value (R$)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Average Review Score Over Time**")
    dated = merged.dropna(subset=["order_purchase_timestamp", "review_score"]).copy()
    dated["order_month"] = dated["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    monthly_score = dated.drop_duplicates("id").groupby("order_month")["review_score"].mean().reset_index()
    fig = px.line(monthly_score, x="order_month", y="review_score", markers=True)
    fig.update_layout(xaxis_title="Month", yaxis_title="Avg Review Score")
    st.plotly_chart(fig, use_container_width=True)

    if comment_col is None:
        st.info(
            "No review comment text column found — sentiment is based on `review_score` only."
        )

    with st.expander("View sample reviews with sentiment"):
        sample_cols = [c for c in ["order_id", "review_score", comment_col, "sentiment"] if c and c in reviews.columns]
        st.dataframe(reviews[sample_cols].head(500), use_container_width=True)


# ----------------------------------------------------------------------
# 9. Data Quality
# ----------------------------------------------------------------------
def render_data_quality(df: pd.DataFrame):
    st.subheader("Data Quality Monitoring")
    st.caption("Flags computed in `fact_orders` by the dbt gold-mart model.")

    flag_cols = {
        "has_invalid_delivery_date": "Delivered before purchase date",
        "is_overdue_delivery": "Overdue / never delivered",
        "is_high_value_product": "High-value item (> R$10,000)",
        "has_missing_delivery_date": "Missing delivery date (status = delivered)",
        "is_long_delivery": "Delivery took > 30 days",
        "has_missing_payment_info": "Missing payment info",
        "has_no_items": "Order has no line items",
    }

    available = [c for c in flag_cols if c in df.columns]
    if not available:
        st.warning("No data quality flag columns found in fact_orders.")
        return

    rows = []
    for col in available:
        flagged = int(df[col].fillna(False).sum())
        pct = (flagged / len(df) * 100) if len(df) else 0
        rows.append({
            "Check": flag_cols[col],
            "Flagged rows": flagged,
            "% of rows": round(pct, 2),
        })

    summary = pd.DataFrame(rows).sort_values("Flagged rows", ascending=False)

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = px.bar(
            summary, x="Check", y="Flagged rows", text="% of rows",
            title="Flagged Rows by Data Quality Check"
        )
        fig.update_layout(xaxis_title="", yaxis_title="Flagged rows")
        fig.update_xaxes(tickangle=30)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(summary, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Inspect flagged rows**")
    selected_check = st.selectbox(
        "Choose a check to drill into",
        options=available,
        format_func=lambda c: flag_cols[c],
    )

    flagged_df = df[df[selected_check].fillna(False)]
    st.write(f"{len(flagged_df):,} rows flagged for: **{flag_cols[selected_check]}**")
    display_cols = [
        c for c in [
            "id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_delivered_customer_date", "order_estimated_delivery_date",
            "price", "freight_value", "payment_type", "payment_value", selected_check,
        ] if c in flagged_df.columns
    ]
    st.dataframe(flagged_df[display_cols].head(500), use_container_width=True)


# ----------------------------------------------------------------------
# Main app
# ----------------------------------------------------------------------
def main():
    st.title("📦 Olist Gold Mart Dashboard")
    st.caption(
        "Interactive analytics built on top of the dbt gold-mart models: "
        "`fact_orders`, `dim_customers`, `dim_products`, `dim_sellers`, `dim_reviews`."
    )

    with st.spinner("Loading data from BigQuery..."):
        fact_orders = load_fact_orders()
        dim_customers = load_dim_customers()
        dim_products = load_dim_products()
        dim_sellers = load_dim_sellers()
        dim_reviews = load_dim_reviews()

    filtered_orders = build_sidebar(fact_orders)

    tabs = st.tabs([
        "Revenue Performance",
        "Seller Ranking",
        "Category Performance",
        "Payment Analysis",
        "Delivery Performance",
        "Customer Segmentation",
        "Geographic Heatmap",
        "Review Sentiment",
        "Data Quality",
    ])

    with tabs[0]:
        render_revenue_performance(filtered_orders)

    with tabs[1]:
        render_seller_performance(filtered_orders, dim_sellers, dim_reviews)

    with tabs[2]:
        render_category_performance(filtered_orders, dim_products)

    with tabs[3]:
        render_payment_analysis(filtered_orders)

    with tabs[4]:
        render_delivery_performance(filtered_orders)

    with tabs[5]:
        render_customer_segmentation(filtered_orders)

    with tabs[6]:
        render_geographic_heatmap(filtered_orders, dim_customers)

    with tabs[7]:
        render_review_sentiment(filtered_orders, dim_reviews)

    with tabs[8]:
        render_data_quality(fact_orders)  # unfiltered: monitor full table


if __name__ == "__main__":
    main()
