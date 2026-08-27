import os
import io
from datetime import timedelta

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="GSOM Treasury Dashboard",
    page_icon="📈",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>

.stApp {
    background-color: #f8fafc;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
}

/* Main title */
.dashboard-title {
    text-align: center;
    margin-bottom: 1rem;
}

.dashboard-title h1 {
    margin-bottom: 0;
    color: #0f172a;
}

.dashboard-title p {
    color: #64748b;
    font-size: 1.05rem;
    margin-top: 0.25rem;
}


/* KPI section */
.kpi-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    margin-top: 10px;
    margin-bottom: 12px;
}


/* Metric cards */
div[data-testid="stMetric"] {
    background-color: white;
    border: 1px solid #e2e8f0;
    padding: 18px 20px;
    border-radius: 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05);
}

div[data-testid="stMetricLabel"] {
    color: #64748b !important;
    font-weight: 600;
}

div[data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-weight: 700;
}


/* Section headings */
.section-heading {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    margin-top: 10px;
    margin-bottom: 12px;
}


/* Summary boxes */
.summary-box {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
}

.summary-box-title {
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 8px;
}

.bill-title {
    color: #2563eb;
}

.bond-title {
    color: #0d9488;
}


/* Horizontal divider */
.dashboard-divider {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 22px 0;
}


/* Mobile */
@media (max-width: 768px) {

    div[data-testid="stMetric"] {
        padding: 12px;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }

}

</style>
""", unsafe_allow_html=True)


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    st.error("DATABASE_URL environment variable is not configured.")
    st.stop()

engine = create_engine(
    DATABASE_URL,
    connect_args={"prepare_threshold": None}
)


# ============================================================
# TITLE
# ============================================================

st.markdown("""
<div class="dashboard-title">
    <h1>🏛️ GSOM Treasury & Securities Dashboard</h1>
    <p>Live data for Government Bonds, FRTBs, and T-Bills</p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# HELPERS
# ============================================================

def money_to_crore(series):
    """
    Convert Outstanding BDT from Million BDT to Crore BDT.

    1 Crore = 10 Million BDT

    Therefore:
        Million BDT / 10 = Crore BDT
    """
    return (
        pd.to_numeric(
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("৳", "", regex=False)
            .str.strip(),
            errors="coerce"
        )
        .fillna(0)
        / 10.0
    )


def yield_to_number(series):
    """Convert yield strings such as '9.25%' to 9.25."""
    return pd.to_numeric(
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce"
    )


def normalize_date_column(df):
    """Make Data_Date a clean datetime column."""
    if df.empty or "Data_Date" not in df.columns:
        return df

    df = df.copy()
    df["Data_Date"] = pd.to_datetime(
        df["Data_Date"],
        errors="coerce"
    )

    return df


def latest_snapshot(df):
    """
    Return the latest available date snapshot,
    deduplicated by ISIN.
    """
    if df.empty or "Data_Date" not in df.columns:
        return pd.DataFrame()

    df = normalize_date_column(df)

    latest = df["Data_Date"].max()

    if pd.isna(latest):
        return pd.DataFrame()

    snapshot = df[
        df["Data_Date"] == latest
    ].copy()

    if "ISIN" in snapshot.columns:
        snapshot = snapshot.drop_duplicates(
            subset="ISIN",
            keep="first"
        )

    return snapshot


# ============================================================
# DATE BOUNDS
# ============================================================

@st.cache_data(ttl=30)
def get_bill_date_bounds():

    try:
        q = text("""
            SELECT
                MIN("Data_Date") AS min_date,
                MAX("Data_Date") AS max_date
            FROM public.daily_bills
        """)

        df = pd.read_sql(q, engine)

        return (
            df.loc[0, "min_date"],
            df.loc[0, "max_date"]
        )

    except Exception as e:
        st.error(f"Error fetching T-Bill date range: {e}")
        return None, None


@st.cache_data(ttl=30)
def get_security_date_bounds():

    try:
        q = text("""
            SELECT
                MIN("Data_Date") AS min_date,
                MAX("Data_Date") AS max_date
            FROM public.daily_securities
        """)

        df = pd.read_sql(q, engine)

        return (
            df.loc[0, "min_date"],
            df.loc[0, "max_date"]
        )

    except Exception as e:
        st.error(f"Error fetching Bond/FRTB date range: {e}")
        return None, None


bill_min, bill_max = get_bill_date_bounds()
sec_min, sec_max = get_security_date_bounds()


if bill_min is None and sec_min is None:
    st.warning(
        "No data found in the database. "
        "Please check your tables or run the scrapers."
    )
    st.stop()


def to_date(value):

    if value is None or pd.isna(value):
        return None

    return pd.to_datetime(value).date()


def default_range(min_date, max_date, lookback_days=30):

    mn = to_date(min_date)
    mx = to_date(max_date)

    if mn is None or mx is None:
        return None, None

    start = max(
        mn,
        mx - timedelta(days=lookback_days)
    )

    return start, mx


# ============================================================
# DATE SELECTORS
# ============================================================

st.markdown(
    '<div class="section-heading">🔎 Select Date Range</div>',
    unsafe_allow_html=True
)

range_col1, range_col2 = st.columns(2)


with range_col1:

    if bill_min is not None:

        b_start_default, b_end_default = default_range(
            bill_min,
            bill_max
        )

        bill_range = st.date_input(
            "📅 T-Bill Date Range",
            value=(
                b_start_default,
                b_end_default
            ),
            min_value=to_date(bill_min),
            max_value=to_date(bill_max)
        )

    else:

        bill_range = None

        st.info("No T-Bill dates available.")


with range_col2:

    if sec_min is not None:

        s_start_default, s_end_default = default_range(
            sec_min,
            sec_max
        )

        bond_range = st.date_input(
            "📅 Bond / FRTB Date Range",
            value=(
                s_start_default,
                s_end_default
            ),
            min_value=to_date(sec_min),
            max_value=to_date(sec_max)
        )

    else:

        bond_range = None

        st.info("No Bond/FRTB dates available.")


def unpack_range(value):

    if isinstance(value, tuple) and len(value) == 2:
        return value[0], value[1]

    return None, None


bill_start, bill_end = unpack_range(bill_range)
bond_start, bond_end = unpack_range(bond_range)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=30)
def load_bills_range(start_d, end_d):

    if start_d is None or end_d is None:
        return pd.DataFrame()

    q = text("""
        SELECT *
        FROM public.daily_bills
        WHERE "Data_Date" BETWEEN :start_date AND :end_date
        ORDER BY "Data_Date" DESC
    """)

    df = pd.read_sql(
        q,
        engine,
        params={
            "start_date": str(start_d),
            "end_date": str(end_d)
        }
    )

    return normalize_date_column(df)


@st.cache_data(ttl=30)
def load_securities_range(start_d, end_d):

    if start_d is None or end_d is None:
        return pd.DataFrame()

    q = text("""
        SELECT *
        FROM public.daily_securities
        WHERE "Data_Date" BETWEEN :start_date AND :end_date
        ORDER BY "Data_Date" DESC
    """)

    df = pd.read_sql(
        q,
        engine,
        params={
            "start_date": str(start_d),
            "end_date": str(end_d)
        }
    )

    return normalize_date_column(df)


df_bills = load_bills_range(
    bill_start,
    bill_end
)

df_securities = load_securities_range(
    bond_start,
    bond_end
)


# ============================================================
# SNAPSHOTS
# ============================================================

bills_latest = latest_snapshot(df_bills)
bonds_latest = latest_snapshot(df_securities)


bills_anchor = (
    bills_latest["Data_Date"].max()
    if not bills_latest.empty
    else None
)

bonds_anchor = (
    bonds_latest["Data_Date"].max()
    if not bonds_latest.empty
    else None
)


# ============================================================
# PORTFOLIO CALCULATIONS
# ============================================================

def calculate_portfolio_metrics(bills, bonds):

    bills = bills.copy()
    bonds = bonds.copy()

    total_outstanding = 0.0
    total_isins = 0
    weighted_yield_numerator = 0.0

    # --------------------------
    # T-BILLS
    # --------------------------

    if not bills.empty:

        bills_amount = money_to_crore(
            bills["Outstanding BDT (in Mill)"]
        )

        bills["__amount_cr"] = bills_amount

        total_outstanding += bills_amount.sum()

        if "ISIN" in bills.columns:
            total_isins += bills["ISIN"].nunique()

        if "Market Yield" in bills.columns:

            bills_yield = yield_to_number(
                bills["Market Yield"]
            ).fillna(0)

            weighted_yield_numerator += (
                bills_yield * bills_amount
            ).sum()

    # --------------------------
    # BONDS / FRTBs
    # --------------------------

    if not bonds.empty:

        bonds_amount = money_to_crore(
            bonds["Outstanding BDT (in Mill)"]
        )

        bonds["__amount_cr"] = bonds_amount

        total_outstanding += bonds_amount.sum()

        if "ISIN" in bonds.columns:
            total_isins += bonds["ISIN"].nunique()

        if "Market Yield" in bonds.columns:

            bonds_yield = yield_to_number(
                bonds["Market Yield"]
            ).fillna(0)

            weighted_yield_numerator += (
                bonds_yield * bonds_amount
            ).sum()

    # --------------------------
    # WEIGHTED YIELD
    # --------------------------

    if total_outstanding > 0:

        weighted_yield = (
            weighted_yield_numerator
            / total_outstanding
        )

    else:

        weighted_yield = 0.0

    return (
        float(total_outstanding),
        int(total_isins),
        float(weighted_yield)
    )


(
    portfolio_outstanding,
    portfolio_isins,
    portfolio_yield
) = calculate_portfolio_metrics(
    bills_latest,
    bonds_latest
)


# ============================================================
# MATURITY CALCULATION
# ============================================================

def compute_maturity_detail(df, days=30):

    snapshot = latest_snapshot(df)

    if snapshot.empty:
        return (
            pd.DataFrame(),
            0.0,
            0
        )

    if "Maturity/ Expiry Date" not in snapshot.columns:
        return (
            pd.DataFrame(),
            0.0,
            0
        )

    if "Outstanding BDT (in Mill)" not in snapshot.columns:
        return (
            pd.DataFrame(),
            0.0,
            0
        )

    base_date = snapshot["Data_Date"].max()

    base_date = pd.to_datetime(
        base_date,
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
            <= base_date + pd.Timedelta(days=days)
        )
    )

    maturing = snapshot.loc[mask].copy()

    if maturing.empty:

        return (
            maturing,
            0.0,
            0
        )

    maturing["__amount_cr"] = money_to_crore(
        maturing["Outstanding BDT (in Mill)"]
    )

    total_crore = maturing["__amount_cr"].sum()

    # Sort by maturity date
    maturing["__sort_date"] = pd.to_datetime(
        maturing["Maturity/ Expiry Date"],
        errors="coerce"
    )

    maturing = maturing.sort_values(
        "__sort_date"
    )

    maturing = maturing.drop(
        columns=[
            "__sort_date",
            "__amount_cr"
        ],
        errors="ignore"
    )

    # Remove database ID
    maturing = maturing.drop(
        columns=[
            "id",
            "ID",
            "Id"
        ],
        errors="ignore"
    )

    # Remove Data_Date from maturity table
    maturing = maturing.drop(
        columns=["Data_Date"],
        errors="ignore"
    )

    # Add serial number
    existing_sl = next(
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

    if existing_sl:

        maturing[existing_sl] = range(
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


(
    bills_maturing,
    bills_maturing_crore,
    bills_maturing_count
) = compute_maturity_detail(
    df_bills
)


(
    bonds_maturing,
    bonds_maturing_crore,
    bonds_maturing_count
) = compute_maturity_detail(
    df_securities
)


total_maturing = (
    bills_maturing_crore
    + bonds_maturing_crore
)


total_maturing_isins = (
    bills_maturing_count
    + bonds_maturing_count
)


# ============================================================
# PORTFOLIO KPIs
# ============================================================

st.markdown(
    '<div class="section-heading">📌 Portfolio KPIs</div>',
    unsafe_allow_html=True
)

k1, k2, k3, k4 = st.columns(4)


with k1:

    st.metric(
        "Total Outstanding",
        f"৳{portfolio_outstanding:,.2f} Cr",
        help="Latest available T-Bill + Bond/FRTB outstanding amount."
    )


with k2:

    st.metric(
        "Total ISINs",
        f"{portfolio_isins:,}",
        help="Unique ISINs in the latest available snapshot."
    )


with k3:

    st.metric(
        "Portfolio Wtd. Yield",
        f"{portfolio_yield:.2f}%",
        help="Outstanding-weighted market yield."
    )


with k4:

    st.metric(
        "Maturing in 30 Days",
        f"৳{total_maturing:,.2f} Cr",
        help="Outstanding amount maturing within 30 days from the latest snapshot."
    )


st.caption(
    "Portfolio KPIs use the latest available snapshot within each selected date range."
)


# ============================================================
# MARKET SUMMARY
# ============================================================

st.markdown(
    '<div class="section-heading">📊 Market Summary</div>',
    unsafe_allow_html=True
)


def build_summary_row(
    name,
    snapshot
):

    if snapshot.empty:

        return {
            "Category": name,
            "ISINs": 0,
            "Outstanding (BDT Cr)": 0.0,
            "Wtd. Yield (%)": 0.0
        }

    amount = money_to_crore(
        snapshot["Outstanding BDT (in Mill)"]
    )

    total = amount.sum()

    if "Market Yield" in snapshot.columns:

        yld = yield_to_number(
            snapshot["Market Yield"]
        ).fillna(0)

        if total > 0:

            weighted_yield = (
                yld * amount
            ).sum() / total

        else:

            weighted_yield = 0

    else:

        weighted_yield = 0

    count = (
        snapshot["ISIN"].nunique()
        if "ISIN" in snapshot.columns
        else len(snapshot)
    )

    return {
        "Category": name,
        "ISINs": int(count),
        "Outstanding (BDT Cr)": round(
            float(total),
            2
        ),
        "Wtd. Yield (%)": round(
            float(weighted_yield),
            2
        )
    }


bills_summary = build_summary_row(
    "Treasury Bills",
    bills_latest
)

bonds_summary = build_summary_row(
    "Treasury Bonds & FRTBs",
    bonds_latest
)


summary_df = pd.DataFrame(
    [
        bills_summary,
        bonds_summary
    ]
)


sum1, sum2 = st.columns(2)


with sum1:

    st.markdown(
        '<div class="summary-box-title bill-title">'
        '📉 Treasury Bills'
        '</div>',
        unsafe_allow_html=True
    )

    if bills_anchor is not None:

        st.caption(
            f"As of {bills_anchor.strftime('%Y-%m-%d')}"
        )

    st.dataframe(
        pd.DataFrame([{
            "ISINs": bills_summary["ISINs"],
            "Amount (BDT Cr)": bills_summary[
                "Outstanding (BDT Cr)"
            ],
            "Wtd. Yield": (
                f'{bills_summary["Wtd. Yield (%)"]:.2f}%'
            )
        }]),
        use_container_width=True,
        hide_index=True
    )


with sum2:

    st.markdown(
        '<div class="summary-box-title bond-title">'
        '📈 Treasury Bonds & FRTBs'
        '</div>',
        unsafe_allow_html=True
    )

    if bonds_anchor is not None:

        st.caption(
            f"As of {bonds_anchor.strftime('%Y-%m-%d')}"
        )

    st.dataframe(
        pd.DataFrame([{
            "ISINs": bonds_summary["ISINs"],
            "Amount (BDT Cr)": bonds_summary[
                "Outstanding (BDT Cr)"
            ],
            "Wtd. Yield": (
                f'{bonds_summary["Wtd. Yield (%)"]:.2f}%'
            )
        }]),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# BOND COUPON METRIC
# ============================================================

def calculate_weighted_coupon(snapshot):

    if snapshot.empty:
        return None

    coupon_col = next(
        (
            c for c in snapshot.columns
            if "coupon" in c.lower()
        ),
        None
    )

    if coupon_col is None:
        return None

    amount = money_to_crore(
        snapshot["Outstanding BDT (in Mill)"]
    )

    total = amount.sum()

    if total <= 0:
        return None

    coupon = yield_to_number(
        snapshot[coupon_col]
    ).fillna(0)

    return float(
        (coupon * amount).sum()
        / total
    )


bond_coupon = calculate_weighted_coupon(
    bonds_latest
)


if bond_coupon is not None:

    st.caption(
        f"Bond/FRTB outstanding-weighted average coupon: "
        f"**{bond_coupon:.2f}%**"
    )


# ============================================================
# DIVIDER
# ============================================================

st.markdown(
    '<hr class="dashboard-divider">',
    unsafe_allow_html=True
)


# ============================================================
# MATURITY SNAPSHOT
# ============================================================

st.markdown(
    '<div class="section-heading">⏰ Maturity Snapshot — Next 30 Days</div>',
    unsafe_allow_html=True
)


mat1, mat2 = st.columns(2)


with mat1:

    st.markdown(
        "### 📉 T-Bills"
    )

    if bills_anchor is not None:

        st.caption(
            f"From latest snapshot: "
            f"{bills_anchor.strftime('%Y-%m-%d')}"
        )

    m1, m2 = st.columns(2)

    with m1:

        st.metric(
            "Maturing Amount",
            f"৳{bills_maturing_crore:,.2f} Cr"
        )

    with m2:

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
            "No T-Bill ISINs maturing in the next 30 days."
        )


with mat2:

    st.markdown(
        "### 📈 Bonds & FRTBs"
    )

    if bonds_anchor is not None:

        st.caption(
            f"From latest snapshot: "
            f"{bonds_anchor.strftime('%Y-%m-%d')}"
        )

    m1, m2 = st.columns(2)

    with m1:

        st.metric(
            "Maturing Amount",
            f"৳{bonds_maturing_crore:,.2f} Cr"
        )

    with m2:

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
            "No Bond/FRTB ISINs maturing in the next 30 days."
        )


# ============================================================
# DIVIDER
# ============================================================

st.markdown(
    '<hr class="dashboard-divider">',
    unsafe_allow_html=True
)


# ============================================================
# EXCEL EXPORT
# ============================================================

def to_excel_bytes(df, sheet_name):

    buffer = io.BytesIO()

    export_df = df.copy()

    # Excel cannot handle timezone-aware timestamps.
    for col in export_df.columns:

        try:

            if isinstance(
                export_df[col].dtype,
                pd.DatetimeTZDtype
            ):

                export_df[col] = (
                    export_df[col]
                    .dt
                    .tz_localize(None)
                )

        except Exception:
            pass

    # Remove database ID from exported data
    export_df = export_df.drop(
        columns=[
            "id",
            "ID",
            "Id"
        ],
        errors="ignore"
    )

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        export_df.to_excel(
            writer,
            index=False,
            sheet_name=sheet_name[:31]
        )

    return buffer.getvalue()


# ============================================================
# DETAIL TABS
# ============================================================

tab1, tab2 = st.tabs(
    [
        "📉 Treasury Bills",
        "📈 Bonds & FRTBs"
    ]
)


# ------------------------------------------------------------
# T-BILLS TAB
# ------------------------------------------------------------

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

        display_bills = df_bills.drop(
            columns=[
                "id",
                "ID",
                "Id"
            ],
            errors="ignore"
        )

        st.dataframe(
            display_bills,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "⬇️ Download T-Bills (Excel)",

            data=to_excel_bytes(
                df_bills,
                "T-Bills"
            ),

            file_name=(
                f"tbills_"
                f"{bill_start}_to_"
                f"{bill_end}.xlsx"
            ),

            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            )
        )

    else:

        st.info(
            "No T-Bill records available for this range."
        )


# ------------------------------------------------------------
# BONDS TAB
# ------------------------------------------------------------

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

        display_sec = df_securities.drop(
            columns=[
                "id",
                "ID",
                "Id"
            ],
            errors="ignore"
        )

        st.dataframe(
            display_sec,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "⬇️ Download Bonds/FRTBs (Excel)",

            data=to_excel_bytes(
                df_securities,
                "Bonds_FRTB"
            ),

            file_name=(
                f"bonds_frtb_"
                f"{bond_start}_to_"
                f"{bond_end}.xlsx"
            ),

            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            )
        )

    else:

        st.info(
            "No Bond/FRTB records available for this range."
        )
