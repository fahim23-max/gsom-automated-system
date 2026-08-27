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

# --- CENTERED TITLE ---
st.markdown("""
    <div style="text-align:center; margin-bottom: 0.25rem;">
        <h1 style="margin-bottom: 0;">🏛️ GSOM Treasury &amp; Securities Dashboard</h1>
        <p style="color:#6b7280; font-size:1.05rem; margin-top:0.25rem;">
            Live data for Government Bonds, FRTBs, and T-Bills
        </p>
    </div>
""", unsafe_allow_html=True)

# --- FETCH AVAILABLE DATES SEPARATELY FOR EACH TABLE ---
@st.cache_data(ttl=30)
def get_bill_dates():
    try:
        query = 'SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_bills ORDER BY 1 DESC;'
        df = pd.read_sql(query, engine)
        return df.iloc[:, 0].dropna().tolist()
    except Exception as e:
        st.error(f"Error fetching T-Bill dates: {e}")
        return []

@st.cache_data(ttl=30)
def get_security_dates():
    try:
        query = 'SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_securities ORDER BY 1 DESC;'
        df = pd.read_sql(query, engine)
        return df.iloc[:, 0].dropna().tolist()
    except Exception as e:
        st.error(f"Error fetching Bond/FRTB dates: {e}")
        return []

bill_dates = get_bill_dates()
security_dates = get_security_dates()

if not bill_dates and not security_dates:
    st.warning("No data found in the database. Please check your tables or run scrapers.")
    st.stop()

# --- INDEPENDENT DATE-WISE SEARCH FOR BILLS AND BONDS ---
st.markdown("#### 🔎 Select Valuation Dates")
date_col1, date_col2 = st.columns(2)

with date_col1:
    selected_bill_date = st.selectbox(
        "📅 T-Bill Valuation Date", bill_dates
    ) if bill_dates else None
    if not bill_dates:
        st.info("No T-Bill dates available.")

with date_col2:
    selected_bond_date = st.selectbox(
        "📅 Bond / FRTB Valuation Date", security_dates
    ) if security_dates else None
    if not security_dates:
        st.info("No Bond/FRTB dates available.")

# --- LOAD DATA INDEPENDENTLY PER SELECTION ---
@st.cache_data(ttl=30)
def load_bills(date_str):
    if not date_str:
        return pd.DataFrame()
    return pd.read_sql(
        f"SELECT * FROM public.daily_bills WHERE \"Data_Date\" = '{date_str}'", engine
    )

@st.cache_data(ttl=30)
def load_securities(date_str):
    if not date_str:
        return pd.DataFrame()
    return pd.read_sql(
        f"SELECT * FROM public.daily_securities WHERE \"Data_Date\" = '{date_str}'", engine
    )

df_bills = load_bills(selected_bill_date)
df_securities = load_securities(selected_bond_date)

# --- MATURITY IN NEXT 30 DAYS, ANCHORED TO THE LATER OF THE TWO SELECTED DATES ---
def get_max_selected_date(d1, d2):
    candidates = [pd.to_datetime(d, errors="coerce") for d in (d1, d2) if d]
    candidates = [d for d in candidates if pd.notna(d)]
    return max(candidates) if candidates else None

base_dt = get_max_selected_date(selected_bill_date, selected_bond_date)

def calculate_maturing_volume(df_b, df_s, base_dt):
    combined_df = pd.concat([df_b, df_s], ignore_index=True)
    if combined_df.empty or "Maturity/ Expiry Date" not in combined_df.columns or base_dt is None:
        return 0.0, 0

    mat_dt = pd.to_datetime(combined_df["Maturity/ Expiry Date"], errors="coerce")

    mask = (mat_dt >= base_dt) & (mat_dt <= (base_dt + pd.Timedelta(days=30)))
    maturing_subset = combined_df[mask].copy()

    if maturing_subset.empty:
        return 0.0, 0

    maturing_subset["Crore_Val"] = pd.to_numeric(
        maturing_subset["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0

    return float(maturing_subset["Crore_Val"].sum()), len(maturing_subset)

maturing_crore, maturing_count = calculate_maturing_volume(df_bills, df_securities, base_dt)

base_dt_label = base_dt.strftime("%d %b %Y") if base_dt is not None else "N/A"

# --- SUMMARY BOX ---
st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%);
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 24px;
        margin-top: 10px;
        margin-bottom: 25px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    ">
        <h4 style="
            color: #1f2937;
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 1.15rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 3px solid #3b82f6;
            padding-bottom: 8px;
        ">
            📊 Market Summary &amp; Overview
        </h4>
""", unsafe_allow_html=True)

# 30-Day Maturity Callout — vivid gradient KPI card
st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #f97316 0%, #ef4444 100%);
        border-radius: 12px;
        padding: 20px 24px;
        color: white;
        box-shadow: 0 4px 12px rgba(239,68,68,0.25);
        margin-bottom: 8px;
    ">
        <div style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.08em; opacity:0.9;">
            ⏰ Maturing Within Next 30 Days (from {base_dt_label})
        </div>
        <div style="font-size:2.1rem; font-weight:700; margin-top:4px;">
            ৳ {maturing_crore:,.2f} Crore
        </div>
        <div style="font-size:0.95rem; opacity:0.9; margin-top:2px;">
            {maturing_count} Instruments Maturing
        </div>
    </div>
""", unsafe_allow_html=True)

st.markdown("<hr style='margin: 20px 0; border: 0; border-top: 1px solid #e0e0e0;'>", unsafe_allow_html=True)

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

# Vivid, distinct colors cycled per category card
CARD_COLORS = [
    ("#6366f1", "#4f46e5"),  # indigo
    ("#06b6d4", "#0891b2"),  # cyan
    ("#10b981", "#059669"),  # emerald
    ("#f59e0b", "#d97706"),  # amber
    ("#ec4899", "#db2777"),  # pink
    ("#8b5cf6", "#7c3aed"),  # violet
]

def render_colorful_summary(summary_df, empty_message):
    if summary_df.empty:
        st.info(empty_message)
        return

    cols = st.columns(len(summary_df)) if len(summary_df) <= 4 else st.columns(4)
    for i, (_, row) in enumerate(summary_df.iterrows()):
        color_start, color_end = CARD_COLORS[i % len(CARD_COLORS)]
        target_col = cols[i % len(cols)]
        with target_col:
            st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, {color_start} 0%, {color_end} 100%);
                    border-radius: 10px;
                    padding: 16px;
                    color: white;
                    margin-bottom: 12px;
                    box-shadow: 0 3px 8px rgba(0,0,0,0.12);
                    min-height: 130px;
                ">
                    <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em; opacity:0.9;">
                        {row['Category']}
                    </div>
                    <div style="font-size:1.6rem; font-weight:700; margin-top:6px;">
                        {row['Count']}
                    </div>
                    <div style="font-size:0.85rem; opacity:0.9;">instruments</div>
                    <hr style="border-color: rgba(255,255,255,0.3); margin: 8px 0;">
                    <div style="font-size:0.85rem;">
                        ৳ {row['Total Outstanding (BDT Crore)']:,.2f} Cr outstanding
                    </div>
                    <div style="font-size:0.85rem;">
                        Avg Yield: {row['Avg Market Yield (%)']:.2f}%
                    </div>
                </div>
            """, unsafe_allow_html=True)

st.markdown("##### 📉 Treasury Bills Summary")
bills_summary = compute_summary(df_bills, "Securities Type")
render_colorful_summary(bills_summary, "No T-Bill data available for the selected date.")

st.markdown("##### 📈 Bonds & FRTBs Summary")
securities_summary = compute_summary(df_securities, "Securities Type")
render_colorful_summary(securities_summary, "No Bond/FRTB data available for the selected date.")

st.markdown("</div>", unsafe_allow_html=True)

# Tabs for detailed tables
tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

with tab1:
    st.subheader(f"Treasury Bills Details ({selected_bill_date or 'N/A'})")
    if not df_bills.empty:
        st.dataframe(df_bills, use_container_width=True)
    else:
        st.info("No T-Bill records available for this date.")

with tab2:
    st.subheader(f"Bonds & FRTBs Details ({selected_bond_date or 'N/A'})")
    if not df_securities.empty:
        st.dataframe(df_securities, use_container_width=True)
    else:
        st.info("No Bond or FRTB records available for this date.")
