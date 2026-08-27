import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# Page Configuration
st.set_page_config(
    page_title="Bangladesh Bank GSOM Valuation Dashboard",
    page_icon="📈",
    layout="wide"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

@st.cache_resource
def get_engine():
    if not DATABASE_URL:
        st.error("DATABASE_URL environment variable is missing.")
        return None
    return create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

engine = get_engine()

st.title("Bangladesh Bank GSOM Valuation Dashboard")
st.markdown("Automated Daily Secondary Market Valuation for Government Securities & Treasury Bills.")

# Navigation Tabs
tab_bonds, tab_bills = st.tabs(["🏛️ Treasury Bonds & Sukuk / FRTB", "💵 Treasury Bills (T-Bills)"])

# ==========================================
# 1. TREASURY BONDS & FRTB TAB
# ==========================================
with tab_bonds:
    st.subheader("Bonds & Securities Dashboard")
    if engine:
        try:
            with engine.connect() as conn:
                bond_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_securities ORDER BY "Data_Date" DESC', conn)
            
            if not bond_dates_df.empty:
                available_bond_dates = bond_dates_df["Data_Date"].tolist()
                
                # Range or Single Date Selection Option
                selection_mode = st.radio("Selection Mode (Bonds)", ["Single Date", "Date Range"], horizontal=True, key="bond_mode")
                
                if selection_mode == "Single Date":
                    selected_date = st.selectbox("Select Valuation Date", available_bond_dates, key="bond_single_date")
                    query_bonds = f"""
                        SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                               "Issue Date", "Maturity/ Expiry Date", "Remaining Maturity", 
                               "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date"
                        FROM public.daily_securities 
                        WHERE "Data_Date" = '{selected_date}'
                        ORDER BY "Sl. No." ASC
                    """
                else:
                    col_d1, col_d2 = st.columns(2)
                    start_date = col_d1.selectbox("Start Date", available_bond_dates, index=min(len(available_bond_dates)-1, 30), key="bond_start_date")
                    end_date = col_d2.selectbox("End Date", available_bond_dates, index=0, key="bond_end_date")
                    query_bonds = f"""
                        SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                               "Issue Date", "Maturity/ Expiry Date", "Remaining Maturity", 
                               "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date"
                        FROM public.daily_securities 
                        WHERE "Data_Date" BETWEEN '{start_date}' AND '{end_date}'
                        ORDER BY "Data_Date" DESC, "Sl. No." ASC
                    """

                with engine.connect() as conn:
                    bonds_df = pd.read_sql(query_bonds, conn)

                if not bonds_df.empty:
                    # Clean Numerics for Analytics
                    bonds_df["Market Yield Num"] = pd.to_numeric(bonds_df["Market Yield"], errors="coerce")
                    bonds_df["Outstanding Num"] = pd.to_numeric(bonds_df["Outstanding BDT (in Mill)"], errors="coerce")

                    st.markdown("### 📊 Market Summary by Instrument Type")
                    
                    # Group by Securities Type / Category for Dashboard Metrics
                    summary_df = bonds_df.groupby("Securities Type").agg(
                        Count=("ISIN", "count"),
                        Total_Outstanding=("Outstanding Num", "sum"),
                        Avg_Yield=("Market Yield Num", "mean")
                    ).reset_index()

                    cols = st.columns(len(summary_df) if len(summary_df) > 0 else 1)
                    for idx, row in summary_df.iterrows():
                        with cols[idx % len(cols)]:
                            st.metric(
                                label=f"{row['Securities Type']}",
                                value=f"{row['Count']} Inst.",
                                delta=f"Out: {row['Total_Outstanding']:,.1f} M | Yield: {row['Avg_Yield']:.2f}%"
                            )

                    st.divider()
                    st.subheader("Detailed Data View & Download")
                    st.dataframe(bonds_df.drop(columns=["Market Yield Num", "Outstanding Num"], errors="ignore"), use_container_width=True)

                    # Download Button
                    csv_data = bonds_df.drop(columns=["Market Yield Num", "Outstanding Num"], errors="ignore").to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Bond Data as CSV", data=csv_data, file_name="bonds_valuation_report.csv", mime="text/csv")
                else:
                    st.info("No records found for the selected range.")
            else:
                st.info("No daily securities records found yet.")
        except Exception as e:
            st.error(f"Error querying securities: {e}")

# ==========================================
# 2. TREASURY BILLS TAB
# ==========================================
with tab_bills:
    st.subheader("Treasury Bills Dashboard")
    if engine:
        try:
            with engine.connect() as conn:
                bill_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_bills ORDER BY "Data_Date" DESC', conn)
            
            if not bill_dates_df.empty:
                available_bill_dates = bill_dates_df["Data_Date"].tolist()
                
                bill_selection_mode = st.radio("Selection Mode (T-Bills)", ["Single Date", "Date Range"], horizontal=True, key="bill_mode")
                
                if bill_selection_mode == "Single Date":
                    selected_bill_date = st.selectbox("Select T-Bill Valuation Date", available_bill_dates, key="bill_single_date")
                    query_bills = f"""
                        SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                               "Issue Date", "Maturity/ Expiry Date", "Issue Price",
                               "Remaining Maturity", "Market Yield", "Market Price", 
                               "Outstanding BDT (in Mill)", "Data_Date"
                        FROM public.daily_bills 
                        WHERE "Data_Date" = '{selected_bill_date}'
                        ORDER BY "Sl. No." ASC
                    """
                else:
                    col_bd1, col_bd2 = st.columns(2)
                    start_bdate = col_bd1.selectbox("Start Date", available_bill_dates, index=min(len(available_bill_dates)-1, 30), key="bill_start_date")
                    end_bdate = col_bd2.selectbox("End Date", available_bill_dates, index=0, key="bill_end_date")
                    query_bills = f"""
                        SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                               "Issue Date", "Maturity/ Expiry Date", "Issue Price",
                               "Remaining Maturity", "Market Yield", "Market Price", 
                               "Outstanding BDT (in Mill)", "Data_Date"
                        FROM public.daily_bills 
                        WHERE "Data_Date" BETWEEN '{start_bdate}' AND '{end_bdate}'
                        ORDER BY "Data_Date" DESC, "Sl. No." ASC
                    """

                with engine.connect() as conn:
                    bills_df = pd.read_sql(query_bills, conn)

                if not bills_df.empty:
                    bills_df["Market Yield Num"] = pd.to_numeric(bills_df["Market Yield"], errors="coerce")
                    bills_df["Outstanding Num"] = pd.to_numeric(bills_df["Outstanding BDT (in Mill)"], errors="coerce")

                    st.markdown("### 📊 T-Bill Market Summary by Tenor Type")
                    
                    bill_summary = bills_df.groupby("Securities Type").agg(
                        Count=("ISIN", "count"),
                        Total_Outstanding=("Outstanding Num", "sum"),
                        Avg_Yield=("Market Yield Num", "mean")
                    ).reset_index()

                    b_cols = st.columns(len(bill_summary) if len(bill_summary) > 0 else 1)
                    for idx, row in bill_summary.iterrows():
                        with b_cols[idx % len(b_cols)]:
                            st.metric(
                                label=f"{row['Securities Type']}",
                                value=f"{row['Count']} Bills",
                                delta=f"Out: {row['Total_Outstanding']:,.1f} M | Yield: {row['Avg_Yield']:.2f}%"
                            )

                    st.divider()
                    st.subheader("Detailed T-Bill View & Download")
                    st.dataframe(bills_df.drop(columns=["Market Yield Num", "Outstanding Num"], errors="ignore"), use_container_width=True)

                    # Download Button
                    csv_bills = bills_df.drop(columns=["Market Yield Num", "Outstanding Num"], errors="ignore").to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download T-Bill Data as CSV", data=csv_bills, file_name="tbills_valuation_report.csv", mime="text/csv")
                else:
                    st.info("No T-Bill records found for the selected range.")
            else:
                st.info("No T-Bill records found in the database yet.")
        except Exception as e:
            st.error(f"Error querying T-Bills: {e}")
