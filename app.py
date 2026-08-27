import os
import io
from datetime import timedelta
import traceback

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
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
            padding: 8px;
            border: 1px solid #e2e8f0;
            font-size: 0.90rem;
        }
        .summary-table td {
            text-align: center;
            padding: 10px;
            border: 1px solid #e2e8f0;
            font-size: 1.05rem;
            font-weight: 600;
            color: #0f172a;
        }

        /* Ledger Table Styling */
        .ledger-table {
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
        .ledger-table th {
            background-color: #f1f5f9;
            color: #334155;
            font-weight: 700;
            text-align: center;
            padding: 10px;
            border: 1px solid #e2e8f0;
            font-size: 0.90rem;
        }
        .ledger-table td {
            text-align: center;
            padding: 10px;
            border: 1px solid #e2e8f0;
            font-size: 0.95rem;
            font-weight: 600;
            color: #0f172a;
        }
        .ledger-table td:first-child {
            background-color: #f8fafc;
            font-weight: 700;
            color: #475569;
        }
        
        /* Centered Table Headers */
        .bill-header { color: #dc2626; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }
        .frtb-header { color: #059669; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }
        .bond-header { color: #2563eb; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }

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
        }
        .custom-metric-card.bill-card {
            border-top-color: #dc2626 !important;
        }
        .custom-metric-card.bond-card {
            border-top-color: #2563eb !important;
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
    if not DATABASE_URL:
        st.error("DATABASE_URL secret is missing from Streamlit Secrets!")
        st.stop()

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
        df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_bills', engine)
        if df.empty or pd.isna(df.iloc[0, 0]):
            return None, None
        return df.iloc[0, 0], df.iloc[0, 1]

    @st.cache_data(ttl=30)
    def get_security_date_bounds():
        df = pd.read_sql('SELECT MIN("Data_Date")::TEXT, MAX("Data_Date")::TEXT FROM public.daily_securities', engine)
        if df.empty or pd.isna(df.iloc[0, 0]):
            return None, None
        return df.iloc[0, 0], df.iloc[0, 1]

    bill_min, bill_max = get_bill_date_bounds()
    sec_min, sec_max = get_security_date_bounds()

    def to_date(s):
        return pd.to_datetime(s).date() if s else None

    def default_range(min_s, max_s, lookback_days=30):
        mn, mx = to_date(min_s), to_date(max_s)
        if mn is None or mx is None:
            return None, None
        start = max(mn, mx - timedelta(days=lookback_days))
        return start, mx

    # --- DATE RANGE PICKERS (FORM WRAPPED) ---
    with st.form("search_form"):
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
        
        submitted = st.form_submit_button("🔍 Search", type="primary")

    def unpack_range(rng):
        if isinstance(rng, tuple) and len(rng) == 2:
            return rng[0], rng[1]
        return None, None

    bill_start, bill_end = unpack_range(bill_range)
    bond_start, bond_end = unpack_range(bond_range)

    # --- LOAD RANGE-FILTERED DATA WITH SQL SPLITTING ---
    @st.cache_data(ttl=30)
    def load_bills_range(start_d, end_d):
        if not start_d or not end_d:
            return pd.DataFrame()
        q = text('SELECT * FROM public.daily_bills WHERE "Data_Date"::DATE BETWEEN :s AND :e ORDER BY "Data_Date" DESC')
        return pd.read_sql(q, engine, params={"s": str(start_d), "e": str(end_d)})

    @st.cache_data(ttl=30)
    def load_securities_range(start_d, end_d, is_frtb=None):
        if not start_d or not end_d:
            return pd.DataFrame()
        if is_frtb is None:
            q = text('SELECT * FROM public.daily_securities WHERE "Data_Date"::DATE BETWEEN :s AND :e ORDER BY "Data_Date" DESC')
        elif is_frtb:
            q = text('SELECT * FROM public.daily_securities WHERE "Data_Date"::DATE BETWEEN :s AND :e AND (CAST(public.daily_securities AS TEXT) ILIKE "%FRTB%") ORDER BY "Data_Date" DESC')
        else:
            q = text('SELECT * FROM public.daily_securities WHERE "Data_Date"::DATE BETWEEN :s AND :e AND (CAST(public.daily_securities AS TEXT) NOT ILIKE "%FRTB%") ORDER BY "Data_Date" DESC')
        return pd.read_sql(q, engine, params={"s": str(start_d), "e": str(end_d)})

    df_bills = load_bills_range(bill_start, bill_end)
    df_securities = load_securities_range(bond_start, bond_end, is_frtb=None)
    df_frtbs = load_securities_range(bond_start, bond_end, is_frtb=True)
    df_bonds = load_securities_range(bond_start, bond_end, is_frtb=False)

    # --- EXCEL EXPORT HELPER ---
    def to_excel_bytes(df, sheet_name):
        buffer = io.BytesIO()
        export_df = df.copy()
        for col in export_df.columns:
            if isinstance(export_df[col].dtype, pd.DatetimeTZDtype):
                export_df[col] = export_df[col].dt.tz_localize(None)
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        return buffer.getvalue()

    # --- STRICT TARGET DATE ANCHORING ---
    def get_snapshot_for_target_date(df, target_date_str):
        if df.empty or "ISIN" not in df.columns or "Data_Date" not in df.columns:
            return pd.DataFrame(), "N/A"
        
        exact_match = df[df["Data_Date"].astype(str) == str(target_date_str)]
        if not exact_match.empty:
            snapshot = exact_match.drop_duplicates(subset=["ISIN"], keep="first").copy()
            return snapshot, str(target_date_str)
        
        valid_dates = df[df["Data_Date"].astype(str) <= str(target_date_str)]
        if valid_dates.empty:
            latest_date = df["Data_Date"].max()
        else:
            latest_date = valid_dates["Data_Date"].max()
            
        snapshot = df[df["Data_Date"] == latest_date].drop_duplicates(subset=["ISIN"], keep="first").copy()
        return snapshot, str(latest_date)

    # --- LIGHTNING-FAST CACHED MONTHLY METRICS CALCULATION ---
    @st.cache_data(ttl=300)
    def calculate_monthly_metrics(table_name, is_frtb=None):
        cols = ["Newly Issued", "Reissued", "WA Yield", "Settled"]
        
        if table_name == "daily_securities" and is_frtb is not None:
            if is_frtb:
                q = text('SELECT "ISIN", "Data_Date", "Issue Date", "Maturity/ Expiry Date", "Outstanding BDT (in Mill)", "Market Yield" FROM public.daily_securities WHERE CAST(public.daily_securities AS TEXT) ILIKE "%FRTB%"')
            else:
                q = text('SELECT "ISIN", "Data_Date", "Issue Date", "Maturity/ Expiry Date", "Outstanding BDT (in Mill)", "Market Yield" FROM public.daily_securities WHERE CAST(public.daily_securities AS TEXT) NOT ILIKE "%FRTB%"')
        else:
            q = text(f'SELECT "ISIN", "Data_Date", "Issue Date", "Maturity/ Expiry Date", "Outstanding BDT (in Mill)", "Market Yield" FROM public.{table_name}')
            
        temp_df = pd.read_sql(q, engine)
        if temp_df.empty:
            return pd.DataFrame(columns=cols)

        temp_df["Amt_Cr"] = pd.to_numeric(
            temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0) / 10.0
        
        temp_df["Yield_Val"] = pd.to_numeric(
            temp_df["Market Yield"].astype(str).str.replace("%", "", regex=False).str.strip(), errors="coerce"
        ).fillna(0)
        
        temp_df["Data_Dt"] = pd.to_datetime(temp_df["Data_Date"], errors="coerce").dt.normalize()
        
        issue_col = "Issue Date" if "Issue Date" in temp_df.columns else None
        mat_col = "Maturity/ Expiry Date" if "Maturity/ Expiry Date" in temp_df.columns else None
        
        temp_df["Issue_Dt"] = pd.to_datetime(temp_df[issue_col], format="mixed", errors="coerce").dt.normalize() if issue_col else pd.NaT
        temp_df["Mat_Dt"] = pd.to_datetime(temp_df[mat_col], format="mixed", errors="coerce").dt.normalize() if mat_col else pd.NaT
        
        max_date = temp_df["Data_Dt"].max()
        temp_df = temp_df.sort_values(by=["ISIN", "Data_Dt"])
        
        # 1. Newly Issued
        first_records = temp_df[temp_df["Amt_Cr"] > 0].drop_duplicates(subset=["ISIN"], keep="first").copy()
        first_records = first_records.dropna(subset=["Issue_Dt"])
        first_records["Month"] = first_records["Issue_Dt"].dt.to_period("M")
        
        newly_issued = first_records.groupby("Month")["Amt_Cr"].sum().rename("Newly Issued")
        newly_issued_yield_vol = (first_records["Amt_Cr"] * first_records["Yield_Val"]).groupby(first_records["Month"]).sum()
        
        # 2. Reissued
        temp_df["Amt_Diff"] = temp_df.groupby("ISIN")["Amt_Cr"].diff()
        reissues = temp_df[temp_df["Amt_Diff"] > 0].copy()
        reissues = reissues.dropna(subset=["Data_Dt"])
        reissues["Month"] = reissues["Data_Dt"].dt.to_period("M")
        
        reissued = reissues.groupby("Month")["Amt_Diff"].sum().rename("Reissued")
        reissued_yield_vol = (reissues["Amt_Diff"] * reissues["Yield_Val"]).groupby(reissues["Month"]).sum()
        
        # 3. WA Yield
        total_vol = newly_issued.add(reissued, fill_value=0)
        total_yield_vol = newly_issued_yield_vol.add(reissued_yield_vol, fill_value=0)
        wa_yield = (total_yield_vol / total_vol).fillna(0).rename("WA Yield")
        
        # 4. Settled
        max_amt_per_isin = temp_df.groupby("ISIN")["Amt_Cr"].max().reset_index(name="Max_Amt")
        last_records = temp_df.drop_duplicates(subset=["ISIN"], keep="last").copy()
        last_records = last_records.merge(max_amt_per_isin, on="ISIN")
        
        past_maturities = last_records[last_records["Mat_Dt"] <= max_date].dropna(subset=["Mat_Dt"])
        past_maturities["Month"] = past_maturities["Mat_Dt"].dt.to_period("M")
        
        settled = past_maturities.groupby("Month")["Max_Amt"].sum().rename("Settled")
        
        monthly = pd.concat([newly_issued, reissued, wa_yield, settled], axis=1).fillna(0)
        
        for c in cols:
            if c not in monthly.columns:
                monthly[c] = 0.0
        return monthly[cols]

    # --- MATURITY DETAILS ---
    def compute_maturity_detail(df, target_end_date, days=30):
        snapshot, anchor_date = get_snapshot_for_target_date(df, target_end_date)
        if snapshot.empty or "Maturity/ Expiry Date" not in snapshot.columns:
            return pd.DataFrame(), 0.0, 0, anchor_date

        base_dt = pd.to_datetime(anchor_date, errors="coerce")
        mat_dt = pd.to_datetime(snapshot["Maturity/ Expiry Date"], format="mixed", errors="coerce")
        mask = (mat_dt >= base_dt) & (mat_dt <= base_dt + pd.Timedelta(days=days))
        maturing = snapshot[mask].copy()

        if maturing.empty:
            return maturing, 0.0, 0, anchor_date

        crore = pd.to_numeric(
            maturing["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0) / 10.0

        maturing["_mat_sort"] = pd.to_datetime(maturing["Maturity/ Expiry Date"], format="mixed", errors="coerce")
        maturing = maturing.sort_values(by="_mat_sort", ascending=True).drop(columns=["_mat_sort"])

        cols_to_drop = [col for col in ["id", "ID", "Id", "Data_Date"] if col in maturing.columns]
        maturing = maturing.drop(columns=cols_to_drop, errors="ignore")

        sl_col = next((c for c in maturing.columns if c.lower() in ["sl. no.", "sl. no", "sl_no", "sl no"]), None)
        if sl_col:
            maturing[sl_col] = range(1, len(maturing) + 1)
        else:
            maturing.insert(0, "Sl. No.", range(1, len(maturing) + 1))

        return maturing, float(crore.sum()), int(maturing["ISIN"].nunique()), anchor_date

    bills_maturing, bills_maturing_crore, bills_maturing_count, bills_anchor = compute_maturity_detail(df_bills, bill_end)
    bonds_maturing, bonds_maturing_crore, bonds_maturing_count, bonds_anchor = compute_maturity_detail(df_securities, bond_end)

    # --- UNIFIED SUMMARY BLOCK RENDERER ---
    def render_summary_block(df, target_end_date, title, header_class, include_coupon=False):
        if df.empty or "Data_Date" not in df.columns:
            st.markdown(f'<div class="{header_class}">{title}</div>', unsafe_allow_html=True)
            st.info(f"No {title} data in this range.")
            return
            
        temp_df, actual_date = get_snapshot_for_target_date(df, target_end_date)
        count = int(temp_df["ISIN"].nunique()) if not temp_df.empty else 0
        
        if count > 0:
            temp_df["Outstanding_Crore"] = pd.to_numeric(
                temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
            ).fillna(0) / 10.0
            total_crore = temp_df["Outstanding_Crore"].sum()
            
            temp_df["Yield_Val"] = pd.to_numeric(
                temp_df["Market Yield"].astype(str).str.replace("%", "", regex=False).str.strip(), errors="coerce"
            ).fillna(0)

            valid_yields = temp_df[temp_df["Yield_Val"] > 0]
            if not valid_yields.empty and valid_yields["Outstanding_Crore"].sum() > 0:
                weighted_yield = (valid_yields["Yield_Val"] * valid_yields["Outstanding_Crore"]).sum() / valid_yields["Outstanding_Crore"].sum()
            else:
                weighted_yield = 0.0

            if include_coupon:
                coupon_col = next((c for c in temp_df.columns if "coupon" in c.lower()), None)
                if coupon_col:
                    temp_df["Coupon_Val"] = pd.to_numeric(
                        temp_df[coupon_col].astype(str).str.replace("%", "", regex=False).str.strip(), errors="coerce"
                    ).fillna(0)
                    
                    valid_coupons = temp_df[temp_df["Coupon_Val"] > 0]
                    if not valid_coupons.empty and valid_coupons["Outstanding_Crore"].sum() > 0:
                        weighted_coupon = (valid_coupons["Coupon_Val"] * valid_coupons["Outstanding_Crore"]).sum() / valid_coupons["Outstanding_Crore"].sum()
                        coupon_str = f"{weighted_coupon:.4f}%"
                    else:
                        coupon_str = "0.0000%"
                else:
                    coupon_str = "N/A"
            else:
                coupon_str = None
        else:
            total_crore = 0.0
            weighted_yield = 0.0
            coupon_str = "N/A" if include_coupon else None

        header_html = f'<div class="{header_class}">{title} <span style="font-size: 0.85rem; color: #64748b; font-weight: normal;">(as of {actual_date})</span></div>'
        
        if include_coupon:
            table_html = f"""
            <table class="summary-table">
                <thead>
                    <tr>
                        <th>Count</th>
                        <th>Amount (BDT Cr)</th>
                        <th>WA Yield</th>
                        <th>WA Coupon</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>{count}</td>
                        <td>৳{total_crore:,.2f} Cr</td>
                        <td>{weighted_yield:.4f}%</td>
                        <td>{coupon_str}</td>
                    </tr>
                </tbody>
            </table>
            """
        else:
            table_html = f"""
            <table class="summary-table">
                <thead>
                    <tr>
                        <th>Count</th>
                        <th>Amount (BDT Cr)</th>
                        <th>WA Yield</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>{count}</td>
                        <td>৳{total_crore:,.2f} Cr</td>
                        <td>{weighted_yield:.4f}%</td>
                    </tr>
                </tbody>
            </table>
            """
            
        st.markdown(header_html + table_html, unsafe_allow_html=True)

    # --- HTML LEDGER GENERATOR ---
    def render_monthly_ledger_html(df):
        if df.empty:
            st.info("Not enough data to compute monthly metrics for the selected range.")
            return

        html = '<div style="overflow-x: auto;"><table class="ledger-table">'
        html += '<thead>'
        html += '<tr>'
        html += '<th rowspan="2" style="vertical-align: middle; width: 10%;">Month Year</th>'
        
        level0_cols = df.columns.get_level_values(0).unique()
        for col in level0_cols:
            colspan = sum(1 for c in df.columns if c[0] == col)
            if colspan > 0:
                html += f'<th colspan="{colspan}" style="border-left: 2px solid #cbd5e1; color: #1e293b;">{col}</th>'
        html += '</tr>'
        
        html += '<tr>'
        for idx, col in enumerate(df.columns):
            border_style = "border-left: 2px solid #cbd5e1;" if idx % 4 == 0 else ""
            html += f'<th style="{border_style}">{col[1]}</th>'
        html += '</tr>'
        html += '</thead>'
        
        html += '<tbody>'
        for idx, row in df.iterrows():
            html += '<tr>'
            html += f'<td>{idx}</td>'
            for col_idx, val in enumerate(row):
                col_name = df.columns[col_idx][1]
                border_style = "border-left: 2px solid #cbd5e1;" if col_idx % 4 == 0 else ""
                
                if val == 0:
                    html += f'<td style="color: #94a3b8; {border_style}">-</td>'
                elif col_name == "WA Yield":
                    html += f'<td style="{border_style}">{val:.4f}%</td>'
                else:
                    html += f'<td style="{border_style}">{val:,.2f}</td>'
            html += '</tr>'
        html += '</tbody></table></div>'
        
        st.markdown(html, unsafe_allow_html=True)


    # --- 1. MARKET SUMMARY SECTION (3-COLUMN SPLIT) ---
    st.markdown("#### 📊 Market Summary")
    sum_col1, sum_col2, sum_col3 = st.columns(3)

    with sum_col1:
        render_summary_block(df_bills, bill_end, "Treasury Bills", "bill-header", include_coupon=False)

    with sum_col2:
        render_summary_block(df_frtbs, bond_end, "FRTBs", "frtb-header", include_coupon=True)

    with sum_col3:
        render_summary_block(df_bonds, bond_end, "Treasury Bonds", "bond-header", include_coupon=True)


    # --- 2. MONTHLY METRICS LEDGER (3-PART SPLIT: BILLS, FRTBS, BONDS) ---
    st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
    st.markdown("#### 📅 Monthly Issuance & Settlement Ledger (BDT Cr)")
    
    bills_monthly = calculate_monthly_metrics("daily_bills")
    frtbs_monthly = calculate_monthly_metrics("daily_securities", is_frtb=True)
    bonds_monthly = calculate_monthly_metrics("daily_securities", is_frtb=False)

    dfs_to_join = []
    if not bills_monthly.empty:
        bills_monthly.columns = pd.MultiIndex.from_product([["Treasury Bills"], bills_monthly.columns])
        dfs_to_join.append(bills_monthly)
    if not frtbs_monthly.empty:
        frtbs_monthly.columns = pd.MultiIndex.from_product([["FRTBs"], frtbs_monthly.columns])
        dfs_to_join.append(frtbs_monthly)
    if not bonds_monthly.empty:
        bonds_monthly.columns = pd.MultiIndex.from_product([["Treasury Bonds"], bonds_monthly.columns])
        dfs_to_join.append(bonds_monthly)

    if dfs_to_join:
        combined_monthly = dfs_to_join[0]
        for d in dfs_to_join[1:]:
            combined_monthly = combined_monthly.join(d, how="outer")
            
        combined_monthly = combined_monthly.fillna(0)
        combined_monthly.sort_index(ascending=False, inplace=True)
        
        combined_monthly.index = combined_monthly.index.strftime("%b-%y")
        
        render_monthly_ledger_html(combined_monthly)
    else:
        st.info("Not enough data to compute monthly metrics for the selected range.")


    # --- 3. MATURITY SNAPSHOT SECTION ---
    st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
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
            st.dataframe(bills_maturing, hide_index=True, width="stretch")
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
            st.dataframe(bonds_maturing, hide_index=True, width="stretch")
        else:
            st.caption("No Bond/FRTB ISINs maturing in the next 30 days.")

    st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

    # --- 4. DETAIL TABS WITH EXCEL EXPORT ---
    tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])

    with tab1:
        range_label = f"{bill_start} to {bill_end}" if bill_start and bill_end else "N/A"
        st.subheader(f"Treasury Bills — {range_label}")
        if not df_bills.empty:
            display_bills = df_bills.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_bills.columns], errors="ignore")
            st.dataframe(display_bills, width="stretch")
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
            st.dataframe(display_sec, width="stretch")
            st.download_button(
                "⬇️ Download Bonds/FRTBs (Excel)",
                data=to_excel_bytes(df_securities, "Bonds_FRTB"),
                file_name=f"bonds_frtb_{bond_start}_to_{bond_end}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("No Bond or FRTB records available for this range.")

except Exception as e:
    st.error("🚨 An unhandled exception occurred in the app:")
    st.code(traceback.format_exc())
