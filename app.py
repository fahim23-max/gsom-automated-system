import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# Page Configuration
st.set_page_config(
    page_title="GSOM Treasury Dashboard",
    page_icon="📈",
    layout="wide"
)

# Inject Custom CSS for Table Styling (Center-align & Fit Content)
st.markdown("""
    <style>
    /* Force tables and dataframes to fit content and center align text */
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

# Fetch available dates from database for filtering
@st.cache_data(ttl=60)
def get_available_dates():
    with engine.connect() as conn:
        # Combining available dates from both securities and bills tables
        query = text("""
            SELECT DISTINCT "Data_Date" FROM public.daily_securities
            UNION
            SELECT DISTINCT "Data_Date" FROM public.daily_bills
            ORDER BY "Data_Date" DESC;
        """)
        result = conn.execute(query).fetchall()
    return [row[0] for row in result]

available_dates = get_available_dates()

if not available_dates:
    st.warning("No data found in the database. Please run your scrapers.")
    st.stop()

# --- SEARCH DATE FILTER AT THE TOP ---
selected_date = st.selectbox("📅 Select Valuation Date", available_dates)

# Fetch data for the selected date
@st.cache_data(ttl=60)
def load_data_for_date(date_str):
    with engine.connect() as conn:
        bills_query = text(f"SELECT * FROM public.daily_bills WHERE \"Data_Date\" = '{date_str}'")
        securities_query = text(f"SELECT * FROM public.daily_securities WHERE \"Data_Date\" = '{date_str}'")
        
        df_bills = pd.read_sql(bills_query, conn)
        df_securities = pd.read_sql(securities_query, conn)
    return df_bills, df_securities

df_bills, df_securities = load_data_for_date(selected_date)

# Calculate Summary Metrics
total_bills = len(df_bills)
total_securities = len(df_securities)
total_active = total_bills + total_securities

# --- SUMMARY BOX PLACED JUST BELOW THE DATE SELECTOR ---
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
        <div style="display: flex; justify-content: space-around; text-align: center;">
            <div>
                <span style="font-size: 0.85rem; color: #6b7280; display: block;">Total T-Bill Issues</span>
                <span style="font-size: 1.4rem; font-weight: bold; color: #111827;">{total_bills}</span>
            </div>
            <div>
                <span style="font-size: 0.85rem; color: #6b7280; display: block;">Total Bond & FRTB Issues</span>
                <span style="font-size: 1.4rem; font-weight: bold; color: #111827;">{total_securities}</span>
            </div>
            <div>
                <span style="font-size: 0.85rem; color: #6b7280; display: block;">Total Active Instruments</span>
                <span style="font-size: 1.4rem; font-weight: bold; color: #111827;">{total_active}</span>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Tabs for detailed tables
tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

with tab1:
    st.subheader(f"Treasury Bills ({selected_date})")
    if not df_bills.empty:
        st.dataframe(df_bills, use_container_width=True)
    else:
        st.info("No T-Bill records available for this date.")

with tab2:
    st.subheader(f"Bonds & FRTBs ({selected_date})")
    if not df_securities.empty:
        st.dataframe(df_securities, use_container_width=True)
    else:
        st.info("No Bond or FRTB records available for this date.")
