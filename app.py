import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import io

st.set_page_config(page_title="BB Securities MTM", layout="wide")
st.title("🇧🇩 Bangladesh Bank Securities Data (Latest Available)")

# Connect to database
engine = create_engine(st.secrets["DATABASE_URL"])

# Category selection
selected_cat = st.multiselect("Filter Category", ["T_Bonds", "T_Bills", "FRTB"], default=["T_Bonds", "T_Bills", "FRTB"])

if selected_cat:
    cat_str = ','.join([f"'{c}'" for c in selected_cat])
    
    # Query to get the latest data date for each selected category independently
    query = f"""
        SELECT * FROM daily_securities 
        WHERE "Category" IN ({cat_str}) 
        AND "Data_Date" IN (
            SELECT MAX("Data_Date") 
            FROM daily_securities 
            WHERE "Category" IN ({cat_str})
            GROUP BY "Category"
        )
    """
    df = pd.read_sql(query, engine)
    
    if df.empty:
        st.info("ℹ️ No data found in the database yet.")
    else:
        # Show which dates are being displayed
        latest_dates = df[["Category", "Data_Date"]].drop_duplicates()
        st.markdown("**Displaying latest available records per category:**")
        st.dataframe(latest_dates, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.dataframe(df, use_container_width=True)

        # Download Button
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Latest_Securities", index=False)
        
        st.download_button(
            label="📥 Download Latest Data as Excel", 
            data=buffer.getvalue(), 
            file_name="BB_Securities_Latest.xlsx", 
            mime="application/vnd.ms-excel"
        )
else:
    st.info("Please select at least one category.")
