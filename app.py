import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# Page Configuration
st.set_page_config(
    page_title="GSOM Treasury Dashboard",
    page_icon="📈",
    layout="wide"
)

# Inject Custom CSS for Table Styling (Center-align & Fit Content)
st.markdown("""
    <style>
    table {
        width: auto !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    th {
        text-align: center !important;
    }
    td {
        text-align: center !important;
    }
    </style>
""", unsafe_allow_html=True)

# Database Connection
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

st.title("🏛️ GSOM Treasury & Securities Dashboard")
st.markdown("Live data for Government Bonds, FRTBs, and T-Bills.")

# Fetch available dates from database safely using explicit text casting for UNION compatibility
@st.cache_data(ttl=30)
def get_available_dates():
    try:
        query = """
            SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_securities
            UNION
            SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_bills
            ORDER BY 1 DESC;
        """
        df = pd.read_sql(query, engine)
        return df.iloc[:, 0].dropna().tolist()
    except Exception as e:
        st.error(f"Error fetching dates: {e}")
        return []

available_dates = get_available_dates()

if not available_dates:
    st.warning("No data found in the database. Please check your tables or run scrapers.")
    st.stop()

# --- SEARCH DATE FILTER AT THE TOP ---
selected_date = st.selectbox("📅 Select Valuation Date", available_dates)

# Fetch data for the selected date using pandas
@st.cache_data(ttl=30)
def load_data_for_date(date_str):
    df_bills = pd.read_sql(f"SELECT * FROM public.daily_bills WHERE \"Data_Date\" = '{date_str}'", engine)
    df_securities = pd.read_sql(f"SELECT * FROM public.daily_securities WHERE \"Data_Date\" = '{date_str}'", engine)
    return df_bills, df_securities

df_bills, df_securities = load_data_for_date(selected_date)

# --- MATURITY IN NEXT 30 DAYS LOGIC ---
def calculate_maturing_volume(df_b, df_s, base_date_str):
    combined_df = pd.concat([df_b, df_s], ignore_index=True)
    if combined_df.empty or "Maturity/ Expiry Date" not in combined_df.columns:
        return 0.0, 0
    
    base_dt = pd.to_datetime(base_date_str, errors="coerce")
    if pd.isna(base_dt):
        return 0.0, 0
        
    mat_dt = pd.to_datetime(combined_df["Maturity/ Expiry Date"], errors="coerce")
    
    # Filter items maturing between base date and next 30 days
    mask = (mat_dt >= base_dt) & (mat_dt <= (base_dt + pd.Timedelta(days=30)))
    maturing_subset = combined_df[mask].copy()
    
    if maturing_subset.empty:
        return 0.0, 0
        
    maturing_subset["Crore_Val"] = pd.to_numeric(
        maturing_subset["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0
    
    return float(maturing_subset["Crore_Val"].sum()), len(maturing_subset)

maturing_crore, maturing_count = calculate_maturing_volume(df_bills, df_securities, selected_date)

# --- SUMMARY BOX & TABLES ---
st.markdown(f"""
    <div style="
        background-color: #f8f9fa; 
        border: 1px solid #e0e0e0; 
        border-radius: 8px; 
        padding: 20px; 
        margin-top: 10px;
        margin-bottom: 25px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    ">
        <h4 style="
            color: #1f2937; 
            margin-top: 0; 
            margin-bottom: 15px; 
            font-size: 1.1rem; 
            text-transform: uppercase; 
            letter-spacing: 0.05em;
            border-bottom: 2px solid #3b82f6;
            padding-bottom: 8px;
        ">
            📊 Market Summary & Overview ({selected_date})
        </h4>
""", unsafe_allow_html=True)

# 30-Day Maturity Callout Metric Card inside Summary
st.metric(
    label="⏰ Maturing Within Next 30 Days", 
    value=f"৳ {maturing_crore:,.2f} Crore", 
    delta=f"{maturing_count} Instruments Maturing"
)
st.markdown("<hr style='margin: 15px 0; border: 0; border-top: 1px solid #e0e0e0;'>", unsafe_allow_html=True)

def compute_summary(df, type_col):
    if df.empty:
        return pd.DataFrame(columns=["Category", "Count", "Total Outstanding (BDT Crore)", "Avg Market Yield (%)"])
    
    temp_df = df.copy()
    temp_df["Outstanding_Crore"] = pd.to_numeric(
        temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0

    temp_df["Yield_Val"] = pd.to_numeric(
        temp_df["Market Yield"].astype(str).str.replace("%", "").str.strip(), errors="coerce"
    ).fillna(0)

    summary = temp_df.groupby(type_col).agg(
        Count=("ISIN", "count"),
        Outstanding_Crore=("Outstanding_Crore", "sum"),
        Avg_Yield=("Yield_Val", "mean")
    ).reset_index()

    summary.columns = ["Category", "Count", "Total Outstanding (BDT Crore)", "Avg Market Yield (%)"]
    summary["Total Outstanding (BDT Crore)"] = summary["Total Outstanding (BDT Crore)"].round(2)
    summary["Avg Market Yield (%)"] = summary["Avg Market Yield (%)"].round(2)
    return summary

col_sum1, col_sum2 = st.columns(2)

with col_sum1:
    st.markdown("##### 📉 Treasury Bills Summary")
    if not df_bills.empty:
        bills_summary = compute_summary(df_bills, "Securities Type")
        st.dataframe(bills_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No T-Bill data available.")

with col_sum2:
    st.markdown("##### 📈 Bonds & FRTBs Summary")
    if not df_securities.empty:
        securities_summary = compute_summary(df_securities, "Securities Type")
        st.dataframe(securities_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No Bond/FRTB data available.")

st.markdown("</div>", unsafe_allow_html=True)

# Tabs for detailed tables
tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

with tab1:
    st.subheader(f"Treasury Bills Details ({selected_date})")
    if not df_bills.empty:
        st.dataframe(df_bills, use_container_width=True)
    else:
        st.info("No T-Bill records available for this date.")

with tab2:
    st.subheader(f"Bonds & FRTBs Details ({selected_date})")
    if not df_securities.empty:
        st.dataframe(df_securities, use_container_width=True)
    else:
        st.info("No Bond or FRTB records available for this date.")
