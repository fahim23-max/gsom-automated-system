import os
import io
from datetime import timedelta
import traceback

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    # --- PAGE CONFIGURATION ---
    st.set_page_config(
        page_title="GSOM Treasury Dashboard",
        page_icon="📈",
        layout="wide"
    )

    # --- CUSTOM CSS STYLING ---
    st.markdown("""
        <style>
        .stApp {
            background-color: #f8fafc !important;
        }
        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
        }
        
        /* Isolated Scrollable Container for Side-by-Side Tables */
        .table-container-card {
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            padding: 8px 10px 14px 10px;
            margin-top: 8px;
            margin-bottom: 14px;
            overflow-x: auto;
            max-width: 100%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        }

        /* Universal Styled Data Table */
        .custom-data-table {
            width: 100%;
            border-collapse: collapse;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #ffffff;
        }
        .custom-data-table th {
            background-color: #e2e8f0 !important;
            color: #000000 !important;
            font-weight: 800 !important;
            text-align: center !important;
            vertical-align: middle !important;
            padding: 8px 10px !important;
            border: 1px solid #cbd5e1 !important;
            font-size: 0.80rem !important;
            letter-spacing: 0.02em;
            white-space: nowrap !important;
        }
        .custom-data-table td {
            text-align: center !important;
            vertical-align: middle !important;
            padding: 7px 10px !important;
            border: 1px solid #e2e8f0 !important;
            font-size: 0.84rem !important;
            color: #0f172a !important;
            white-space: nowrap !important;
        }
        .custom-data-table tr:nth-child(even) {
            background-color: #f8fafc;
        }
        .custom-data-table tr:hover {
            background-color: #f1f5f9;
        }

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
            background-color: #e2e8f0;
            color: #000000;
            font-weight: 800;
            text-align: center;
            padding: 8px;
            border: 1px solid #cbd5e1;
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
        .bill-header { color: #dc2626; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }
        .frtb-header { color: #059669; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }
        .bond-header { color: #2563eb; font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; text-align: center; }
        .custom-metric-card {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-top: 4px solid #3b82f6 !important;
            border-radius: 10px !important;
            padding: 20px !important;
            text-align: center !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03) !important;
            margin-bottom: 12px !important;
        }
        .custom-metric-card.bill-card { border-top-color: #dc2626 !important; }
        .custom-metric-card.bond-card { border-top-color: #2563eb !important; }
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

    # --- DATABASE ENGINE ---
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        st.error("DATABASE_URL secret is missing from Streamlit Secrets!")
        st.stop()

    engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

    # --- HTML TABLE BUILDER (SCROLLABLE CARD CONTAINER) ---
    def render_centered_html_table(df, format_dict=None):
        if df.empty:
            return "<p style='text-align:center; color:#64748b; margin-top:8px;'>No data available.</p>"
        
        display_df = df.copy()
        html = ['<div class="table-container-card"><table class="custom-data-table">']
        
        if isinstance(display_df.columns, pd.MultiIndex):
            html.append('<thead><tr>')
            html.append('<th rowspan="2" style="vertical-align: middle;">Month Year</th>')
            for top in display_df.columns.get_level_values(0).unique():
                span = sum(1 for c in display_df.columns if c[0] == top)
                html.append(f'<th colspan="{span}">{top}</th>')
            html.append('</tr>')

            html.append('<tr>')
            for col in display_df.columns:
                html.append(f'<th>{col[1]}</th>')
            html.append('</tr></thead><tbody>')

            for idx, row in display_df.iterrows():
                html.append('<tr>')
                html.append(f'<td style="font-weight:700; background-color:#f8fafc;">{idx}</td>')
                for col_name, val in row.items():
                    sub_col = col_name[1]
                    if "Yield" in sub_col:
                        val_str = f"{val:.2f}%" if pd.notnull(val) and val > 0 else "-"
                    else:
                        val_str = f"{val:,.2f}" if pd.notnull(val) and val != 0 else "-"
                    html.append(f'<td>{val_str}</td>')
                html.append('</tr>')
            html.append('</tbody></table></div>')
        else:
            html.append('<thead><tr>')
            for col in display_df.columns:
                html.append(f'<th>{col}</th>')
            html.append('</tr></thead><tbody>')
            for _, row in display_df.iterrows():
                html.append('<tr>')
                for col, val in row.items():
                    if format_dict and col in format_dict:
                        val_str = format_dict[col].format(val) if pd.notnull(val) and isinstance(val, (int, float)) else str(val)
                    else:
                        if isinstance(val, float):
                            val_str = f"{val:,.2f}" if val != 0 else "-"
                        elif isinstance(val, int):
                            val_str = f"{val}"
                        else:
                            val_str = str(val) if pd.notnull(val) and str(val).strip() != "" else "-"
                    html.append(f'<td>{val_str}</td>')
                html.append('</tr>')
            html.append('</tbody></table></div>')

        return "".join(html)

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

    # --- CACHED LATEST DATE RETRIEVAL ---
    @st.cache_data(ttl=60)
    def get_latest_dates():
        q_bills = text('SELECT MAX("Data_Date")::TEXT FROM public.daily_bills')
        q_secs = text('SELECT MAX("Data_Date")::TEXT FROM public.daily_securities')
        with engine.connect() as conn:
            latest_bill = conn.execute(q_bills).scalar()
            latest_sec = conn.execute(q_secs).scalar()
        return latest_bill, latest_sec

    latest_bill_date, latest_sec_date = get_latest_dates()

    # --- FAST SINGLE-SNAPSHOT LOADER ---
    @st.cache_data(ttl=60)
    def load_snapshot(table_name, target_date_str):
        if not target_date_str:
            return pd.DataFrame()
        q = text(f'SELECT * FROM public.{table_name} WHERE "Data_Date"::DATE = :d')
        return pd.read_sql(q, engine, params={"d": str(target_date_str)})

    # --- CACHED HISTORICAL RANGE LOADER ---
    @st.cache_data(ttl=60)
    def load_historical_range(table_name, start_d, end_d):
        if not start_d or not end_d:
            return pd.DataFrame()
        q = text(f'SELECT * FROM public.{table_name} WHERE "Data_Date"::DATE BETWEEN :s AND :e ORDER BY "Data_Date" DESC')
        return pd.read_sql(q, engine, params={"s": str(start_d), "e": str(end_d)})

    # --- SUMMARY BLOCK RENDERER ---
    def render_summary_block(df, actual_date, title, header_class, include_coupon=False):
        if df.empty:
            st.markdown(f'<div class="{header_class}">{title}</div>', unsafe_allow_html=True)
            st.info(f"No {title} data available for {actual_date}.")
            return

        temp_df = df.drop_duplicates(subset=["ISIN"], keep="first").copy()
        count = int(temp_df["ISIN"].nunique())

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

        coupon_str = "N/A"
        if include_coupon:
            coupon_col = next((c for c in temp_df.columns if "coupon" in c.lower() and "freq" not in c.lower() and "date" not in c.lower()), None)
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

        header_html = f'<div class="{header_class}">{title} <span style="font-size: 0.85rem; color: #64748b; font-weight: normal;">(as of {actual_date})</span></div>'
        if include_coupon:
            table_html = f"""
            <table class="summary-table">
                <thead>
                    <tr><th>Count</th><th>Amount (BDT Cr)</th><th>WA Yield</th><th>WA Coupon</th></tr>
                </thead>
                <tbody>
                    <tr><td>{count}</td><td>৳{total_crore:,.2f} Cr</td><td>{weighted_yield:.4f}%</td><td>{coupon_str}</td></tr>
                </tbody>
            </table>
            """
        else:
            table_html = f"""
            <table class="summary-table">
                <thead>
                    <tr><th>Count</th><th>Amount (BDT Cr)</th><th>WA Yield</th></tr>
                </thead>
                <tbody>
                    <tr><td>{count}</td><td>৳{total_crore:,.2f} Cr</td><td>{weighted_yield:.4f}%</td></tr>
                </tbody>
            </table>
            """
        st.markdown(header_html + table_html, unsafe_allow_html=True)

    # --- MATURITY DETAILS LOGIC (COUPON EXCLUDED FOR BILLS, INCLUDED FOR BONDS) ---
    def compute_maturity_detail(df, base_date_str, days=30, is_bond=False):
        if df.empty or "Maturity/ Expiry Date" not in df.columns or not base_date_str:
            return pd.DataFrame(), 0.0, 0

        snapshot = df.drop_duplicates(subset=["ISIN"], keep="first").copy()
        base_dt = pd.to_datetime(base_date_str, errors="coerce")
        mat_dt = pd.to_datetime(snapshot["Maturity/ Expiry Date"], format="mixed", errors="coerce")
        
        mask = (mat_dt >= base_dt) & (mat_dt <= base_dt + pd.Timedelta(days=days))
        maturing = snapshot[mask].copy()

        if maturing.empty:
            return maturing, 0.0, 0

        # Standardize Outstanding to Crore
        maturing["Outstanding (BDT Cr)"] = pd.to_numeric(
            maturing["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0) / 10.0

        # Sort by chronological maturity date
        maturing["_mat_sort"] = pd.to_datetime(maturing["Maturity/ Expiry Date"], format="mixed", errors="coerce")
        maturing = maturing.sort_values(by="_mat_sort", ascending=True).drop(columns=["_mat_sort"])
        
        # Standardize Market Yield display
        if "Market Yield" in maturing.columns:
            maturing["Market Yield"] = maturing["Market Yield"].astype(str).apply(lambda x: x if "%" in x else (f"{float(x):.2f}%" if x.replace(".", "", 1).isdigit() else x))

        if is_bond:
            # Identify Coupon Column dynamically for Bonds
            coupon_col = next((c for c in maturing.columns if "coupon" in c.lower() and "freq" not in c.lower() and "date" not in c.lower()), None)
            if coupon_col and coupon_col in maturing.columns:
                maturing["Coupon Rate"] = maturing[coupon_col].astype(str).apply(lambda x: x if "%" in x else (f"{float(x):.2f}%" if x.replace(".", "", 1).isdigit() else x))
            else:
                maturing["Coupon Rate"] = "-"

            preferred_cols = [
                "ISIN", "Securities Name", "Issue Date", 
                "Maturity/ Expiry Date", "Coupon Rate", "Market Yield", 
                "Outstanding (BDT Cr)"
            ]
        else:
            # For T-Bills: Explicitly do not include Coupon
            preferred_cols = [
                "ISIN", "Securities Name", "Issue Date", 
                "Maturity/ Expiry Date", "Market Yield", 
                "Outstanding (BDT Cr)"
            ]

        display_df = maturing[[c for c in preferred_cols if c in maturing.columns]].copy()
        display_df.insert(0, "Sl. No.", range(1, len(display_df) + 1))

        return display_df, float(maturing["Outstanding (BDT Cr)"].sum()), int(maturing["ISIN"].nunique())

    # --- MATURITY LADDERING (ANALYTICS) ---
    def compute_maturity_ladder(df, base_date_str):
        if df.empty or "Maturity/ Expiry Date" not in df.columns or not base_date_str:
            return pd.DataFrame()

        snapshot = df.drop_duplicates(subset=["ISIN"], keep="first").copy()
        base_dt = pd.to_datetime(base_date_str, errors="coerce")
        snapshot["Mat_Dt"] = pd.to_datetime(snapshot["Maturity/ Expiry Date"], format="mixed", errors="coerce")
        snapshot = snapshot.dropna(subset=["Mat_Dt"])
        snapshot["Days_To_Mat"] = (snapshot["Mat_Dt"] - base_dt).dt.days

        snapshot["Amt_Cr"] = pd.to_numeric(
            snapshot["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0) / 10.0

        bins = [-float('inf'), 0, 30, 91, 182, 365, 730, 1825, 3650, float('inf')]
        labels = ["Overdue", "1-30 Days", "31-91 Days", "92-182 Days", "183-365 Days", "1-2 Years", "2-5 Years", "5-10 Years", "Over 10 Years"]
        
        snapshot["Bucket"] = pd.cut(snapshot["Days_To_Mat"], bins=bins, labels=labels)
        ladder = snapshot.groupby("Bucket", observed=False).agg(
            Count=("ISIN", "nunique"),
            Amount_Cr=("Amt_Cr", "sum")
        ).reset_index()

        ladder.columns = ["Time Bucket", "Active ISINs", "Outstanding (BDT Cr)"]
        return ladder

    # --- MONTHLY LEDGER COMPUTATION (WITH HISTORICAL MATURITY DETECTION) ---
    def calculate_monthly_metrics(df, start_d=None, end_d=None):
        cols = ["Newly Issued", "New WA Yield", "Reissued", "Reissue WA Yield", "Settled"]
        if df.empty or "ISIN" not in df.columns or "Data_Date" not in df.columns:
            return pd.DataFrame(columns=cols)

        temp_df = df.copy()
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
        
        min_date = pd.to_datetime(start_d).normalize() if start_d else temp_df["Data_Dt"].min()
        max_date = pd.to_datetime(end_d).normalize() if end_d else temp_df["Data_Dt"].max()
        
        temp_df = temp_df.sort_values(by=["ISIN", "Data_Dt"])

        # 1. NEWLY ISSUED & NEW WA YIELD
        first_records = temp_df[temp_df["Amt_Cr"] > 0].drop_duplicates(subset=["ISIN"], keep="first").copy()
        first_records = first_records.dropna(subset=["Issue_Dt"])
        first_records = first_records[(first_records["Issue_Dt"] >= min_date) & (first_records["Issue_Dt"] <= max_date)]
        first_records["Month"] = first_records["Issue_Dt"].dt.to_period("M")
        
        newly_issued = first_records.groupby("Month")["Amt_Cr"].sum().rename("Newly Issued")
        newly_issued_yield_vol = (first_records["Amt_Cr"] * first_records["Yield_Val"]).groupby(first_records["Month"]).sum()
        new_wa_yield = (newly_issued_yield_vol / newly_issued).fillna(0).rename("New WA Yield")

        # 2. REISSUED & REISSUE WA YIELD
        temp_df["Amt_Diff"] = temp_df.groupby("ISIN")["Amt_Cr"].diff()
        reissues = temp_df[temp_df["Amt_Diff"] > 0].copy()
        reissues = reissues.dropna(subset=["Data_Dt"])
        reissues = reissues[(reissues["Data_Dt"] >= min_date) & (reissues["Data_Dt"] <= max_date)]
        reissues["Month"] = reissues["Data_Dt"].dt.to_period("M")
        
        reissued = reissues.groupby("Month")["Amt_Diff"].sum().rename("Reissued")
        reissued_yield_vol = (reissues["Amt_Diff"] * reissues["Yield_Val"]).groupby(reissues["Month"]).sum()
        reissue_wa_yield = (reissued_yield_vol / reissued).fillna(0).rename("Reissue WA Yield")

        # 3. SETTLED / MATURED
        max_amt_per_isin = temp_df.groupby("ISIN")["Amt_Cr"].max().reset_index(name="Max_Amt")
        unique_isins = temp_df.drop_duplicates(subset=["ISIN"], keep="last")[["ISIN", "Mat_Dt"]].merge(max_amt_per_isin, on="ISIN")
        
        settled_mask = (unique_isins["Mat_Dt"] >= min_date) & (unique_isins["Mat_Dt"] <= max_date)
        settled_records = unique_isins[settled_mask].copy()

        if not settled_records.empty:
            settled_records["Month"] = settled_records["Mat_Dt"].dt.to_period("M")
            settled = settled_records.groupby("Month")["Max_Amt"].sum().rename("Settled")
        else:
            settled = pd.Series(dtype=float, name="Settled")

        monthly = pd.concat([newly_issued, new_wa_yield, reissued, reissue_wa_yield, settled], axis=1).fillna(0)
        
        for c in cols:
            if c not in monthly.columns:
                monthly[c] = 0.0
                
        start_p = min_date.to_period("M")
        end_p = max_date.to_period("M")
        all_months = pd.period_range(start=start_p, end=end_p, freq="M")
        monthly = monthly.reindex(all_months, fill_value=0.0)
        
        return monthly[cols]

    # --- DRILL-DOWN INSTRUMENT EXTRACTOR ---
    def get_monthly_drilldown_details(df, selected_month_period, event_type, instrument_label):
        if df.empty or "ISIN" not in df.columns:
            return pd.DataFrame()

        temp_df = df.copy()
        temp_df["Amt_Cr"] = pd.to_numeric(
            temp_df["Outstanding BDT (in Mill)"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        ).fillna(0) / 10.0

        temp_df["Data_Dt"] = pd.to_datetime(temp_df["Data_Date"], errors="coerce").dt.normalize()
        
        issue_col = "Issue Date" if "Issue Date" in temp_df.columns else None
        mat_col = "Maturity/ Expiry Date" if "Maturity/ Expiry Date" in temp_df.columns else None
        
        temp_df["Issue_Dt"] = pd.to_datetime(temp_df[issue_col], format="mixed", errors="coerce").dt.normalize() if issue_col else pd.NaT
        temp_df["Mat_Dt"] = pd.to_datetime(temp_df[mat_col], format="mixed", errors="coerce").dt.normalize() if mat_col else pd.NaT
        
        temp_df = temp_df.sort_values(by=["ISIN", "Data_Dt"])

        coupon_col = next((c for c in temp_df.columns if "coupon" in c.lower() and "freq" not in c.lower() and "date" not in c.lower()), None)
        rem_mat_col = next((c for c in temp_df.columns if "remaining" in c.lower()), "Remaining Maturity")

        match = pd.DataFrame()
        if event_type == "Newly Issued":
            first_records = temp_df[temp_df["Amt_Cr"] > 0].drop_duplicates(subset=["ISIN"], keep="first").copy()
            first_records = first_records.dropna(subset=["Issue_Dt"])
            match = first_records[first_records["Issue_Dt"].dt.to_period("M") == selected_month_period].copy()
            if not match.empty:
                match["Event Amount (BDT Cr)"] = match["Amt_Cr"]
                match["Event Date"] = match["Issue_Dt"].dt.strftime("%Y-%m-%d")
                match["Category"] = "New Issue"

        elif event_type == "Reissued":
            temp_df["Amt_Diff"] = temp_df.groupby("ISIN")["Amt_Cr"].diff()
            reissues = temp_df[temp_df["Amt_Diff"] > 0].copy()
            reissues = reissues.dropna(subset=["Data_Dt"])
            match = reissues[reissues["Data_Dt"].dt.to_period("M") == selected_month_period].copy()
            if not match.empty:
                match["Event Amount (BDT Cr)"] = match["Amt_Diff"]
                match["Event Date"] = match["Data_Dt"].dt.strftime("%Y-%m-%d")
                match["Category"] = "Reissue"

        elif event_type == "Settled":
            max_amt_per_isin = temp_df.groupby("ISIN")["Amt_Cr"].max().reset_index(name="Max_Amt")
            last_records = temp_df.drop_duplicates(subset=["ISIN"], keep="last").copy()
            last_records = last_records.merge(max_amt_per_isin, on="ISIN")
            past_mat = last_records.dropna(subset=["Mat_Dt"]).copy()
            match = past_mat[past_mat["Mat_Dt"].dt.to_period("M") == selected_month_period].copy()
            if not match.empty:
                match["Event Amount (BDT Cr)"] = match["Max_Amt"]
                match["Event Date"] = match["Mat_Dt"].dt.strftime("%Y-%m-%d")
                match["Category"] = "Maturity / Settlement"

        if not match.empty:
            if instrument_label != "Treasury Bills":
                if coupon_col and coupon_col in match.columns:
                    match["Coupon Rate"] = match[coupon_col]
                else:
                    match["Coupon Rate"] = "-"
                
            if rem_mat_col and rem_mat_col in match.columns:
                match["Remaining Maturity"] = match[rem_mat_col]
            else:
                match["Remaining Maturity"] = "-"

        return match


    # ==========================================
    # --- SIDEBAR NAVIGATION ---
    # ==========================================
    with st.sidebar:
        st.markdown("## 🏛️ GSOM Treasury")
        menu_selection = st.radio(
            "Go to Menu:",
            ["📊 Latest Market Summary", "📈 Analytics & Gap Ladder", "📁 Historical Data Export"],
            index=0
        )
        st.markdown("---")
        st.caption(f"**Latest Bill Date:** {latest_bill_date or 'N/A'}")
        st.caption(f"**Latest Bond Date:** {latest_sec_date or 'N/A'}")


    # ==========================================
    # --- 1. LATEST MARKET SUMMARY (DEFAULT) ---
    # ==========================================
    if menu_selection == "📊 Latest Market Summary":
        st.markdown(f"""
            <div style="margin-bottom: 1.25rem;">
                <h2 style="margin-bottom: 0;">🏛️ GSOM Daily</h2>
                <p style="color:#64748b; font-size:1rem; margin-top:0.25rem;">
                    Treasury Bills, FRTBs, and Treasury Bonds
                </p>
            </div>
        """, unsafe_allow_html=True)

        df_latest_bills = load_snapshot("daily_bills", latest_bill_date)
        df_latest_secs = load_snapshot("daily_securities", latest_sec_date)

        if not df_latest_secs.empty:
            frtb_mask = df_latest_secs.apply(lambda row: row.astype(str).str.contains('FRTB', case=False).any(), axis=1)
            df_latest_frtbs = df_latest_secs[frtb_mask]
            df_latest_bonds = df_latest_secs[~frtb_mask]
        else:
            df_latest_frtbs = pd.DataFrame()
            df_latest_bonds = pd.DataFrame()

        sum_col1, sum_col2, sum_col3 = st.columns(3)
        with sum_col1:
            render_summary_block(df_latest_bills, latest_bill_date, "Treasury Bills", "bill-header", include_coupon=False)
        with sum_col2:
            render_summary_block(df_latest_frtbs, latest_sec_date, "FRTBs", "frtb-header", include_coupon=True)
        with sum_col3:
            render_summary_block(df_latest_bonds, latest_sec_date, "Treasury Bonds", "bond-header", include_coupon=True)

        st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

        # Maturity Snapshot (30 Days) - Clean Side-by-Side Cards (No Coupon for Bills, Coupon for Bonds)
        st.markdown("#### ⏰ Upcoming Maturity Snapshot (Next 30 Days)")
        bills_mat, bills_mat_cr, bills_mat_cnt = compute_maturity_detail(df_latest_bills, latest_bill_date, days=30, is_bond=False)
        secs_mat, secs_mat_cr, secs_mat_cnt = compute_maturity_detail(df_latest_secs, latest_sec_date, days=30, is_bond=True)

        mat_col1, mat_col2 = st.columns(2)
        with mat_col1:
            st.markdown(f"""
                <div class="custom-metric-card bill-card">
                    <div class="custom-metric-label">T-Bills Maturing (from {latest_bill_date})</div>
                    <div class="custom-metric-value">৳ {bills_mat_cr:,.2f} Cr</div>
                    <div class="custom-metric-delta">📌 {bills_mat_cnt} ISINs Maturing</div>
                </div>
            """, unsafe_allow_html=True)
            if not bills_mat.empty:
                st.markdown(render_centered_html_table(bills_mat, format_dict={"Outstanding (BDT Cr)": "{:,.2f}"}), unsafe_allow_html=True)
            else:
                st.caption("No T-Bill ISINs maturing in the next 30 days.")

        with mat_col2:
            st.markdown(f"""
                <div class="custom-metric-card bond-card">
                    <div class="custom-metric-label">Bonds/FRTBs Maturing (from {latest_sec_date})</div>
                    <div class="custom-metric-value">৳ {secs_mat_cr:,.2f} Cr</div>
                    <div class="custom-metric-delta">📌 {secs_mat_cnt} ISINs Maturing</div>
                </div>
            """, unsafe_allow_html=True)
            if not secs_mat.empty:
                st.markdown(render_centered_html_table(secs_mat, format_dict={"Outstanding (BDT Cr)": "{:,.2f}"}), unsafe_allow_html=True)
            else:
                st.caption("No Bond/FRTB ISINs maturing in the next 30 days.")

        st.markdown("<hr style='margin: 18px 0; border: 0; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

        # Active Holdings Raw View
        st.markdown("#### 📑 AVAILABLE SECURITIES IN THE MARKET")
        tab1, tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])
        with tab1:
            if not df_latest_bills.empty:
                disp_b = df_latest_bills.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_latest_bills.columns], errors="ignore")
                st.dataframe(disp_b, width="stretch")
            else:
                st.info("No T-Bill data available.")
        with tab2:
            if not df_latest_secs.empty:
                disp_s = df_latest_secs.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_latest_secs.columns], errors="ignore")
                st.dataframe(disp_s, width="stretch")
            else:
                st.info("No Securities data available.")


    # ==========================================
    # --- 2. ANALYTICS & GAP LADDER ---
    # ==========================================
    elif menu_selection == "📈 Analytics & Gap Ladder":
        st.markdown("""
            <div style="margin-bottom: 1.25rem;">
                <h2 style="margin-bottom: 0;">📈 Treasury Analytics &amp; ALM Laddering</h2>
                <p style="color:#64748b; font-size:1rem; margin-top:0.25rem;">
                    Maturity gap laddering and interactive monthly ledger drill-down.
                </p>
            </div>
        """, unsafe_allow_html=True)

        ana_tab1, ana_tab2 = st.tabs(["🪜 Maturity Gap Ladder", "📅 Monthly Issuance & Settlement Ledger"])

        # TAB 1: MATURITY GAP LADDER
        with ana_tab1:
            st.markdown("#### 🪜 Maturity Bucket Distribution (as of Latest Date)")
            df_latest_bills = load_snapshot("daily_bills", latest_bill_date)
            df_latest_secs = load_snapshot("daily_securities", latest_sec_date)

            col_lad1, col_lad2 = st.columns(2)
            with col_lad1:
                st.markdown(f"<div style='text-align:center; font-weight:700; color:#0f172a; margin-bottom:6px;'>Treasury Bills Ladder <span style='font-weight:normal; color:#64748b;'>(as of {latest_bill_date})</span></div>", unsafe_allow_html=True)
                bill_ladder = compute_maturity_ladder(df_latest_bills, latest_bill_date)
                if not bill_ladder.empty:
                    st.markdown(
                        render_centered_html_table(bill_ladder, format_dict={"Outstanding (BDT Cr)": "{:,.2f}"}),
                        unsafe_allow_html=True
                    )
                else:
                    st.info("No data available.")

            with col_lad2:
                st.markdown(f"<div style='text-align:center; font-weight:700; color:#0f172a; margin-bottom:6px;'>Bonds & FRTBs Ladder <span style='font-weight:normal; color:#64748b;'>(as of {latest_sec_date})</span></div>", unsafe_allow_html=True)
                bond_ladder = compute_maturity_ladder(df_latest_secs, latest_sec_date)
                if not bond_ladder.empty:
                    st.markdown(
                        render_centered_html_table(bond_ladder, format_dict={"Outstanding (BDT Cr)": "{:,.2f}"}),
                        unsafe_allow_html=True
                    )
                else:
                    st.info("No data available.")

        # TAB 2: MONTHLY ISSUANCE & SETTLEMENT LEDGER (FORM-ISOLATED SEARCH)
        with ana_tab2:
            st.markdown("#### 📅 Monthly Issuance, Reissuance & Settlement Ledger (BDT Cr)")
            with st.form("analytics_range_form"):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    ana_start = st.date_input("Start Date", value=pd.to_datetime(latest_bill_date or "2026-01-01").date() - timedelta(days=240))
                with col_a2:
                    ana_end = st.date_input("End Date", value=pd.to_datetime(latest_bill_date or "2026-08-27").date())
                run_ledger = st.form_submit_button("📊 Compute Ledger", type="primary")

            if run_ledger:
                st.session_state["ana_start"] = str(ana_start)
                st.session_state["ana_end"] = str(ana_end)

            if "ana_start" in st.session_state and "ana_end" in st.session_state:
                s_d = st.session_state["ana_start"]
                e_d = st.session_state["ana_end"]

                with st.spinner("Computing monthly volume across selected history..."):
                    df_ana_bills = load_historical_range("daily_bills", s_d, e_d)
                    df_ana_secs = load_historical_range("daily_securities", s_d, e_d)

                    if not df_ana_secs.empty:
                        frtb_mask_ana = df_ana_secs.apply(lambda row: row.astype(str).str.contains('FRTB', case=False).any(), axis=1)
                        df_ana_frtbs = df_ana_secs[frtb_mask_ana]
                        df_ana_bonds = df_ana_secs[~frtb_mask_ana]
                    else:
                        df_ana_frtbs = pd.DataFrame()
                        df_ana_bonds = pd.DataFrame()

                    sub_cols = ["Newly Issued", "New WA Yield", "Reissued", "Reissue WA Yield", "Settled"]

                    bills_monthly = calculate_monthly_metrics(df_ana_bills, s_d, e_d)
                    frtbs_monthly = calculate_monthly_metrics(df_ana_frtbs, s_d, e_d)
                    bonds_monthly = calculate_monthly_metrics(df_ana_bonds, s_d, e_d)

                    dfs_to_join = []
                    
                    if not bills_monthly.empty:
                        b_df = bills_monthly.copy()
                        b_df.columns = pd.MultiIndex.from_product([["Treasury Bills"], sub_cols])
                        dfs_to_join.append(b_df)
                    else:
                        empty_idx = pd.MultiIndex.from_product([["Treasury Bills"], sub_cols])
                        dfs_to_join.append(pd.DataFrame(columns=empty_idx))

                    if not frtbs_monthly.empty:
                        f_df = frtbs_monthly.copy()
                        f_df.columns = pd.MultiIndex.from_product([["FRTBs"], sub_cols])
                        dfs_to_join.append(f_df)
                    else:
                        empty_idx = pd.MultiIndex.from_product([["FRTBs"], sub_cols])
                        dfs_to_join.append(pd.DataFrame(columns=empty_idx))

                    if not bonds_monthly.empty:
                        bd_df = bonds_monthly.copy()
                        bd_df.columns = pd.MultiIndex.from_product([["Treasury Bonds"], sub_cols])
                        dfs_to_join.append(bd_df)
                    else:
                        empty_idx = pd.MultiIndex.from_product([["Treasury Bonds"], sub_cols])
                        dfs_to_join.append(pd.DataFrame(columns=empty_idx))

                    combined_monthly = dfs_to_join[0]
                    for d in dfs_to_join[1:]:
                        combined_monthly = combined_monthly.join(d, how="outer")
                    
                    combined_monthly = combined_monthly.fillna(0)
                    combined_monthly.sort_index(ascending=False, inplace=True)

                    if not combined_monthly.empty:
                        month_periods = combined_monthly.index.tolist()
                        combined_display = combined_monthly.copy()
                        combined_display.index = combined_display.index.strftime("%b-%y")
                        combined_display.index.name = "Month Year"

                        # 1. Render Multi-Tier HTML Table
                        st.markdown(
                            render_centered_html_table(combined_display),
                            unsafe_allow_html=True
                        )

                        # 2. Form-Isolated Drill-Down Section
                        st.markdown("---")
                        st.markdown("#### 🔍 Inspect Underlyings / Instrument Breakdown")

                        with st.form("drilldown_form"):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                selected_label = st.selectbox("Select Month", combined_display.index.tolist())
                            with c2:
                                inst_choice = st.selectbox("Select Instrument", ["Treasury Bills", "FRTBs", "Treasury Bonds"])
                            with c3:
                                event_choice = st.selectbox("Select Event Type", ["Newly Issued", "Reissued", "Settled"])
                            
                            search_drilldown = st.form_submit_button("🔍 Search Breakdown", type="primary")

                        if search_drilldown:
                            st.session_state["drill_month"] = selected_label
                            st.session_state["drill_inst"] = inst_choice
                            st.session_state["drill_event"] = event_choice

                        if "drill_month" in st.session_state:
                            d_month = st.session_state["drill_month"]
                            d_inst = st.session_state["drill_inst"]
                            d_event = st.session_state["drill_event"]

                            if d_month in combined_display.index.tolist():
                                selected_idx = combined_display.index.tolist().index(d_month)
                                selected_period = month_periods[selected_idx]
                                target_df = df_ana_bills if d_inst == "Treasury Bills" else (df_ana_frtbs if d_inst == "FRTBs" else df_ana_bonds)
                                
                                details_df = get_monthly_drilldown_details(target_df, selected_period, d_event, d_inst)

                                if not details_df.empty:
                                    total_event_cr = details_df["Event Amount (BDT Cr)"].sum()
                                    st.success(f"**{d_inst}** | **{d_event}** in **{d_month}**: **৳ {total_event_cr:,.2f} Cr** across **{details_df['ISIN'].nunique()} ISINs**")
                                    
                                    # Adapt column sequence dynamically based on instrument type
                                    if d_inst == "Treasury Bills":
                                        preferred_cols = [
                                            "ISIN", "Securities Name", "Category", "Event Date", 
                                            "Event Amount (BDT Cr)", "Market Yield", 
                                            "Remaining Maturity", "Issue Date", "Maturity/ Expiry Date", 
                                            "Outstanding BDT (in Mill)"
                                        ]
                                    else:
                                        preferred_cols = [
                                            "ISIN", "Securities Name", "Category", "Event Date", 
                                            "Event Amount (BDT Cr)", "Market Yield", "Coupon Rate", 
                                            "Remaining Maturity", "Issue Date", "Maturity/ Expiry Date", 
                                            "Outstanding BDT (in Mill)"
                                        ]
                                        
                                    display_cols = [c for c in preferred_cols if c in details_df.columns]
                                    
                                    st.markdown(
                                        render_centered_html_table(details_df[display_cols], format_dict={"Event Amount (BDT Cr)": "{:,.2f}"}),
                                        unsafe_allow_html=True
                                    )
                                    
                                    st.download_button(
                                        f"⬇️ Download {d_month} {d_inst} {d_event} (Excel)",
                                        data=to_excel_bytes(details_df, f"{d_month}_{d_event}"),
                                        file_name=f"details_{d_month}_{d_inst}_{d_event}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    )
                                else:
                                    st.info(f"No {d_inst} recorded as {d_event} in {d_month}.")
                    else:
                        st.info("No records found in this range.")


    # ==========================================
    # --- 3. HISTORICAL DATA EXPORT ---
    # ==========================================
    elif menu_selection == "📁 Historical Data Export":
        st.markdown("""
            <div style="margin-bottom: 1.25rem;">
                <h2 style="margin-bottom: 0;">📁 Historical Data Browser &amp; Export</h2>
                <p style="color:#64748b; font-size:1rem; margin-top:0.25rem;">
                    Filter and download raw records for Treasury Bills, FRTBs, and Treasury Bonds across custom date ranges.
                </p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("historical_export_form"):
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                hist_start = st.date_input("From Date", value=pd.to_datetime(latest_bill_date or "2026-07-28").date() - timedelta(days=30))
            with col_h2:
                hist_end = st.date_input("To Date", value=pd.to_datetime(latest_bill_date or "2026-08-27").date())
            load_hist = st.form_submit_button("🔎 Load Records", type="primary")

        if load_hist:
            with st.spinner("Fetching historical records from database..."):
                df_hist_bills = load_historical_range("daily_bills", hist_start, hist_end)
                df_hist_secs = load_historical_range("daily_securities", hist_start, hist_end)

                h_tab1, h_tab2 = st.tabs(["📉 Treasury Bills", "📈 Bonds & FRTBs"])
                with h_tab1:
                    st.subheader(f"Treasury Bills ({hist_start} to {hist_end})")
                    if not df_hist_bills.empty:
                        disp_bills = df_hist_bills.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_hist_bills.columns], errors="ignore")
                        st.dataframe(disp_bills, width="stretch")
                        st.download_button(
                            "⬇️ Download T-Bills (Excel)",
                            data=to_excel_bytes(df_hist_bills, "T-Bills"),
                            file_name=f"tbills_{hist_start}_to_{hist_end}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    else:
                        st.info("No T-Bill records found for this date range.")

                with h_tab2:
                    st.subheader(f"Bonds & FRTBs ({hist_start} to {hist_end})")
                    if not df_hist_secs.empty:
                        disp_secs = df_hist_secs.drop(columns=[c for c in ["id", "ID", "Id"] if c in df_hist_secs.columns], errors="ignore")
                        st.dataframe(disp_secs, width="stretch")
                        st.download_button(
                            "⬇️ Download Bonds/FRTBs (Excel)",
                            data=to_excel_bytes(df_hist_secs, "Bonds_FRTB"),
                            file_name=f"bonds_frtb_{hist_start}_to_{hist_end}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    else:
                        st.info("No Bond/FRTB records found for this date range.")

except Exception as e:
    st.error("🚨 An unhandled exception occurred in the app:")
    st.code(traceback.format_exc())
