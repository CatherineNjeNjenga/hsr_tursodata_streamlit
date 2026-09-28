import streamlit as st
import libsql

st.title("My Turso Cloud Database App")

# Securely fetch connection keys from Streamlit Cloud dashboard settings
db_url = st.secrets["turso"]["url"]
auth_token = st.secrets["turso"]["auth_token"]

try:
    # Connect to your remote Turso Database
    conn = libsql.connect(database=db_url, auth_token=auth_token)
    cursor = conn.cursor()

    st.success("Successfully connected to Turso!")

    # Optional: Uncomment these lines if you want to pull data immediately
    # cursor.execute("SELECT * FROM your_table_name LIMIT 10;")
    # rows = cursor.fetchall()
    # st.write(rows)

except Exception as e:
    st.error(f"An error occurred: {e}")
