import os
import io
from datetime import timedelta

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from sqlalchemy import create_engine, text

# Page Configuration
st.set_page_config(
    page_title="GSOM Dashboard",
    page_icon="📈",
    layout="wide"
)

st.markdown("""
    <style>
    table {
        width: auto !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    th { text-align: center !important; }
    td { text-align: center !important; }
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

# --- AVAILABLE DATE BOUNDS (used to set sensible date_input min/max/default) ---
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
    """Default to the last `lookback_days` within the available bounds."""
    mn, mx = to_date(min_s), to_date(max_s)
    if mn is None or mx is None:
        return None, None
    start = max(mn, mx - timedelta(days=lookback_days))
    return start, mx


# --- DATE RANGE PICKERS (independent for Bills and Bonds/FRTBs) ---
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
    """st.date_input returns a single date while the user is mid-pick; only
    treat it as a valid range once both endpoints are chosen."""
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


# --- EXCEL EXPORT HELPER (Fixed for Timezone stripping) ---
def to_excel_bytes(df, sheet_name):
    buffer = io.BytesIO()
    export_df = df.copy()
    
    # Strip timezones from any datetime columns to prevent Excel export errors
    for col in export_df.select_dtypes(include=['datetime64[ns, UTC]', 'datetimetz']).columns:
        export_df[col] = export_df[col].dt.tz_localize(None)
        
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buffer.getvalue()


# --- MATURITY: SEPARATE PER CATEGORY, ANCHORED TO THE LATEST DATE IN EACH RANGE ---
def compute_maturity_detail(df, days=30):
    """Uses the most recent date present in the loaded range as the snapshot,
    dedupes by ISIN, and returns (detail_df, total_crore, count)."""
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

    return maturing, float(crore.sum()), int(maturing["ISIN"].nunique())


bills_maturing, bills_maturing_crore, bills_maturing_count = compute_maturity_detail(df_bills)
bonds_maturing, bonds_maturing_crore, bonds_maturing_count = compute_maturity_detail(df_securities)

bills_anchor = df_bills["Data_Date"].max() if not df_bills.empty else "N/A"
bonds_anchor = df_securities["Data_Date"].max() if not df_securities.empty else "N/A"


def render_maturity_card(title, anchor_label, crore, count, color_start, color_end):
    card_html = f"""
    <div style="
        background: linear-gradient(135deg, {color_start} 0%, {color_end} 100%);
        border-radius: 10px;
        padding: 14px 18px;
        color: white;
        font-family: sans-serif;
        box-shadow: 0 3px 10px rgba(0,0,0,0.12);
    ">
        <div style="font-size:0.9rem; text-transform:uppercase; letter-spacing:0.05em; opacity:0.92;">
            ⏰ {title} — Maturing in 30 Days (from {anchor_label})
        </div>
        <div style="font-size:2.0rem; font-weight:800; margin-top:4px;">
            ৳ {crore:,.2f} Cr &nbsp;
            <span style="font-size:1.1rem; font-weight:400; opacity:0.92;">({count} ISINs)</span>
        </div>
    </div>
    """
    components.html(card_html, height=95, scrolling=False)


# --- MARKET SUMMARY (shown first) ---
def compute_summary(df):
    if df.empty or "Data_Date" not in df.columns:
        return pd.DataFrame(columns=["Category", "Count", "Total Outstanding (BDT Crore)", "Avg Market Yield (%)"])

    latest_date = df["Data_Date"].max()
    temp_df = df[df["Data_Date"] == latest_date].copy()

    temp_df["Outstanding_Crore"] = pd.to_numeric(
        temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0) / 10.0
    temp_df["Yield_Val"] = pd.to_numeric(
        temp_df["Market Yield"].astype(str).str.replace("%", "").str.strip(), errors="coerce"
    ).fillna(0)

    summary = temp_df.groupby("Securities Type").agg(
        Count=("ISIN", "count"),
        Outstanding_Crore=("Outstanding_Crore", "sum"),
        Avg_Yield=("Yield_Val", "mean")
    ).reset_index()
    summary.columns = ["Category", "Count", "Total Outstanding (BDT Crore)", "Avg Market Yield (%)"]
    summary["Total Outstanding (BDT Crore)"] = summary["Total Outstanding (BDT Crore)"].round(2)
    summary["Avg Market Yield (%)"] = summary["Avg Market Yield (%)"].round(2)
    return summary


BILLS_SHADES = ["#2563eb", "#1d4ed8", "#1e3a8a"]   # blues
BONDS_SHADES = ["#0d9488", "#0f766e", "#134e4a"]   # teals


def render_summary_cards(summary_df, empty_message, latest_label, shades):
    if summary_df.empty:
        st.info(empty_message)
        return
    st.caption(f"As of {latest_label}")

    cards_html = "<div style='display:flex; flex-wrap:wrap; gap:14px; font-family:sans-serif;'>"
    for i, (_, row) in enumerate(summary_df.iterrows()):
        color = shades[i % len(shades)]
        cards_html += f"""
            <div style="
                flex: 0 1 250px;
                background: {color};
                border-radius: 10px;
                padding: 18px 20px;
                color: white;
                box-shadow: 0 3px 10px rgba(0,0,0,0.15);
            ">
                <div style="font-size:0.9rem; text-transform:uppercase; letter-spacing:0.04em; opacity:0.92;">
                    {row['Category']}
                </div>
                <div style="font-size:2.1rem; font-weight:800; line-height:1.25; margin-top:6px;">
                    {row['Count']} <span style="font-size:1rem; font-weight:400;">instr.</span>
                </div>
                <div style="font-size:1.05rem; opacity:0.95; margin-top:6px;">
                    ৳{row['Total Outstanding (BDT Crore)']:,.1f}Cr &nbsp;·&nbsp; {row['Avg Market Yield (%)']:.2f}%
                </div>
            </div>
        """
    cards_html += "</div>"
    
    components.html(cards_html, height=130, scrolling=False)


st.markdown("#### 📊 Market Summary")
sum_col1, sum_col2 = st.columns(2)
with sum_col1:
    st.markdown("##### 📉 Treasury Bills")
    render_summary_cards(compute_summary(df_bills), "No T-Bill data in this range.", bills_anchor, BILLS_SHADES)
with sum_col2:
    st.markdown("##### 📈 Bonds & FRTBs")
    render_summary_cards(compute_summary(df_securities), "No Bond/FRTB data in this range.", bonds_anchor, BONDS_SHADES)

st.markdown("<hr style='margin: 24px 0; border: 0; border-top: 1px solid #e0e0e0;'>", unsafe_allow_html=True)

# --- MATURITY SNAPSHOT (shown second, uses the same color families as its side) ---
st.markdown("#### ⏰ Maturity Snapshot (next 30 days)")
mat_col1, mat_col2 = st.columns(2)
with mat_col1:
    render_maturity_card("T-Bills", bills_anchor, bills_maturing_crore, bills_maturing_count, BILLS_SHADES[0], BILLS_SHADES[2])
    if not bills_maturing.empty:
        st.dataframe(
            bills_maturing.drop(columns=["Data_Date"], errors="ignore"),
            use_container_width=True, hide_index=True, height=200,
        )
    else:
        st.caption("No T-Bill ISINs maturing in the next 30 days.")

with mat_col2:
    render_maturity_card("Bonds/FRTBs", bonds_anchor, bonds_maturing_crore, bonds_maturing_count, BONDS_SHADES[0], BONDS_SHADES[2])
    if not bonds_maturing.empty:
        st.dataframe(
            bonds_maturing.drop(columns=["Data_Date"], errors="ignore"),
            use_container_width=True, hide_index=True, height=200,
        )
    else:
        st.caption("No Bond/FRTB ISINs maturing in the next 30 days.")

st.markdown("<hr style='margin: 24px 0; border: 0; border-top: 1px solid #e0e0e0;'>", unsafe_allow_html=True)

# --- DETAIL TABS WITH EXCEL EXPORT FOR THE SELECTED RANGE ---
tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

with tab1:
    range_label = f"{bill_start} to {bill_end}" if bill_start and bill_end else "N/A"
    st.subheader(f"Treasury Bills — {range_label}")
    if not df_bills.empty:
        st.dataframe(df_bills, use_container_width=True)
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
        st.dataframe(df_securities, use_container_width=True)
        st.download_button(
            "⬇️ Download Bonds/FRTBs (Excel)",
            data=to_excel_bytes(df_securities, "Bonds_FRTB"),
            file_name=f"bonds_frtb_{bond_start}_to_{bond_end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No Bond or FRTB records available for this range.")
