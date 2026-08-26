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
        # --- PREPARE DATE COLUMNS FOR MATURITY CALCULATIONS ---
        # Convert Maturity/Expiry Date to datetime format for calculations
        if "Maturity/ Expiry Date" in df.columns:
            df["Maturity/ Expiry Date"] = pd.to_datetime(df["Maturity/ Expiry Date"], errors='coerce')
        if "Data_Date" in df.columns:
            df["Data_Date"] = pd.to_datetime(df["Data_Date"], errors='coerce')

        # --- EXECUTIVE SUMMARY METRICS ---
        st.markdown("### 📊 Portfolio Summary & Upcoming Maturities")
        
        cols = st.columns(len(selected_cat))
        
        for idx, cat in enumerate(selected_cat):
            cat_df = df[df["Category"] == cat]
            count = len(cat_df)
            
            with cols[idx]:
                st.metric(label=f"Total {cat} Instruments", value=count)
                
                # Total Outstanding BDT calculation
                if "Outstanding BDT" in cat_df.columns:
                    # Clean up string commas if present and convert to numeric
                    outstanding_series = pd.to_numeric(cat_df["Outstanding BDT"].astype(str).str.replace(',', ''), errors='coerce')
                    total_outstand = outstanding_series.sum()
                    st.markdown(f"**Total Outstanding:** BDT {total_outstand:,.2f}")
                    
                    # Upcoming Month's Maturity calculation (Next 30 Days from current row's Data_Date)
                    if "Maturity/ Expiry Date" in cat_df.columns and not cat_df["Data_Date"].isna().all():
                        # Use the max data date in this subset as the baseline "current" date
                        base_date = cat_df["Data_Date"].max()
                        next_month_end = base_date + pd.Timedelta(days=30)
                        
                        # Filter for bonds maturing within the next 30 days
                        maturing_soon = cat_df[
                            (cat_df["Maturity/ Expiry Date"] >= base_date) & 
                            (cat_df["Maturity/ Expiry Date"] <= next_month_end)
                        ]
                        
                        maturing_amt = pd.to_numeric(maturing_soon["Outstanding BDT"].astype(str).str.replace(',', ''), errors='coerce').sum()
                        st.markdown(f"⏳ **Maturing (Next 30 Days):** BDT {maturing_amt:,.2f}")

        st.markdown("---")

        # Display Data Table
        if view_mode == "View Latest Available per Category (Smart Fallback)":
            st.markdown("##### 📅 Active Data Dates per Category:")
            summary_dates = df[["Category", "Data_Date"]].drop_duplicates()
            # Convert back to string for clean display
            summary_dates["Data_Date"] = summary_dates["Data_Date"].dt.strftime('%Y-%m-%d')
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
