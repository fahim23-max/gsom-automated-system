import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import io

st.set_page_config(page_title="BB Securities MTM", layout="wide")
st.title("🇧🇩 Bangladesh Bank Securities Data")

# Connect to database
engine = create_engine(st.secrets["DATABASE_URL"])

# Fetch dates
try:
    dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM daily_securities ORDER BY "Data_Date" DESC', engine)
    available_dates = dates_df["Data_Date"].tolist()
except:
    st.warning("No data found in the database yet. The scraper might still be running!")
    st.stop()

# Filters
col1, col2 = st.columns(2)
with col1:
    selected_date = st.selectbox("Select Date", available_dates)
with col2:
    selected_cat = st.multiselect("Filter Category", ["T_Bonds", "T_Bills", "FRTB"], default=["T_Bonds", "T_Bills", "FRTB"])

# Get filtered data
if selected_cat:
    cat_str = ','.join([f"'{c}'" for c in selected_cat])
    query = f'SELECT * FROM daily_securities WHERE "Data_Date" = \'{selected_date}\' AND "Category" IN ({cat_str})'
    df = pd.read_sql(query, engine)
    
    st.dataframe(df, use_container_width=True)

    # Download Button
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Securities", index=False)
    
    st.download_button(label="📥 Download Data as Excel", data=buffer.getvalue(), file_name=f"BB_Securities_{selected_date}.xlsx", mime="application/vnd.ms-excel")
else:
    st.info("Please select at least one category.")
