import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import io

st.set_page_config(page_title="BB Securities MTM", layout="wide")
st.title("🇧🇩 Bangladesh Bank Securities Data Dashboard")

# Connect to database
engine = create_engine(st.secrets["DATABASE_URL"])

# Fetch available dates for history
try:
    dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM daily_securities ORDER BY "Data_Date" DESC', engine)
    available_dates = dates_df["Data_Date"].tolist()
except:
    st.warning("No data found in the database yet.")
    st.stop()

# View mode and filters
view_mode = st.radio("Select View Mode", ["View Specific Date", "View Latest Available per Category (Smart Fallback)"], horizontal=True)
selected_cat = st.multiselect("Filter Category", ["T_Bonds", "T_Bills", "FRTB"], default=["T_Bonds", "T_Bills", "FRTB"])

if selected_cat:
    cat_str = ','.join([f"'{c}'" for c in selected_cat])
    
    if view_mode == "View Specific Date":
        selected_date = st.selectbox("Select Date", available_dates)
        query = f'SELECT * FROM daily_securities WHERE "Data_Date" = \'{selected_date}\' AND "Category" IN ({cat_str})'
        df = pd.read_sql(query, engine)
        file_suffix = selected_date
    else:
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
        file_suffix = "Latest"
    
    if df.empty:
        st.info(f"ℹ️ No data available for the selected options.")
    else:
        # --- EXECUTIVE SUMMARY METRICS ---
        st.markdown("### 📊 Portfolio Summary")
        
        # Create columns dynamically based on selected categories
        cols = st.columns(len(selected_cat))
        
        for idx, cat in enumerate(selected_cat):
            cat_df = df[df["Category"] == cat]
            count = len(cat_df)
            
            with cols[idx]:
                st.metric(label=f"Total {cat} Instruments", value=count)
                
                # If there's a numeric column for amounts (like Outstanding/Volume), we can sum it up safely
                numeric_cols = cat_df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    # Picks the last numeric column or a likely size column as a proxy for total volume
                    total_vol = cat_df[numeric_cols[-1]].sum()
                    if total_vol > 0:
                        st.caption(f"Total Volume / Metric: {total_vol:,.2f}")

        st.markdown("---")

        # Display Data Table
        if view_mode == "View Latest Available per Category (Smart Fallback)":
            st.markdown("##### 📅 Active Data Dates per Category:")
            summary_dates = df[["Category", "Data_Date"]].drop_duplicates()
            st.dataframe(summary_dates, use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.dataframe(df, use_container_width=True)

        # Download Button
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Securities", index=False)
        
        st.download_button(
            label="📥 Download Current View as Excel", 
            data=buffer.getvalue(), 
            file_name=f"BB_Securities_{file_suffix}.xlsx", 
            mime="application/vnd.ms-excel"
        )
else:
    st.info("Please select at least one category.")
