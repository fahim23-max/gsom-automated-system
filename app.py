import os
import io
from datetime import timedelta

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# Page Configuration
st.set_page_config(
    page_title="GSOM Treasury Dashboard",
    page_icon="📈",
    layout="wide"
)

# Custom CSS for Background Color, Centered Tables, and Upgraded Financial Metric Cards
st.markdown("""
    <style>
    /* Full Page Background */
    .stApp {
        background-color: #f8fafc !important;
    }
    
    /* Global App Container */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }

    /* Summary Table Styling */
    .summary-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        margin-bottom: 12px;
        font-family: sans-serif;
        background-color: #ffffff;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .summary-table th {
        background-color: #f1f5f9;
        color: #334155;
        font-weight: 700;
        text-align: center;
        padding: 10px;
        border: 1px solid #e2e8f0;
        font-size: 0.95rem;
    }
    .summary-table td {
        text-align: center;
        padding: 12px;
        border: 1px solid #e2e8f0;
        font-size: 1.15rem;
        font-weight: 600;
        color: #0f172a;
    }
    
    /* Centered Table Headers */
    .bill-header, .bond-header { 
        color: #dc2626; 
        font-weight: bold; 
        font-size: 1.15rem; 
        margin-bottom: 4px; 
        text-align: center; 
    }

    /* Upgraded Professional Financial Metric Cards */
    .custom-metric-card {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-top: 4px solid #3b82f6 !important;
        border-radius: 10px !important;
        padding: 20px !important;
        text-align: center !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03) !important;
        margin-bottom: 15px !important;
        transition: transform 0.2s ease;
    }
    .custom-metric-card.bill-card {
        border-top-color: #dc2626 !important; /* Red accent for T-Bills */
    }
    .custom-metric-card.bond-card {
        border-top-color: #2563eb !important; /* Blue accent for Bonds */
    }
    .custom-metric-label {
        font-size: 0.9rem !important;
        color: #64748b !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 8px !important;
    }
    .custom-metric-value {
        font-size: 1.8rem !important;
        color: #0f172a !important;
        font-weight: 800 !important;
        margin-bottom: 8px !important;
    }
    .custom-metric-delta {
        font-size: 0.85rem !important;
        color: #1e293b !important;
        background-color: #f1f5f9 !important;
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        border: 1px solid #e2e8f0;
    }
    </style>
""", unsafe_allow_html=True)

# Database Connection
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

# --- TITLE ---
st.markdown("""
    <div style="text-align:center; margin-bottom: 1rem;">
        <h1 style="margin-bottom: 0;">🏛️ GSOM Treasury &amp; Securities Dashboard</h1>
        <p style="color:#64748b; font-size:1.05rem; margin-top:0.25rem;">
            Live data for Government Bonds, FRTBs, and T-Bills
        </p>
    </div>
""", unsafe_allow_html=True)

# --- AVAILABLE DATE BOUNDS ---
@st.cache_data(ttl=30)
def get_bill_date_bounds():
    try:
        df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_bills', engine)
        return df.iloc[0, 0], df.iloc[0, 1]
    except Exception as e:
        st.error(f"Error fetching T-Bill date range: {e}")
        return None, None

@st.cache_data(ttl=30)
def get_security_date_bounds():
    try:
        df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_securities', engine)
        return df.iloc[0, 0], df.iloc[0, 1]
    except Exception as e:
        st.error(f"Error fetching Bond/FRTB date range: {e}")
        return None, None

bill_min, bill_max = get_bill_date_bounds()
sec_min, sec_max = get_security_date_bounds()

if not bill_min and not sec_min:
    st.warning("No data found in the database. Please check your tables or run scrapers.")
    st.stop()


def to_date(s):
    return pd.to_datetime(s).date() if s else None


def default_range(min_s, max_s, lookback_days=30):
    mn, mx = to_date(min_s), to_date(max_s)
    if mn is None or mx is None:
        return None, None
    start = max(mn, mx - timedelta(days=lookback_days))
    return start, mx


# --- DATE RANGE PICKERS ---
st.markdown("#### 🔎 Select Date Range")
range_col1, range_col2 = st.columns(2)

with range_col1:
    if bill_min:
        b_start_default, b_end_default = default_range(bill_min, bill_max)
        bill_range = st.date_input(
            "📅 T-Bill Date Range",
            value=(b_start_default, b_end_default),
            min_value=to_date(bill_min),
            max_value=to_date(bill_max),
        )
    else:
        bill_range = None
        st.info("No T-Bill dates available.")

with range_col2:
    if sec_min:
        s_start_default, s_end_default = default_range(sec_min, sec_max)
        bond_range = st.date_input(
            "📅 Bond / FRTB Date Range",
            value=(s_start_default, s_end_default),
            min_value=to_date(sec_min),
            max_value=to_date(sec_max),
        )
    else:
        bond_range = None
        st.info("No Bond/FRTB dates available.")


def unpack_range(rng):
    if isinstance(rng, tuple) and len(rng) == 2:
        return rng[0], rng[1]
    return None, None


bill_start, bill_end = unpack_range(bill_range)
bond_start, bond_end = unpack_range(bond_range)

# --- LOAD RANGE-FILTERED DATA ---
@st.cache_data(ttl=30)
def load_bills_range(start_d, end_d):
    if not start_d or not end_d:
        return pd.DataFrame()
    q = text('SELECT * FROM public.daily_bills WHERE "Data_Date" BETWEEN :s AND :e ORDER BY "Data_Date" DESC')
    return pd.read_sql(q, engine, params={"s": str(start_d), "e": str(end_d)})

@st.cache_data(ttl=30)
def load_securities_range(start_d, end_d):
    if not start_d or not end_d:
        return pd.DataFrame()
    q = text('SELECT * FROM public.daily_securities WHERE "Data_Date" BETWEEN :s AND :e ORDER BY "Data_Date" DESC')
    return pd.read_sql(q, engine, params={"s": str(start_d), "e": str(end_d)})

df_bills = load_bills_range(bill_start, bill_end)
df_securities = load_securities_range(bond_start, bond_end)


# --- EXCEL EXPORT HELPER ---
def to_excel_bytes(df, sheet_name):
    buffer = io.BytesIO()
    export_df = df.copy()
    for col in export_df.select_dtypes(include=['datetime64[ns, UTC]', 'datetimetz']).columns:
        export_df[col] = export_df[col].dt.tz_localize(None)
        
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buffer.getvalue()


# --- MATURITY DETAILS (ID REMOVED & ORDERED SERIAL NUMBER) ---
def compute_maturity_detail(df, days=30):
    if df.empty or "Maturity/ Expiry Date" not in df.columns or "Data_Date" not in df.columns:
        return pd.DataFrame(), 0.0, 0

    latest_date = df["Data_Date"].max()
    snapshot = df[df["Data_Date"] == latest_date].drop_duplicates(subset="ISIN").copy()

    base_dt = pd.to_datetime(latest_date, errors="coerce")
    mat_dt = pd.to_datetime(snapshot["Maturity/ Expiry Date"], errors="coerce")
    mask = (mat_dt >= base_dt) & (mat_dt <= base_dt + pd.Timedelta(days=days))
    maturing = snapshot[mask].copy()

    if maturing.empty:
        return maturing, 0.0, 0

    crore = pd.to_numeric(
        maturing["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0

    maturing["_mat_sort"] = pd.to_datetime(maturing["Maturity/ Expiry Date"], errors="coerce")
    maturing = maturing.sort_values(by="_mat_sort", ascending=True).drop(columns=["_mat_sort"])

    cols_to_drop = [col for col in ["id", "ID", "Id", "Data_Date"] if col in maturing.columns]
    maturing = maturing.drop(columns=cols_to_drop, errors="ignore")

    sl_col = next((c for c in maturing.columns if c.lower() in ["sl. no.", "sl. no", "sl_no", "sl no"]), None)
    if sl_col:
        maturing[sl_col] = range(1, len(maturing) + 1)
    else:
        maturing.insert(0, "Sl. No.", range(1, len(maturing) + 1))

    return maturing, float(crore.sum()), int(maturing["ISIN"].nunique())


bills_maturing, bills_maturing_crore, bills_maturing_count = compute_maturity_detail(df_bills)
bonds_maturing, bonds_maturing_crore, bonds_maturing_count = compute_maturity_detail(df_securities)

bills_anchor = df_bills["Data_Date"].max() if not df_bills.empty else "N/A"
bonds_anchor = df_securities["Data_Date"].max() if not df_securities.empty else "N/A"


# --- SUMMARY COMPUTATION & RENDERERS ---
def render_bills_summary_table(df):
    if df.empty or "Data_Date" not in df.columns:
        st.info("No T-Bill data in this range.")
        return
    
    latest_date = df["Data_Date"].max()
    temp_df = df[df["Data_Date"] == latest_date].drop_duplicates(subset="ISIN").copy()
    
    count = int(temp_df["ISIN"].nunique())
    
    temp_df["Outstanding_Crore"] = pd.to_numeric(
        temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0
    total_crore = temp_df["Outstanding_Crore"].sum()
    
    temp_df["Yield_Val"] = pd.to_numeric(
        temp_df["Market Yield"].astype(str).str.replace("%", "").str.strip(), errors="coerce"
    ).fillna(0)

    if total_crore > 0:
        weighted_yield = (temp_df["Yield_Val"] * temp_df["Outstanding_Crore"]).sum() / total_crore
    else:
        weighted_yield = 0.0

    st.markdown(f"""
        <div class="bill-header">Treasury Bills <span style="font-size: 0.85rem; color: #64748b; font-weight: normal;">(as of {latest_date})</span></div>
        <table class="summary-table">
            <thead>
                <tr>
                    <th>Count</th>
                    <th>Amount (BDT Cr)</th>
                    <th>Avg Yields</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{count}</td>
                    <td>৳{total_crore:,.2f} Cr</td>
                    <td>{weighted_yield:.2f}%</td>
                </tr>
            </tbody>
        </table>
    """, unsafe_allow_html=True)


def render_bonds_summary_table(df):
    if df.empty or "Data_Date" not in df.columns:
        st.info("No Bond/FRTB data in this range.")
        return
    
    latest_date = df["Data_Date"].max()
    temp_df = df[df["Data_Date"] == latest_date].drop_duplicates(subset="ISIN").copy()
    
    count = int(temp_df["ISIN"].nunique())
    
    temp_df["Outstanding_Crore"] = pd.to_numeric(
        temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0
    total_crore = temp_df["Outstanding_Crore"].sum()
    
    temp_df["Yield_Val"] = pd.to_numeric(
        temp_df["Market Yield"].astype(str).str.replace("%", "").str.strip(), errors="coerce"
    ).fillna(0)

    if total_crore > 0:
        weighted_yield = (temp_df["Yield_Val"] * temp_df["Outstanding_Crore"]).sum() / total_crore
    else:
        weighted_yield = 0.0

    coupon_col = next((c for c in temp_df.columns if "coupon" in c.lower()), None)
    if coupon_col and total_crore > 0:
        temp_df["Coupon_Val"] = pd.to_numeric(
            temp_df[coupon_col].astype(str).str.replace("%", "").str.strip(), errors="coerce"
        ).fillna(0)
        weighted_coupon = (temp_df["Coupon_Val"] * temp_df["Outstanding_Crore"]).sum() / total_crore
        coupon_str = f"{weighted_coupon:.2f}%"
    else:
        coupon_str = "N/A"

    st.markdown(f"""
        <div class="bond-header">Treasury Bonds &amp; FRTBs <span style="font-size: 0.85rem; color: #64748b; font-weight: normal;">(as of {latest_date})</span></div>
        <table class="summary-table">
            <thead>
                <tr>
                    <th>Count</th>
                    <th>Amount (BDT Cr)</th>
                    <th>Avg Yields</th>
                    <th>Avg Coupons</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{count}</td>
                    <td>৳{total_crore:,.2f} Cr</td>
                    <td>{weighted_yield:.2f}%</td>
                    <td>{coupon_str}</td>
                </tr>
            </tbody>
        </table>
    """, unsafe_allow_html=True)


# --- 1. MARKET SUMMARY SECTION ---
st.markdown("#### 📊 Market Summary")
sum_col1, sum_col2 = st.columns(2)

with sum_col1:
    render_bills_summary_table(df_bills)

with sum_col2:
    render_bonds_summary_table(df_securities)

st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

# --- 2. MATURITY SNAPSHOT SECTION (UPGRADED METRIC CARDS) ---
st.markdown("#### ⏰ Maturity Snapshot (Next 30 Days)")
mat_col1, mat_col2 = st.columns(2)

with mat_col1:
    st.markdown(f"""
        <div class="custom-metric-card bill-card">
            <div class="custom-metric-label">T-Bills Maturing (from {bills_anchor})</div>
            <div class="custom-metric-value">৳ {bills_maturing_crore:,.2f} Cr</div>
            <div class="custom-metric-delta">📌 {bills_maturing_count} ISINs Maturing</div>
        </div>
    """, unsafe_allow_html=True)
    
    if not bills_maturing.empty:
        st.dataframe(
            bills_maturing,
            use_container_width=True, hide_index=True, height=180,
        )
    else:
        st.caption("No T-Bill ISINs maturing in the next 30 days.")

with mat_col2:
    st.markdown(f"""
        <div class="custom-metric-card bond-card">
            <div class="custom-metric-label">Bonds/FRTBs Maturing (from {bonds_anchor})</div>
            <div class="custom-metric-value">৳ {bonds_maturing_crore:,.2f} Cr</div>
            <div class="custom-metric-delta">📌 {bonds_maturing_count} ISINs Maturing</div>
        </div>
    """, unsafe_allow_html=True)

    if not bonds_maturing.empty:
        st.dataframe(
            bonds_maturing,
            use_container_width=True, hide_index=True, height=180,
        )
    else:
        st.caption("No Bond/FRTB ISINs maturing in the next 30 days.")

st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

# --- 3. DETAIL TABS WITH EXCEL EXPORT ---
tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

with tab1:
    range_label = f"{bill_start} to {bill_end}" if bill_start and bill_end else "N/A"
    st.subheader(f"Treasury Bills — {range_label}")
    if not df_bills.empty:
        display_bills = df_bills.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_bills.columns], errors="ignore")
        st.dataframe(display_bills, use_container_width=True)
        st.download_button(
            "⬇️ Download T-Bills (Excel)",
            data=to_excel_bytes(df_bills, "T-Bills"),
            file_name=f"tbills_{bill_start}_to_{bill_end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No T-Bill records available for this range.")

with tab2:
    range_label = f"{bond_start} to {bond_end}" if bond_start and bond_end else "N/A"
    st.subheader(f"Bonds & FRTBs — {range_label}")
    if not df_securities.empty:
        display_sec = df_securities.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_securities.columns], errors="ignore")
        st.dataframe(display_sec, use_container_width=True)
        st.download_button(
            "⬇️ Download Bonds/FRTBs (Excel)",
            data=to_excel_bytes(df_securities, "Bonds_FRTB"),
            file_name=f"bonds_frtb_{bond_start}_to_{bond_end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No Bond or FRTB records available for this range.")
