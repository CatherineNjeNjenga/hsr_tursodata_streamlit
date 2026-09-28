import streamlit as st
import libsql
import pandas as pd
import plotly.express as px

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="Dashboard | HSR Partnership Intelligence",
    page_icon=":material/dashboard:",
    layout="wide",
)

# ---------- TURSO CONNECTION (cached) ----------
@st.cache_resource
def get_connection():
    """Create a single Turso connection, reused across reruns."""
    return libsql.connect(
        database=st.secrets["turso"]["url"],
        auth_token=st.secrets["turso"]["token"],
    )

conn = get_connection()

# ---------- HELPER: RUN QUERY → DATAFRAME ----------
@st.cache_data(ttl=300)  # refresh every 5 minutes
def run_query(sql: str) -> pd.DataFrame:
    result = conn.execute(sql)
    rows = result.fetchall()
    columns = [desc[0] for desc in result.description]
    return pd.DataFrame(rows, columns=columns)

# ---------- HEADER ----------
st.title("📊 HSR Partnership Intelligence")
st.caption("Live recommendations data from the Hot Smart Rich podcast")

# ---------- SECTION 1: HEADLINE METRICS ----------
st.subheader("Overview")

metrics_sql = """
SELECT
    COUNT(*)                        AS total_recommendations,
    COUNT(DISTINCT brand)           AS unique_brands,
    COUNT(DISTINCT guest_name)      AS unique_guests,
    SUM(CASE WHEN link_type = 'ShopMy' THEN 1 ELSE 0 END) AS shopmy_links,
    SUM(CASE WHEN link_type = 'None'   THEN 1 ELSE 0 END) AS missing_links
FROM recommendations;
"""
m = run_query(metrics_sql).iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Recommendations", f"{int(m['total_recommendations']):,}")
c2.metric("Unique Brands", f"{int(m['unique_brands']):,}")
c3.metric("Unique Guests", f"{int(m['unique_guests']):,}")
c4.metric("ShopMy Links", f"{int(m['shopmy_links']):,}")
c5.metric("Missing Links", f"{int(m['missing_links']):,}")

st.divider()

# ---------- SECTION 2: BRAND LEADERBOARD ----------
st.subheader("🏆 Top 20 Brands by Recommendation Frequency")

brands_sql = """
SELECT
    brand,
    COUNT(*)                    AS recommendation_count,
    COUNT(DISTINCT guest_name)  AS guest_count,
    GROUP_CONCAT(DISTINCT main_category) AS categories
FROM recommendations
GROUP BY brand
ORDER BY recommendation_count DESC
LIMIT 20;
"""
brands = run_query(brands_sql)

fig_brands = px.bar(
    brands.sort_values("recommendation_count"),
    x="recommendation_count",
    y="brand",
    orientation="h",
    color="recommendation_count",
    color_continuous_scale="Purples",
    labels={"recommendation_count": "Recommendations", "brand": ""},
)
fig_brands.update_layout(showlegend=False, height=600, coloraxis_showscale=False)
st.plotly_chart(fig_brands, use_container_width=True)

with st.expander("View brand data as table"):
    st.dataframe(brands, use_container_width=True, hide_index=True)

st.divider()

# ---------- SECTION 3: CATEGORY BREAKDOWN ----------
st.subheader("📂 Category Breakdown")

col_left, col_right = st.columns(2)

# Main Category pie
cats_sql = """
SELECT main_category, COUNT(*) AS count
FROM recommendations
GROUP BY main_category
ORDER BY count DESC;
"""
cats = run_query(cats_sql)

fig_cats = px.pie(
    cats,
    names="main_category",
    values="count",
    hole=0.45,
    color_discrete_sequence=px.colors.qualitative.Set3,
)
fig_cats.update_traces(textposition="inside", textinfo="percent+label")
fig_cats.update_layout(showlegend=False, height=450)
col_left.plotly_chart(fig_cats, use_container_width=True)

# Price tier stacked bar by category
tiers_sql = """
SELECT main_category, price_tier, COUNT(*) AS count
FROM recommendations
GROUP BY main_category, price_tier;
"""
tiers = run_query(tiers_sql)

tier_order = ["Free", "Budget", "Mid-Range", "Premium", "Luxury", "Donation", "Varies", "Unknown"]
tiers["price_tier"] = pd.Categorical(tiers["price_tier"], categories=tier_order, ordered=True)

fig_tiers = px.bar(
    tiers,
    x="main_category",
    y="count",
    color="price_tier",
    barmode="stack",
    color_discrete_sequence=px.colors.sequential.Viridis,
    labels={"count": "Recommendations", "main_category": "", "price_tier": "Price Tier"},
)
fig_tiers.update_layout(height=450, xaxis_tickangle=-30)
col_right.plotly_chart(fig_tiers, use_container_width=True)

st.divider()

# ---------- SECTION 4: MONETIZATION GAP ----------
st.subheader("💰 Monetization Gap — Untapped Affiliate Opportunities")
st.caption("Recommendations with no affiliate link, ranked by brand frequency")

gap_sql = """
SELECT
    brand,
    main_category,
    price_tier,
    COUNT(*) AS recommendations_without_links
FROM recommendations
WHERE link_type = 'None'
GROUP BY brand, main_category, price_tier
ORDER BY recommendations_without_links DESC
LIMIT 25;
"""
gap = run_query(gap_sql)

if len(gap) == 0:
    st.success("No monetization gaps found — every recommendation has a link. 🎉")
else:
    fig_gap = px.bar(
        gap.sort_values("recommendations_without_links"),
        x="recommendations_without_links",
        y="brand",
        orientation="h",
        color="main_category",
        labels={
            "recommendations_without_links": "No Link",
            "brand": "",
            "main_category": "Category",
        },
    )
    fig_gap.update_layout(height=600, showlegend=True)
    st.plotly_chart(fig_gap, use_container_width=True)

    with st.expander("View gap data as table"):
        st.dataframe(gap, use_container_width=True, hide_index=True)

st.divider()
st.caption("Data source: Turso (libSQL) · Dashboard: Streamlit · Maintained by HSR Brand Partnerships")