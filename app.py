import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# Page Configuration
st.set_page_config(
    page_title="Bangladesh Bank GSOM Automated Dashboard",
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

tab_bonds, tab_bills = st.tabs(["🏛️ Treasury Bonds & Sukuk", "💵 Treasury Bills (T-Bills)"])

# ==========================================
# 1. TREASURY BONDS TAB
# ==========================================
with tab_bonds:
    st.subheader("Treasury Bonds & Securities Valuation")
    if engine:
        try:
            with engine.connect() as conn:
                bond_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_securities ORDER BY "Data_Date" DESC', conn)
            
            if not bond_dates_df.empty:
                available_bond_dates = bond_dates_df["Data_Date"].tolist()
                selected_bond_date = st.selectbox("Select Bond Valuation Date", available_bond_dates, key="bond_date_select")

                query_bonds = f"""
                    SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                           "Issue Date", "Maturity/ Expiry Date", "Remaining Maturity", 
                           "Market Yield", "Market Price", "Outstanding BDT (in Mill)"
                    FROM public.daily_securities 
                    WHERE "Data_Date" = '{selected_bond_date}'
                    ORDER BY "Sl. No." ASC
                """
                with engine.connect() as conn:
                    bonds_df = pd.read_sql(query_bonds, conn)

                # Metrics
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Bond Instruments", len(bonds_df))
                
                bonds_df["Market Yield Num"] = pd.to_numeric(bonds_df["Market Yield"], errors="coerce")
                avg_bond_yield = bonds_df["Market Yield Num"].mean()
                c2.metric("Average Yield", f"{avg_bond_yield:.2f}%" if pd.notnull(avg_bond_yield) else "N/A")
                
                total_bond_out = pd.to_numeric(bonds_df["Outstanding BDT (in Mill)"], errors="coerce").sum()
                c3.metric("Total Outstanding", f"{total_bond_out:,.2f} BDT (M)")

                st.dataframe(bonds_df.drop(columns=["Market Yield Num"], errors="ignore"), use_container_width=True)
            else:
                st.info("No daily securities records found yet.")
        except Exception as e:
            st.error(f"Error querying securities: {e}")

# ==========================================
# 2. TREASURY BILLS TAB
# ==========================================
with tab_bills:
    st.subheader("Treasury Bills Valuation")
    if engine:
        try:
            with engine.connect() as conn:
                bill_dates_df = pd.read_sql('SELECT DISTINCT "Data_Date" FROM public.daily_bills ORDER BY "Data_Date" DESC', conn)
            
            if not bill_dates_df.empty:
                available_bill_dates = bill_dates_df["Data_Date"].tolist()
                selected_bill_date = st.selectbox("Select T-Bill Valuation Date", available_bill_dates, key="bill_date_select")

                query_bills = f"""
                    SELECT "Sl. No.", "ISIN", "Securities Name", "Securities Type", 
                           "Issue Date", "Maturity/ Expiry Date", "Issue Price",
                           "Remaining Maturity", "Market Yield", "Market Price", 
                           "Outstanding BDT (in Mill)"
                    FROM public.daily_bills 
                    WHERE "Data_Date" = '{selected_bill_date}'
                    ORDER BY "Sl. No." ASC
                """
                with engine.connect() as conn:
                    bills_df = pd.read_sql(query_bills, conn)

                # Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Total T-Bills", len(bills_df))
                
                bills_df["Market Yield Num"] = pd.to_numeric(bills_df["Market Yield"], errors="coerce")
                avg_bill_yield = bills_df["Market Yield Num"].mean()
                col2.metric("Average Market Yield", f"{avg_bill_yield:.2f}%" if pd.notnull(avg_bill_yield) else "N/A")
                
                total_bill_out = pd.to_numeric(bills_df["Outstanding BDT (in Mill)"], errors="coerce").sum()
                col3.metric("Total Outstanding", f"{total_bill_out:,.2f} BDT (M)")

                st.dataframe(bills_df.drop(columns=["Market Yield Num"], errors="ignore"), use_container_width=True)
            else:
                st.info("No T-Bill records found. Run the scraper to populate data.")
        except Exception as e:
            st.error(f"Error querying T-Bills: {e}")
