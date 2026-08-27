import os
import io
import streamlit as st
import pandas as pd
from datetime import timedelta
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

st.title("🏛️ Bangladesh Bank GSOM Valuation Dashboard")
st.markdown("Automated Daily Secondary Market Valuation for Government Securities & Treasury Bills.")
st.divider()

# Navigation Tabs
tab_bonds, tab_bills = st.tabs(["📊 Treasury Bonds & Sukuk / FRTB", "💵 Treasury Bills (T-Bills)"])

# ==========================================
# 1. TREASURY BONDS & FRTB TAB
# ==========================================
with tab_bonds:
    st.subheader("Bonds & Securities Market Overview")
    if engine:
        try:
            with engine.connect() as conn:
                bond_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_securities ORDER BY "Data_Date" DESC', conn)
            
            if not bond_dates_df.empty:
                available_bond_dates = bond_dates_df["Data_Date"].tolist()
                
                col_f1, col_f2 = st.columns([2, 3])
                with col_f1:
                    selection_mode = st.radio("Selection Mode", ["Single Date", "Date Range"], horizontal=True, key="bond_mode")
                
                if selection_mode == "Single Date":
                    with col_f2:
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
                    with col_f2:
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
                    bonds_df["Market Yield Num"] = pd.to_numeric(bonds_df["Market Yield"], errors="coerce")
                    bonds_df["Outstanding Num"] = pd.to_numeric(bonds_df["Outstanding BDT (in Mill)"], errors="coerce")
                    bonds_df["Outstanding (Crore)"] = bonds_df["Outstanding Num"] / 10.0
                    bonds_df["Maturity Date Parsed"] = pd.to_datetime(bonds_df["Maturity/ Expiry Date"], errors="coerce", format="mixed")
                    bonds_df["Data_Date_Parsed"] = pd.to_datetime(bonds_df["Data_Date"])

                    baseline_date = bonds_df["Data_Date_Parsed"].max()
                    summary_source_df = bonds_df[bonds_df["Data_Date_Parsed"] == baseline_date].drop_duplicates(subset=["ISIN"])

                    st.markdown(f"### 📈 Summary by Instrument Type (Snapshot as of {baseline_date.strftime('%Y-%m-%d')})")
                    summary_df = summary_source_df.groupby("Securities Type").agg(
                        Instrument_Count=("ISIN", "count"),
                        Total_Outstanding_Crore=("Outstanding (Crore)", "sum"),
                        Average_Yield=("Market Yield Num", "mean")
                    ).reset_index()

                    summary_df["Total_Outstanding_Crore"] = summary_df["Total_Outstanding_Crore"].map("{:,.2f} Cr".format)
                    summary_df["Average_Yield"] = summary_df["Average_Yield"].map("{:.2f}%".format)
                    summary_df.columns = ["Securities Type", "Total Count", "Total Outstanding (BDT Crore)", "Average Market Yield"]
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)

                    thirty_days_later = baseline_date + timedelta(days=30)
                    maturing_bonds = summary_source_df[
                        (summary_source_df["Maturity Date Parsed"] >= baseline_date) & 
                        (summary_source_df["Maturity Date Parsed"] <= thirty_days_later)
                    ]

                    st.markdown(f"### ⏳ Maturities in Next 30 Days (from highest date: {baseline_date.strftime('%Y-%m-%d')})")
                    if not maturing_bonds.empty:
                        total_maturing_crore = maturing_bonds["Outstanding (Crore)"].sum()
                        st.metric(label="Total Amount Maturing", value=f"{total_maturing_crore:,.2f} Crore BDT", delta=f"{len(maturing_bonds)} Instruments")
                        
                        display_mat_bonds = maturing_bonds.drop(columns=["Market Yield Num", "Outstanding Num", "Maturity Date Parsed", "Data_Date_Parsed"], errors="ignore")
                        st.dataframe(display_mat_bonds, use_container_width=True)
                    else:
                        st.info("No bond instruments maturing in the 30 days following the highest date in this range.")

                    st.markdown("### 📋 Detailed Records (Full Range History)")
                    display_bonds = bonds_df.drop(columns=["Market Yield Num", "Outstanding Num", "Maturity Date Parsed", "Data_Date_Parsed"], errors="ignore")
                    st.dataframe(display_bonds, use_container_width=True)

                    # Excel Export
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        display_bonds.to_excel(writer, index=False, sheet_name='Bonds_Valuation')
                    excel_data_bonds = output.getvalue()

                    st.download_button(
                        label="📥 Download Bond Data (Excel)",
                        data=excel_data_bonds,
                        file_name="bonds_valuation_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_bonds_excel"
                    )
                else:
                    st.warning("No records found for the selected range.")
            else:
                st.info("No daily securities records found yet.")
        except Exception as e:
            st.error(f"Error querying securities: {e}")

# ==========================================
# 2. TREASURY BILLS TAB
# ==========================================
with tab_bills:
    st.subheader("Treasury Bills Market Overview")
    if engine:
        try:
            with engine.connect() as conn:
                bill_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_bills ORDER BY "Data_Date" DESC', conn)
            
            if not bill_dates_df.empty:
                available_bill_dates = bill_dates_df["Data_Date"].tolist()
                
                col_bf1, col_bf2 = st.columns([2, 3])
                with col_bf1:
                    bill_selection_mode = st.radio("Selection Mode", ["Single Date", "Date Range"], horizontal=True, key="bill_mode")
                
                if bill_selection_mode == "Single Date":
                    with col_bf2:
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
                    with col_bf2:
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
                    bills_df["Outstanding (Crore)"] = bills_df["Outstanding Num"] / 10.0
                    bills_df["Maturity Date Parsed"] = pd.to_datetime(bills_df["Maturity/ Expiry Date"], errors="coerce", format="mixed")
                    bills_df["Data_Date_Parsed"] = pd.to_datetime(bills_df["Data_Date"])

                    baseline_bill_date = bills_df["Data_Date_Parsed"].max()
                    summary_bill_source = bills_df[bills_df["Data_Date_Parsed"] == baseline_bill_date].drop_duplicates(subset=["ISIN"])

                    st.markdown(f"### 📈 Summary by Tenor Type (Snapshot as of {baseline_bill_date.strftime('%Y-%m-%d')})")
                    bill_summary = summary_bill_source.groupby("Securities Type").agg(
                        Instrument_Count=("ISIN", "count"),
                        Total_Outstanding_Crore=("Outstanding (Crore)", "sum"),
                        Average_Yield=("Market Yield Num", "mean")
                    ).reset_index()

                    bill_summary["Total_Outstanding_Crore"] = bill_summary["Total_Outstanding_Crore"].map("{:,.2f} Cr".format)
                    bill_summary["Average_Yield"] = bill_summary["Average_Yield"].map("{:.2f}%".format)
                    bill_summary.columns = ["Securities Type", "Total Count", "Total Outstanding (BDT Crore)", "Average Market Yield"]
                    st.dataframe(bill_summary, use_container_width=True, hide_index=True)

                    thirty_days_later_bills = baseline_bill_date + timedelta(days=30)
                    maturing_bills = summary_bill_source[
                        (summary_bill_source["Maturity Date Parsed"] >= baseline_bill_date) & 
                        (summary_bill_source["Maturity Date Parsed"] <= thirty_days_later_bills)
                    ]

                    st.markdown(f"### ⏳ Maturities in Next 30 Days (from highest date: {baseline_bill_date.strftime('%Y-%m-%d')})")
                    if not maturing_bills.empty:
                        total_mat_bills_crore = maturing_bills["Outstanding (Crore)"].sum()
                        st.metric(label="Total T-Bills Maturing", value=f"{total_mat_bills_crore:,.2f} Crore BDT", delta=f"{len(maturing_bills)} Bills")
                        
                        display_mat_bills = maturing_bills.drop(columns=["Market Yield Num", "Outstanding Num", "Maturity Date Parsed", "Data_Date_Parsed"], errors="ignore")
                        st.dataframe(display_mat_bills, use_container_width=True)
                    else:
                        st.info("No Treasury Bills maturing in the 30 days following the highest date in this range.")

                    st.markdown("### 📋 Detailed Records (Full Range History)")
                    display_bills = bills_df.drop(columns=["Market Yield Num", "Outstanding Num", "Maturity Date Parsed", "Data_Date_Parsed"], errors="ignore")
                    st.dataframe(display_bills, use_container_width=True)

                    # Excel Export
                    output_bills = io.BytesIO()
                    with pd.ExcelWriter(output_bills, engine='openpyxl') as writer:
                        display_bills.to_excel(writer, index=False, sheet_name='TBills_Valuation')
                    excel_data_bills = output_bills.getvalue()

                    st.download_button(
                        label="📥 Download T-Bill Data (Excel)",
                        data=excel_data_bills,
                        file_name="tbills_valuation_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_bills_excel"
                    )
                else:
                    st.info("No T-Bill records found for the selected range.")
            else:
                st.info("No T-Bill records found in the database yet.")
        except Exception as e:
            st.error(f"Error querying T-Bills: {e}")
