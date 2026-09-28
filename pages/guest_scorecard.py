import streamlit as st
import libsql
import pandas as pd
import plotly.express as px

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="Guest Scorecard | HSR Partnership Intelligence",
    page_icon=":material/person:",
    layout="wide",
)

# ---------- TURSO CONNECTION (cached) ----------
@st.cache_resource
def get_connection():
    return libsql.connect(
        database=st.secrets["turso"]["url"],
        auth_token=st.secrets["turso"]["token"],
    )

conn = get_connection()

# ---------- HELPER: RUN QUERY → DATAFRAME ----------
@st.cache_data(ttl=300)
def run_query(sql: str) -> pd.DataFrame:
    result = conn.execute(sql)
    rows = result.fetchall()
    columns = [desc[0] for desc in result.description]
    return pd.DataFrame(rows, columns=columns)

# ---------- HEADER ----------
st.title("👤 Guest Scorecard")
st.caption("Performance metrics for every guest who has appeared on HSR")

# ---------- SECTION 1: HEADLINE METRICS ----------
metrics_sql = """
SELECT
    COUNT(DISTINCT guest_name)                    AS total_guests,
    COUNT(DISTINCT guest_type)                    AS guest_types,
    ROUND(AVG(recommendations), 1)                AS avg_recs_per_guest,
    MAX(recommendations)                          AS max_recs
FROM (
    SELECT guest_name, guest_type, COUNT(*) AS recommendations
    FROM recommendations
    WHERE guest_role = 'Guest'
    GROUP BY guest_name, guest_type
);
"""
m = run_query(metrics_sql).iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Guests", f"{int(m['total_guests']):,}")
c2.metric("Guest Types", f"{int(m['guest_types']):,}")
c3.metric("Avg Recs / Guest", f"{m['avg_recs_per_guest']}")
c4.metric("Most Recs (Single Guest)", f"{int(m['max_recs']):,}")

st.divider()

# ---------- SECTION 2: GUEST LEADERBOARD ----------
st.subheader("🏆 Guests by Recommendation Volume")

guests_sql = """
SELECT
    guest_name,
    guest_type,
    COUNT(*)                        AS recommendation_count,
    COUNT(DISTINCT brand)           AS unique_brands,
    COUNT(DISTINCT main_category)   AS category_diversity,
    ROUND(AVG(price_min), 0)        AS avg_price_min
FROM recommendations
WHERE guest_role = 'Guest'
GROUP BY guest_name, guest_type
ORDER BY recommendation_count DESC;
"""
guests = run_query(guests_sql)

fig_guests = px.bar(
    guests.sort_values("recommendation_count"),
    x="recommendation_count",
    y="guest_name",
    orientation="h",
    color="guest_type",
    labels={
        "recommendation_count": "Recommendations",
        "guest_name": "",
        "guest_type": "Guest Type",
    },
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_guests.update_layout(height=1000, showlegend=True)
st.plotly_chart(fig_guests, use_container_width=True)

with st.expander("View guest data as table"):
    st.dataframe(guests, use_container_width=True, hide_index=True)

st.divider()

# ---------- SECTION 3: GUEST TYPE BREAKDOWN ----------
st.subheader("🎭 Recommendations by Guest Type")

col_left, col_right = st.columns([1, 2])

type_sql = """
SELECT guest_type, COUNT(*) AS count
FROM recommendations
WHERE guest_role = 'Guest'
GROUP BY guest_type
ORDER BY count DESC;
"""
types = run_query(type_sql)

fig_type = px.pie(
    types,
    names="guest_type",
    values="count",
    hole=0.45,
    color_discrete_sequence=px.colors.qualitative.Pastel,
)
fig_type.update_traces(textposition="inside", textinfo="percent+label")
fig_type.update_layout(showlegend=False, height=400)
col_left.plotly_chart(fig_type, use_container_width=True)

diversity_sql = """
SELECT
    guest_type,
    ROUND(AVG(recommendations), 1) AS avg_recs_per_guest,
    COUNT(DISTINCT guest_name)     AS guest_count
FROM (
    SELECT guest_name, guest_type, COUNT(*) AS recommendations
    FROM recommendations
    WHERE guest_role = 'Guest'
    GROUP BY guest_name, guest_type
)
GROUP BY guest_type
ORDER BY avg_recs_per_guest DESC;
"""
diversity = run_query(diversity_sql)

fig_div = px.bar(
    diversity,
    x="guest_type",
    y="avg_recs_per_guest",
    color="guest_type",
    text="avg_recs_per_guest",
    labels={
        "avg_recs_per_guest": "Avg Recommendations per Guest",
        "guest_type": "",
    },
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_div.update_traces(textposition="outside")
fig_div.update_layout(showlegend=False, height=400)
col_right.plotly_chart(fig_div, use_container_width=True)

st.divider()

# ---------- SECTION 4: HOST CO-RECOMMENDATION TRACKER ----------
st.subheader("🤝 Host Co-Recommendation Tracker")
st.caption("Brands recommended by both the host and at least one guest")

corec_sql = """
SELECT
    brand,
    COUNT(DISTINCT CASE WHEN guest_role = 'Host' THEN guest_name END) AS host_mentions,
    COUNT(DISTINCT CASE WHEN guest_role = 'Guest' THEN guest_name END) AS guest_mentions,
    COUNT(*) AS total_mentions
FROM recommendations
GROUP BY brand
HAVING host_mentions > 0 AND guest_mentions > 0
ORDER BY total_mentions DESC
LIMIT 20;
"""
corec = run_query(corec_sql)

if len(corec) == 0:
    st.info("No host-guest co-recommendations found yet.")
else:
    fig_corec = px.bar(
        corec.sort_values("total_mentions"),
        x="total_mentions",
        y="brand",
        orientation="h",
        color="host_mentions",
        labels={
            "total_mentions": "Total Mentions",
            "brand": "",
            "host_mentions": "Host Mentions",
        },
        color_continuous_scale="Viridis",
    )
    fig_corec.update_layout(height=600, coloraxis_showscale=True)
    st.plotly_chart(fig_corec, use_container_width=True)

    with st.expander("View co-recommendation data as table"):
        st.dataframe(corec, use_container_width=True, hide_index=True)

st.divider()

# ---------- SECTION 5: CATEGORY PREFERENCES BY GUEST TYPE ----------
st.subheader("📂 Category Preferences by Guest Type")

cat_pref_sql = """
SELECT
    guest_type,
    main_category,
    COUNT(*) AS count
FROM recommendations
WHERE guest_role = 'Guest'
GROUP BY guest_type, main_category
ORDER BY guest_type, count DESC;
"""
cat_pref = run_query(cat_pref_sql)

fig_pref = px.bar(
    cat_pref,
    x="guest_type",
    y="count",
    color="main_category",
    barmode="stack",
    labels={
        "count": "Recommendations",
        "guest_type": "",
        "main_category": "Category",
    },
    color_discrete_sequence=px.colors.qualitative.Set3,
)
fig_pref.update_layout(height=500, xaxis_tickangle=-15)
st.plotly_chart(fig_pref, use_container_width=True)

st.divider()
st.caption("Data source: Turso (libSQL) · Dashboard: Streamlit · Maintained by HSR Brand Partnerships")