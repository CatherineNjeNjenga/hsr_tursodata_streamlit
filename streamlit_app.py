import streamlit as st

# Define pages with full control over title, icon, and URL
pg = st.navigation([
    st.Page("dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("pages/guest_scorecard.py", title="Guest Scorecard", icon=":material/person:"),
])

pg.run()