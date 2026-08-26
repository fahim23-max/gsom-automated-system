import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import io
from datetime import date, timedelta

st.set_page_config(page_title="BB Securities MTM", layout="wide")
st.title("🇧🇩 Bangladesh Bank Securities Data Dashboard")

# Connect to database using transaction pooler settings
engine = create_engine(st.secrets["DATABASE_URL"], connect_args={'prepare_threshold': None})

# Fetch available dates for history
try:
    dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM daily_securities ORDER BY "Data_Date" DESC', engine)
    available_dates = dates_df["Data_Date"].tolist()
    parsed_dates = pd.to_datetime(dates_df["Data_Date"])
    min_db_date = parsed_dates.min().date()
    max_db_date = parsed_dates.max().date()
except Exception as e:
    min_db_date = date(2025, 1, 1)
    max_db_date = date.today()

# View mode and filters
view_mode = st.radio("Select View Mode", ["View Specific Date", "View Date Range", "View Latest Available per Category (Smart Fallback)"], horizontal=True)
selected_cat = st.multiselect("Filter Category", ["T_Bonds", "T_Bills", "FRTB"], default=["T_Bonds", "T_Bills", "FRTB"])

if selected_cat:
    cat_str = ','.join([f"'{c}'" for c in selected_cat])
    
    if view_mode == "View Specific Date":
        selected_date = st.selectbox("Select Date", available_dates)
        query = f'SELECT * FROM daily_securities WHERE "Data_Date" = \'{selected_date}\' AND "Category" IN ({cat_str})'
        df = pd.read_sql(query, engine)
        file_suffix = selected_date
        
    elif view_mode == "View Date Range":
        # Unrestricted date pickers without min/max locks so you can freely type or select any range
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_d = st.date_input("Start Date", value=max_db_date - timedelta(days=7))
        with col_d2:
            end_d = st.date_input("End Date", value=max_db_date)
            
        query = f'SELECT * FROM daily_securities WHERE "Category" IN ({cat_str}) ORDER BY "Data_Date" DESC'
        df = pd.read_sql(query, engine)
        
        if not df.empty and "Data_Date" in df.columns:
            df["Data_Date"] = pd.to_datetime(df["Data_Date"]).dt.date
            df = df[(df["Data_Date"] >= start_d) & (df["Data_Date"] <= end_d)]
            
        file_suffix = f"{start_d}_to_{end_d}"
        
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
        st.info(f"ℹ️ No data available for the selected options or date range.")
    else:
        # --- PREPARE DATES FOR MATRIX CALCULATIONS ---
        if "Maturity/ Expiry Date" in df.columns:
            df["Maturity/ Expiry Date"] = pd.to_datetime(df["Maturity/ Expiry Date"], errors='coerce')
        if "Data_Date" in df.columns:
            df["Data_Date"] = pd.to_datetime(df["Data_Date"], errors='coerce')

        # --- BUILD SUMMARY MATRIX (IN CRORE) WITH STYLING ---
        st.markdown("### 📊 Portfolio Summary Matrix (Amounts in BDT Crore)")
        
        matrix_data = {"Metric": ["Count", "Outstanding", "Maturity in next 30 days"]}
        
        for cat in selected_cat:
            cat_df = df[df["Category"] == cat]
            count_val = len(cat_df)
            
            outstand_val = 0.0
            if "Outstanding BDT (in Mill)" in cat_df.columns and not cat_df.empty:
                outstand_mill = pd.to_numeric(cat_df["Outstanding BDT (in Mill)"].astype(str).str.replace(',', ''), errors='coerce').sum()
                outstand_val = outstand_mill / 10.0
            
            mat_val = 0.0
            if "Maturity/ Expiry Date" in cat_df.columns and not cat_df["Data_Date"].isna().all() and "Outstanding BDT (in Mill)" in cat_df.columns:
                base_date = cat_df["Data_Date"].max()
                next_month_end = base_date + pd.Timedelta(days=30)
                maturing_soon = cat_df[
                    (cat_df["Maturity/ Expiry Date"] >= base_date) & 
                    (cat_df["Maturity/ Expiry Date"] <= next_month_end)
                ]
                mat_mill = pd.to_numeric(maturing_soon["Outstanding BDT (in Mill)"].astype(str).str.replace(',', ''), errors='coerce').sum()
                mat_val = mat_mill / 10.0
            
            matrix_data[cat] = [
                f"{count_val:,}",
                f"BDT {outstand_val:,.2f} Cr",
                f"BDT {mat_val:,.2f} Cr"
            ]
            
        matrix_df = pd.DataFrame(matrix_data).set_index("Metric")
        
        # Apply professional styling
        styled_matrix = matrix_df.style.set_table_styles([
            {"selector": "th", "props": [("background-color", "#0e1117"), ("color", "white"), ("font-family", "sans-serif"), ("font-size", "15px"), ("text-align", "center"), ("padding", "10px")]},
            {"selector": "td", "props": [("font-family", "sans-serif"), ("font-size", "14px"), ("text-align", "center"), ("padding", "8px"), ("border", "1px solid #e0e0e0")]},
            {"selector": "th.row_heading", "props": [("background-color", "#f0f2f6"), ("color", "#262730"), ("font-weight", "bold")]}
        ])
        
        st.markdown(styled_matrix.to_html(), unsafe_allow_html=True)

        st.markdown("---")

        # --- DETAILED SECURITY-WISE DATA TABLE ---
        st.markdown("### 📋 Detailed Security-wise Data")
        
        if view_mode == "View Latest Available per Category (Smart Fallback)":
            st.markdown("##### 📅 Active Data Dates per Category:")
            summary_dates = df[["Category", "Data_Date"]].drop_duplicates()
            summary_dates["Data_Date"] = summary_dates["Data_Date"].dt.strftime('%Y-%m-%d')
            st.dataframe(summary_dates, use_container_width=True, hide_index=True)
            st.markdown("---")
            
        st.dataframe(df, use_container_width=True)

        # --- DOWNLOAD OPTIONS ---
        st.markdown("### 📥 Export Options")
        col_dl1, col_dl2 = st.columns(2)
        
        with col_dl1:
            buffer_current = io.BytesIO()
            with pd.ExcelWriter(buffer_current, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="Securities", index=False)
            
            st.download_button(
                label=f"📥 Download Current View ({file_suffix})", 
                data=buffer_current.getvalue(), 
                file_name=f"BB_Securities_{file_suffix}.xlsx", 
                mime="application/vnd.ms-excel"
            )
            
        with col_dl2:
            history_query = f'SELECT * FROM daily_securities WHERE "Category" IN ({cat_str}) ORDER BY "Data_Date" DESC'
            df_history = pd.read_sql(history_query, engine)
            
            buffer_history = io.BytesIO()
            with pd.ExcelWriter(buffer_history, engine='openpyxl') as writer:
                df_history.to_excel(writer, sheet_name="Full_History", index=False)
                
            st.download_button(
                label="📥 Download Complete Database History", 
                data=buffer_history.getvalue(), 
                file_name="BB_Securities_Full_History.xlsx", 
                mime="application/vnd.ms-excel"
            )
else:
    st.info("Please select at least one category.")
