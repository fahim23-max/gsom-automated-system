import os
import io
from datetime import timedelta

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="GSOM Treasury Dashboard", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc !important; }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; }
    .summary-table { width: 100%; border-collapse: collapse; margin-top: 8px; margin-bottom: 12px; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    .summary-table th { background-color: #f1f5f9; color: #334155; font-weight: 700; text-align: center; padding: 10px; border: 1px solid #e2e8f0; font-size: 0.95rem; }
    .summary-table td { text-align: center; padding: 12px; border: 1px solid #e2e8f0; font-size: 1.15rem; font-weight: 600; color: #0f172a; }
    .bill-header, .bond-header { color: #dc2626; font-weight: bold; font-size: 1.15rem; margin-bottom: 4px; text-align: center; }
    [data-testid="stMetric"] { background-color: #ffffff; padding: 16px 20px; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; flex-direction: column; align-items: center; text-align: center; }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stMetricDelta"] { display: flex; justify-content: center; text-align: center; width: 100%; }
    </style>
""", unsafe_allow_html=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

st.markdown("""
    <div style="text-align:center; margin-bottom: 1rem;">
        <h1 style="margin-bottom: 0;">🏛️ GSOM Treasury &amp; Securities Dashboard</h1>
        <p style="color:#64748b; font-size:1.05rem; margin-top:0.25rem;">Live data for Government Bonds, FRTBs, and T-Bills</p>
    </div>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def get_bill_date_bounds():
    df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_bills', engine)
    return df.iloc[0, 0], df.iloc[0, 1]

@st.cache_data(ttl=30)
def get_security_date_bounds():
    df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_securities', engine)
    return df.iloc[0, 0], df.iloc[0, 1]

bill_min, bill_max = get_bill_date_bounds()
sec_min, sec_max = get_security_date_bounds()

if not bill_min and not sec_min:
    st.warning("No data found in the database. Please check your tables or run scrapers.")
    st.stop()

def to_date(s): return pd.to_datetime(s).date() if s else None
def default_range(min_s, max_s, lookback_days=30):
    mn, mx = to_date(min_s), to_date(max_s)
    return (max(mn, mx - timedelta(days=lookback_days)), mx) if mn and mx else (None, None)

st.markdown("#### 🔎 Select Date Range")
range_col1, range_col2 = st.columns(2)

with range_col1:
    b_start, b_end = default_range(bill_min, bill_max)
    bill_range = st.date_input("📅 T-Bill Date Range", value=(b_start, b_end), min_value=to_date(bill_min), max_value=to_date(bill_max))

with range_col2:
    s_start, s_end = default_range(sec_min, sec_max)
    bond_range = st.date_input("📅 Bond / FRTB Date Range", value=(s_start, s_end), min_value=to_date(sec_min), max_value=to_date(sec_max))

def unpack_range(rng): return rng[0], rng[1] if isinstance(rng, tuple) and len(rng) == 2 else (None, None)
bill_start, bill_end = unpack_range(bill_range)
bond_start, bond_end = unpack_range(bond_range)

@st.cache_data(ttl=30)
def load_bills_range(s, e):
    return pd.read_sql(text('SELECT * FROM public.daily_bills WHERE "Data_Date" BETWEEN :s AND :e ORDER BY "Data_Date" DESC'), engine, params={"s": str(s), "e": str(e)}) if s and e else pd.DataFrame()

@st.cache_data(ttl=30)
def load_securities_range(s, e):
    return pd.read_sql(text('SELECT * FROM public.daily_securities WHERE "Data_Date" BETWEEN :s AND :e ORDER BY "Data_Date" DESC'), engine, params={"s": str(s), "e": str(e)}) if s and e else pd.DataFrame()

df_bills = load_bills_range(bill_start, bill_end)
df_securities = load_securities_range(bond_start, bond_end)

def to_excel_bytes(df, sheet):
    buffer = io.BytesIO()
    export_df = df.copy()
    for col in export_df.select_dtypes(include=['datetime64[ns, UTC]', 'datetimetz']).columns:
        export_df[col] = export_df[col].dt.tz_localize(None)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet[:31])
    return buffer.getvalue()

def compute_maturity_detail(df, days=30):
    if df.empty or "Maturity/ Expiry Date" not in df.columns: return pd.DataFrame(), 0.0, 0
    latest = df["Data_Date"].max()
    snapshot = df[df["Data_Date"] == latest].drop_duplicates(subset="ISIN").copy()
    base_dt = pd.to_datetime(latest, errors="coerce")
    mat_dt = pd.to_datetime(snapshot["Maturity/ Expiry Date"], errors="coerce")
    mask = (mat_dt >= base_dt) & (mat_dt <= base_dt + pd.Timedelta(days=days))
    maturing = snapshot[mask].copy()
    if maturing.empty: return maturing, 0.0, 0
    crore = pd.to_numeric(maturing["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce").fillna(0) / 10.0
    maturing = maturing.sort_values(by="Maturity/ Expiry Date", ascending=True)
    maturing = maturing.drop(columns=[c for c in ["id", "ID", "Id", "Data_Date"] if c in maturing.columns], errors="ignore")
    maturing.insert(0, "Sl. No.", range(1, len(maturing) + 1))
    return maturing, float(crore.sum()), int(maturing["ISIN"].nunique())

bills_maturing, bills_maturing_crore, bills_maturing_count = compute_maturity_detail(df_bills)
bonds_maturing, bonds_maturing_crore, bonds_maturing_count = compute_maturity_detail(df_securities)
bills_anchor = df_bills["Data_Date"].max() if not df_bills.empty else "N/A"
bonds_anchor = df_securities["Data_Date"].max() if not df_securities.empty else "N/A"

def render_summary_table(df, title, is_bond=False):
    if df.empty: return
    latest = df["Data_Date"].max()
    temp = df[df["Data_Date"] == latest].drop_duplicates(subset="ISIN").copy()
    count = int(temp["ISIN"].nunique())
    temp["Crore"] = pd.to_numeric(temp["Outstanding BDT (in Mill)"].astype(str).str.replace(",", ""), errors="coerce").fillna(0) / 10.0
    tot_crore = temp["Crore"].sum()
    temp["Yield"] = pd.to_numeric(temp["Market Yield"].astype(str).str.replace("%", "").str.strip(), errors="coerce").fillna(0)
    w_yield = (temp["Yield"] * temp["Crore"]).sum() / tot_crore if tot_crore > 0 else 0.0
    
    headers = "<th>Count</th><th>Amount (BDT Cr)</th><th>Avg Yields</th>"
    row_data = f"<td>{count}</td><td>৳{tot_crore:,.2f} Cr</td><td>{w_yield:.2f}%</td>"
    if is_bond:
        c_col = next((c for c in temp.columns if "coupon" in c.lower()), None)
        if c_col and tot_crore > 0:
            temp["Coupon"] = pd.to_numeric(temp[c_col].astype(str).str.replace("%", "").str.strip(), errors="coerce").fillna(0)
            w_coup = (temp["Coupon"] * temp["Crore"]).sum() / tot_crore
            row_data += f"<td>{w_coup:.2f}%</td>"
        else:
            row_data += "<td>N/A</td>"
        headers += "<th>Avg Coupons</th>"

    st.markdown(f"""
        <div class="{'bond' if is_bond else 'bill'}-header">{title} <span style="font-size: 0.85rem; color: #64748b; font-weight: normal;">(as of {latest})</span></div>
        <table class="summary-table"><thead><tr>{headers}</tr></thead><tbody><tr>{row_data}</tr></tbody></table>
    """, unsafe_allow_html=True)

st.markdown("#### 📊 Market Summary")
sc1, sc2 = st.columns(2)
with sc1: render_summary_table(df_bills, "Treasury Bills")
with sc2: render_summary_table(df_securities, "Treasury Bonds & FRTBs", is_bond=True)

st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

st.markdown("#### ⏰ Maturity Snapshot (Next 30 Days)")
mc1, mc2 = st.columns(2)
with mc1:
    st.metric(label=f"T-Bills Maturing (from {bills_anchor})", value=f"৳ {bills_maturing_crore:,.2f} Cr", delta=f"{bills_maturing_count} ISINs", delta_color="off")
    if not bills_maturing.empty: st.dataframe(bills_maturing, use_container_width=True, hide_index=True, height=180)
with mc2:
    st.metric(label=f"Bonds/FRTBs Maturing (from {bonds_anchor})", value=f"৳ {bonds_maturing_crore:,.2f} Cr", delta=f"{bonds_maturing_count} ISINs", delta_color="off")
    if not bonds_maturing.empty: st.dataframe(bonds_maturing, use_container_width=True, hide_index=True, height=180)

st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])
with tab1:
    st.subheader(f"Treasury Bills — {bill_start} to {bill_end}")
    if not df_bills.empty:
        st.dataframe(df_bills.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_bills.columns], errors="ignore"), use_container_width=True)
        st.download_button("⬇️ Download T-Bills (Excel)", data=to_excel_bytes(df_bills, "T-Bills"), file_name=f"tbills_{bill_start}_to_{bill_end}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with tab2:
    st.subheader(f"Bonds & FRTBs — {bond_start} to {bond_end}")
    if not df_securities.empty:
        st.dataframe(df_securities.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_securities.columns], errors="ignore"), use_container_width=True)
        st.download_button("⬇️ Download Bonds/FRTBs (Excel)", data=to_excel_bytes(df_securities, "Bonds_FRTB"), file_name=f"bonds_frtb_{bond_start}_to_{bond_end}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
