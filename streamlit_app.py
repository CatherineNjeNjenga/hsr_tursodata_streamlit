import streamlit as st
import libsql
import pandas as pd

# Set page configuration for a wider, cleaner dashboard look
st.set_page_config(page_title="HSR Dashboard", layout="wide")

st.title("📈 Hot Smart Rich Automated Data Dashboard")
st.write("This dashboard is powered by live data scraped via GitHub Actions and safely stored in Turso.")

# Securely pull connection parameters from Streamlit's advanced settings vault
db_url = st.secrets["turso"]["url"]
auth_token = st.secrets["turso"]["auth_token"]

try:
    # Open connection to your Turso cluster
    conn = libsql.connect(database=db_url, auth_token=auth_token)
    
    # 1. Fetching the total record metric safely
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scraped_analytics;")
    total_count = cursor.fetchone()[0]
    cursor.close()

    # 2. Pulling data rows using Pandas to make building layout graphics easy
    # This queries your table and structures it instantly as a dataframe spreadsheet layout
    query = "SELECT guest_name, product_name, logged_at FROM scraped_analytics ORDER BY logged_at DESC;"
    df = pd.read_sql_query(query, conn)

    # Display KPI metrics cards at the top row of the app interface
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Total Scraped Records", value=total_count)
    with col2:
        if not df.empty:
            st.metric(label="Last Synced Update", value=str(df['logged_at'].iloc[0]))
        else:
            st.metric(label="Last Synced Update", value="No data sync yet")

    st.markdown("---")

    # Display Data Section
    if not df.empty:
        st.subheader("📊 Latest Extracted Guest Product Profiles")
        
        # Interactive Search Filters inside Streamlit
        search_query = st.text_input("🔍 Filter dashboard rows by guest name:")
        if search_query:
            df = df[df['guest_name'].str.contains(search_query, case=False, na=False)]

        # Renders an interactive spreadsheet view right inside your browser window frame
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    else:
        st.info("Your database table is currently connected but empty. Fire up your GitHub Action manually to log the first batch of web data!")

except Exception as e:
    st.error(f"❌ Frontend dashboard extraction error: {e}")
    st.info("Double-check that your table schema matches 'scraped_analytics' and your database tokens match.")

