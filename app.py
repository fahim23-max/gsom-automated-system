import os
import io
from datetime import timedelta

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="GSOM Treasury Dashboard",
    page_icon="📈",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    /* ========================================================
       PAGE
       ======================================================== */

    .stApp {
        background-color: #f8fafc;
    }

    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }


    /* ========================================================
       HEADINGS
       ======================================================== */

    h1 {
        color: #0f172a;
    }

    h2, h3, h4 {
        color: #0f172a;
    }


    /* ========================================================
       NATIVE STREAMLIT METRIC CARDS
       ======================================================== */

    [data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
    }

    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-weight: 600;
    }

    [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-weight: 700;
    }

    [data-testid="stMetricDelta"] {
        font-size: 0.85rem;
    }


    /* ========================================================
       DATAFRAME
       ======================================================== */

    [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }


    /* ========================================================
       DIVIDER
       ======================================================== */

    hr {
        border: 0;
        border-top: 1px solid #e2e8f0;
        margin: 20px 0;
    }


    /* ========================================================
       SECTION CAPTION
       ======================================================== */

    .section-caption {
        color: #64748b;
        font-size: 0.85rem;
        margin-top: -8px;
        margin-bottom: 10px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    st.error("DATABASE_URL environment variable is not configured.")
    st.stop()

try:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"prepare_threshold": None}
    )
except Exception as e:
    st.error(f"Unable to connect to the database: {e}")
    st.stop()


# ============================================================
# TITLE
# ============================================================

st.markdown(
    """
    <div style="text-align:center; margin-bottom:1rem;">
        <h1 style="margin-bottom:0;">
            🏛️ GSOM Treasury &amp; Securities Dashboard
        </h1>
        <p style="
            color:#64748b;
            font-size:1.05rem;
            margin-top:0.25rem;
        ">
            Live data for Government Bonds, FRTBs, and T-Bills
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def to_date(value):
    """Convert a database date value to Python date."""
    if value is None:
        return None

    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def default_range(min_value, max_value, lookback_days=30):
    """Return a sensible default date range."""
    mn = to_date(min_value)
    mx = to_date(max_value)

    if mn is None or mx is None:
        return None, None

    start = max(
        mn,
        mx - timedelta(days=lookback_days)
    )

    return start, mx


def unpack_range(value):
    """
    st.date_input returns a tuple when both dates have been selected.
    """
    if isinstance(value, tuple) and len(value) == 2:
        return value[0], value[1]

    return None, None


def clean_number(series):
    """
    Convert strings such as:
        12,345.67
        9.25%
        BDT 12,345
    into numeric values.
    """
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("BDT", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0)


def get_latest_snapshot(df):
    """
    Return the latest available date snapshot with duplicate ISINs removed.
    """
    if df.empty or "Data_Date" not in df.columns:
        return pd.DataFrame()

    latest_date = df["Data_Date"].max()

    snapshot = df[
        df["Data_Date"] == latest_date
    ].copy()

    if "ISIN" in snapshot.columns:
        snapshot = snapshot.drop_duplicates(
            subset="ISIN"
        )

    return snapshot


def remove_id_columns(df):
    """Remove database ID columns from display/export."""
    if df.empty:
        return df.copy()

    columns_to_remove = [
        c for c in ["id", "ID", "Id"]
        if c in df.columns
    ]

    return df.drop(
        columns=columns_to_remove,
        errors="ignore"
    )


# ============================================================
# DATABASE DATE BOUNDS
# ============================================================

@st.cache_data(ttl=30)
def get_bill_date_bounds():
    try:
        query = """
            SELECT
                MIN("Data_Date")::TEXT,
                MAX("Data_Date")::TEXT
            FROM public.daily_bills
        """

        df = pd.read_sql(
            query,
            engine
        )

        return df.iloc[0, 0], df.iloc[0, 1]

    except Exception as e:
        st.error(
            f"Error fetching T-Bill date range: {e}"
        )
        return None, None


@st.cache_data(ttl=30)
def get_security_date_bounds():
    try:
        query = """
            SELECT
                MIN("Data_Date")::TEXT,
                MAX("Data_Date")::TEXT
            FROM public.daily_securities
        """

        df = pd.read_sql(
            query,
            engine
        )

        return df.iloc[0, 0], df.iloc[0, 1]

    except Exception as e:
        st.error(
            f"Error fetching Bond/FRTB date range: {e}"
        )
        return None, None


bill_min, bill_max = get_bill_date_bounds()
sec_min, sec_max = get_security_date_bounds()


if not bill_min and not sec_min:
    st.warning(
        "No data found in the database. "
        "Please check your tables or run the scrapers."
    )
    st.stop()


# ============================================================
# DATE RANGE SELECTORS
# ============================================================

st.markdown("### 🔎 Select Date Range")

range_col1, range_col2 = st.columns(2)


with range_col1:

    if bill_min:

        bill_default_start, bill_default_end = default_range(
            bill_min,
            bill_max
        )

        bill_range = st.date_input(
            "📅 T-Bill Date Range",
            value=(
                bill_default_start,
                bill_default_end
            ),
            min_value=to_date(bill_min),
            max_value=to_date(bill_max),
            key="bill_date_range"
        )

    else:

        bill_range = None

        st.info(
            "No T-Bill dates available."
        )


with range_col2:

    if sec_min:

        bond_default_start, bond_default_end = default_range(
            sec_min,
            sec_max
        )

        bond_range = st.date_input(
            "📅 Bond / FRTB Date Range",
            value=(
                bond_default_start,
                bond_default_end
            ),
            min_value=to_date(sec_min),
            max_value=to_date(sec_max),
            key="bond_date_range"
        )

    else:

        bond_range = None

        st.info(
            "No Bond/FRTB dates available."
        )


bill_start, bill_end = unpack_range(
    bill_range
)

bond_start, bond_end = unpack_range(
    bond_range
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=30)
def load_bills_range(start_date, end_date):

    if not start_date or not end_date:
        return pd.DataFrame()

    query = text(
        """
        SELECT *
        FROM public.daily_bills
        WHERE "Data_Date" BETWEEN :start_date AND :end_date
        ORDER BY "Data_Date" DESC
        """
    )

    return pd.read_sql(
        query,
        engine,
        params={
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )


@st.cache_data(ttl=30)
def load_securities_range(start_date, end_date):

    if not start_date or not end_date:
        return pd.DataFrame()

    query = text(
        """
        SELECT *
        FROM public.daily_securities
        WHERE "Data_Date" BETWEEN :start_date AND :end_date
        ORDER BY "Data_Date" DESC
        """
    )

    return pd.read_sql(
        query,
        engine,
        params={
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )


df_bills = load_bills_range(
    bill_start,
    bill_end
)

df_securities = load_securities_range(
    bond_start,
    bond_end
)


# ============================================================
# EXCEL EXPORT
# ============================================================

def to_excel_bytes(df, sheet_name):

    buffer = io.BytesIO()

    export_df = remove_id_columns(df).copy()

    # Fix timezone-aware datetime columns.
    for col in export_df.columns:

        try:

            if (
                pd.api.types.is_datetime64tz_dtype(
                    export_df[col]
                )
            ):
                export_df[col] = (
                    export_df[col]
                    .dt
                    .tz_localize(None)
                )

        except Exception:
            pass

    try:

        with pd.ExcelWriter(
            buffer,
            engine="openpyxl"
        ) as writer:

            export_df.to_excel(
                writer,
                index=False,
                sheet_name=sheet_name[:31]
            )

    except Exception as e:

        st.error(
            f"Unable to create Excel file: {e}"
        )

        return None

    return buffer.getvalue()


# ============================================================
# MATURITY CALCULATION
# ============================================================

def compute_maturity_detail(df, days=30):

    if df.empty:
        return (
            pd.DataFrame(),
            0.0,
            0
        )

    required_columns = [
        "Maturity/ Expiry Date",
        "Data_Date"
    ]

    if not all(
        c in df.columns
        for c in required_columns
    ):
        return (
            pd.DataFrame(),
            0.0,
            0
        )

    latest_date = df["Data_Date"].max()

    snapshot = df[
        df["Data_Date"] == latest_date
    ].copy()

    if "ISIN" in snapshot.columns:

        snapshot = snapshot.drop_duplicates(
            subset="ISIN"
        )

    base_date = pd.to_datetime(
        latest_date,
        errors="coerce"
    )

    maturity_date = pd.to_datetime(
        snapshot["Maturity/ Expiry Date"],
        errors="coerce"
    )

    mask = (
        (maturity_date >= base_date)
        &
        (
            maturity_date
            <=
            base_date + pd.Timedelta(days=days)
        )
    )

    maturing = snapshot[
        mask
    ].copy()

    if maturing.empty:
        return (
            maturing,
            0.0,
            0
        )

    if "Outstanding BDT (in Mill)" in maturing.columns:

        outstanding_crore = (
            clean_number(
                maturing[
                    "Outstanding BDT (in Mill)"
                ]
            ) / 10
        )

    else:

        outstanding_crore = pd.Series(
            0,
            index=maturing.index
        )

    total_crore = outstanding_crore.sum()

    # Sort by maturity date.
    maturing["_maturity_sort"] = pd.to_datetime(
        maturing["Maturity/ Expiry Date"],
        errors="coerce"
    )

    maturing = (
        maturing
        .sort_values(
            "_maturity_sort",
            ascending=True
        )
        .drop(
            columns="_maturity_sort"
        )
    )

    # Remove database IDs.
    maturing = remove_id_columns(
        maturing
    )

    # Remove Data_Date from maturity detail.
    maturing = maturing.drop(
        columns=["Data_Date"],
        errors="ignore"
    )

    # Add serial number.
    serial_column = next(
        (
            c for c in maturing.columns
            if c.lower() in [
                "sl. no.",
                "sl. no",
                "sl_no",
                "sl no"
            ]
        ),
        None
    )

    if serial_column:

        maturing[serial_column] = range(
            1,
            len(maturing) + 1
        )

    else:

        maturing.insert(
            0,
            "Sl. No.",
            range(
                1,
                len(maturing) + 1
            )
        )

    count = (
        maturing["ISIN"].nunique()
        if "ISIN" in maturing.columns
        else len(maturing)
    )

    return (
        maturing,
        float(total_crore),
        int(count)
    )


# ============================================================
# MATURITY RESULTS
# ============================================================

bills_maturing, bills_maturing_crore, bills_maturing_count = (
    compute_maturity_detail(
        df_bills
    )
)

bonds_maturing, bonds_maturing_crore, bonds_maturing_count = (
    compute_maturity_detail(
        df_securities
    )
)


bills_anchor = (
    df_bills["Data_Date"].max()
    if not df_bills.empty
    else "N/A"
)

bonds_anchor = (
    df_securities["Data_Date"].max()
    if not df_securities.empty
    else "N/A"
)


# ============================================================
# PORTFOLIO KPI CALCULATION
# ============================================================

def calculate_portfolio_kpis(
    bills_df,
    securities_df
):

    bills = get_latest_snapshot(
        bills_df
    )

    securities = get_latest_snapshot(
        securities_df
    )

    frames = []

    # ---------------- T-BILLS ----------------

    if not bills.empty:

        if "Outstanding BDT (in Mill)" in bills.columns:

            bills["_Outstanding_Crore"] = (
                clean_number(
                    bills[
                        "Outstanding BDT (in Mill)"
                    ]
                ) / 10
            )

        else:

            bills["_Outstanding_Crore"] = 0

        if "Market Yield" in bills.columns:

            bills["_Yield"] = clean_number(
                bills["Market Yield"]
            )

        else:

            bills["_Yield"] = 0

        frames.append(
            bills
        )

    # ---------------- BONDS ----------------

    if not securities.empty:

        if "Outstanding BDT (in Mill)" in securities.columns:

            securities["_Outstanding_Crore"] = (
                clean_number(
                    securities[
                        "Outstanding BDT (in Mill)"
                    ]
                ) / 10
            )

        else:

            securities["_Outstanding_Crore"] = 0

        if "Market Yield" in securities.columns:

            securities["_Yield"] = clean_number(
                securities["Market Yield"]
            )

        else:

            securities["_Yield"] = 0

        frames.append(
            securities
        )

    if not frames:

        return {
            "outstanding": 0.0,
            "isins": 0,
            "yield": 0.0,
            "maturity": 0.0,
            "maturity_isins": 0
        }

    portfolio = pd.concat(
        frames,
        ignore_index=True
    )

    total_outstanding = (
        portfolio["_Outstanding_Crore"]
        .sum()
    )

    if "ISIN" in portfolio.columns:

        total_isins = (
            portfolio["ISIN"]
            .nunique()
        )

    else:

        total_isins = len(
            portfolio
        )

    if total_outstanding > 0:

        weighted_yield = (
            (
                portfolio["_Yield"]
                *
                portfolio["_Outstanding_Crore"]
            ).sum()
            /
            total_outstanding
        )

    else:

        weighted_yield = 0.0

    maturity_total = (
        bills_maturing_crore
        +
        bonds_maturing_crore
    )

    maturity_isins = (
        bills_maturing_count
        +
        bonds_maturing_count
    )

    return {
        "outstanding": float(
            total_outstanding
        ),
        "isins": int(
            total_isins
        ),
        "yield": float(
            weighted_yield
        ),
        "maturity": float(
            maturity_total
        ),
        "maturity_isins": int(
            maturity_isins
        )
    }


portfolio_kpis = calculate_portfolio_kpis(
    df_bills,
    df_securities
)


# ============================================================
# 1. PORTFOLIO KPIs
# ============================================================

st.markdown("### 📌 Portfolio KPIs")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)


with kpi1:

    st.metric(
        label="Total Outstanding",
        value=(
            f"৳{portfolio_kpis['outstanding']:,.2f} Cr"
        ),
        help=(
            "Total outstanding amount across "
            "the latest T-Bill and Bond/FRTB snapshots."
        )
    )


with kpi2:

    st.metric(
        label="Total ISINs",
        value=(
            f"{portfolio_kpis['isins']:,}"
        ),
        help=(
            "Unique ISINs in the latest available snapshot."
        )
    )


with kpi3:

    st.metric(
        label="Portfolio Wtd. Yield",
        value=(
            f"{portfolio_kpis['yield']:.2f}%"
        ),
        help=(
            "Outstanding-weighted market yield."
        )
    )


with kpi4:

    st.metric(
        label="Maturing in 30 Days",
        value=(
            f"৳{portfolio_kpis['maturity']:,.2f} Cr"
        ),
        delta=(
            f"{portfolio_kpis['maturity_isins']} ISINs"
        ),
        delta_color="off",
        help=(
            "Outstanding amount maturing within "
            "30 days from the latest available snapshot."
        )
    )


# ============================================================
# SUMMARY CALCULATION
# ============================================================

def calculate_summary(
    df,
    include_coupon=False
):

    if df.empty:
        return None

    if "Data_Date" not in df.columns:
        return None

    latest_date = df["Data_Date"].max()

    temp = df[
        df["Data_Date"] == latest_date
    ].copy()

    if "ISIN" in temp.columns:

        temp = temp.drop_duplicates(
            subset="ISIN"
        )

    if temp.empty:
        return None

    # Outstanding.
    if "Outstanding BDT (in Mill)" in temp.columns:

        temp["Outstanding_Crore"] = (
            clean_number(
                temp[
                    "Outstanding BDT (in Mill)"
                ]
            ) / 10
        )

    else:

        temp["Outstanding_Crore"] = 0

    # Market yield.
    if "Market Yield" in temp.columns:

        temp["Yield_Val"] = clean_number(
            temp["Market Yield"]
        )

    else:

        temp["Yield_Val"] = 0

    total_outstanding = (
        temp["Outstanding_Crore"]
        .sum()
    )

    count = (
        temp["ISIN"].nunique()
        if "ISIN" in temp.columns
        else len(temp)
    )

    if total_outstanding > 0:

        weighted_yield = (
            (
                temp["Yield_Val"]
                *
                temp["Outstanding_Crore"]
            ).sum()
            /
            total_outstanding
        )

    else:

        weighted_yield = 0.0

    result = {
        "Count": int(count),
        "Amount": float(
            total_outstanding
        ),
        "Yield": float(
            weighted_yield
        )
    }

    # Coupon for bonds/FRTBs.
    if include_coupon:

        coupon_column = next(
            (
                c for c in temp.columns
                if "coupon" in c.lower()
            ),
            None
        )

        if coupon_column:

            temp["Coupon_Val"] = clean_number(
                temp[coupon_column]
            )

            if total_outstanding > 0:

                weighted_coupon = (
                    (
                        temp["Coupon_Val"]
                        *
                        temp["Outstanding_Crore"]
                    ).sum()
                    /
                    total_outstanding
                )

            else:

                weighted_coupon = 0.0

            result["Coupon"] = float(
                weighted_coupon
            )

        else:

            result["Coupon"] = None

    return latest_date, result


# ============================================================
# 2. MARKET SUMMARY
# ============================================================

st.markdown("---")

st.markdown("### 📊 Market Summary")

summary_col1, summary_col2 = st.columns(2)


# ============================================================
# T-BILL SUMMARY
# ============================================================

with summary_col1:

    st.markdown("#### 📉 Treasury Bills")

    bill_summary = calculate_summary(
        df_bills,
        include_coupon=False
    )

    if bill_summary is not None:

        latest_date, values = bill_summary

        st.caption(
            f"As of {latest_date}"
        )

        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric(
                "ISINs",
                f"{values['Count']:,}"
            )

        with c2:

            st.metric(
                "Outstanding",
                f"৳{values['Amount']:,.2f} Cr"
            )

        with c3:

            st.metric(
                "Wtd. Yield",
                f"{values['Yield']:.2f}%"
            )

    else:

        st.info(
            "No T-Bill data in this range."
        )


# ============================================================
# BOND / FRTB SUMMARY
# ============================================================

with summary_col2:

    st.markdown(
        "#### 📈 Treasury Bonds & FRTBs"
    )

    bond_summary = calculate_summary(
        df_securities,
        include_coupon=True
    )

    if bond_summary is not None:

        latest_date, values = bond_summary

        st.caption(
            f"As of {latest_date}"
        )

        c1, c2, c3, c4 = st.columns(4)

        with c1:

            st.metric(
                "ISINs",
                f"{values['Count']:,}"
            )

        with c2:

            st.metric(
                "Outstanding",
                f"৳{values['Amount']:,.2f} Cr"
            )

        with c3:

            st.metric(
                "Wtd. Yield",
                f"{values['Yield']:.2f}%"
            )

        with c4:

            coupon = values.get(
                "Coupon"
            )

            if coupon is None:

                st.metric(
                    "Wtd. Coupon",
                    "N/A"
                )

            else:

                st.metric(
                    "Wtd. Coupon",
                    f"{coupon:.2f}%"
                )

    else:

        st.info(
            "No Bond/FRTB data in this range."
        )


# ============================================================
# 3. MATURITY SNAPSHOT
# ============================================================

st.markdown("---")

st.markdown(
    "### ⏰ Maturity Snapshot — Next 30 Days"
)


mat_col1, mat_col2 = st.columns(2)


# ============================================================
# T-BILL MATURITY
# ============================================================

with mat_col1:

    st.markdown("#### 📉 T-Bills")

    st.caption(
        f"From latest available snapshot: {bills_anchor}"
    )

    maturity_metric_col1, maturity_metric_col2 = st.columns(2)

    with maturity_metric_col1:

        st.metric(
            "Maturing Amount",
            f"৳{bills_maturing_crore:,.2f} Cr"
        )

    with maturity_metric_col2:

        st.metric(
            "ISINs",
            f"{bills_maturing_count:,}"
        )

    if not bills_maturing.empty:

        st.dataframe(
            bills_maturing,
            use_container_width=True,
            hide_index=True,
            height=220
        )

    else:

        st.info(
            "No T-Bill ISINs maturing "
            "in the next 30 days."
        )


# ============================================================
# BOND / FRTB MATURITY
# ============================================================

with mat_col2:

    st.markdown(
        "#### 📈 Bonds / FRTBs"
    )

    st.caption(
        f"From latest available snapshot: {bonds_anchor}"
    )

    maturity_metric_col1, maturity_metric_col2 = st.columns(2)

    with maturity_metric_col1:

        st.metric(
            "Maturing Amount",
            f"৳{bonds_maturing_crore:,.2f} Cr"
        )

    with maturity_metric_col2:

        st.metric(
            "ISINs",
            f"{bonds_maturing_count:,}"
        )

    if not bonds_maturing.empty:

        st.dataframe(
            bonds_maturing,
            use_container_width=True,
            hide_index=True,
            height=220
        )

    else:

        st.info(
            "No Bond/FRTB ISINs maturing "
            "in the next 30 days."
        )


# ============================================================
# 4. DETAIL DATA
# ============================================================

st.markdown("---")

st.markdown("### 📋 Detailed Data")


tab1, tab2 = st.tabs(
    [
        "📉 Treasury Bills",
        "📈 Bonds & FRTBs"
    ]
)


# ============================================================
# T-BILL DETAIL
# ============================================================

with tab1:

    range_label = (
        f"{bill_start} to {bill_end}"
        if bill_start and bill_end
        else "N/A"
    )

    st.subheader(
        f"Treasury Bills — {range_label}"
    )

    if not df_bills.empty:

        display_bills = remove_id_columns(
            df_bills
        )

        st.dataframe(
            display_bills,
            use_container_width=True,
            hide_index=True,
            height=500
        )

        excel_data = to_excel_bytes(
            df_bills,
            "T-Bills"
        )

        if excel_data is not None:

            st.download_button(
                label="⬇️ Download T-Bills (Excel)",
                data=excel_data,
                file_name=(
                    f"tbills_"
                    f"{bill_start}_to_"
                    f"{bill_end}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                key="download_bills"
            )

    else:

        st.info(
            "No T-Bill records available "
            "for this range."
        )


# ============================================================
# BOND / FRTB DETAIL
# ============================================================

with tab2:

    range_label = (
        f"{bond_start} to {bond_end}"
        if bond_start and bond_end
        else "N/A"
    )

    st.subheader(
        f"Bonds & FRTBs — {range_label}"
    )

    if not df_securities.empty:

        display_securities = remove_id_columns(
            df_securities
        )

        st.dataframe(
            display_securities,
            use_container_width=True,
            hide_index=True,
            height=500
        )

        excel_data = to_excel_bytes(
            df_securities,
            "Bonds_FRTB"
        )

        if excel_data is not None:

            st.download_button(
                label="⬇️ Download Bonds/FRTBs (Excel)",
                data=excel_data,
                file_name=(
                    f"bonds_frtb_"
                    f"{bond_start}_to_"
                    f"{bond_end}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                key="download_bonds"
            )

    else:

        st.info(
            "No Bond or FRTB records available "
            "for this range."
        )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "GSOM Treasury & Securities Dashboard • "
    "Data displayed from the latest available snapshots "
    "within the selected date ranges."
)
