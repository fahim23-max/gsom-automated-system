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

st.markdown("""
<style>

.stApp {
    background-color: #f8fafc !important;
}

.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
}

/* ----------------------------------------------------------
   Headers
---------------------------------------------------------- */

.section-title {
    color: #0f172a;
    font-weight: 800;
    font-size: 1.35rem;
    margin-top: 12px;
    margin-bottom: 12px;
}

/* ----------------------------------------------------------
   KPI CARDS
---------------------------------------------------------- */

.kpi-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    padding: 16px 18px !important;
    min-height: 125px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.05) !important;
}

.kpi-label {
    color: #64748b !important;
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.kpi-value {
    color: #0f172a !important;
    font-size: 1.65rem !important;
    font-weight: 800 !important;
    margin-top: 5px;
}

.kpi-sub {
    color: #64748b !important;
    font-size: 0.78rem !important;
    margin-top: 5px;
}

/* ----------------------------------------------------------
   SUMMARY TABLE
---------------------------------------------------------- */

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
    font-size: 0.90rem;
}

.summary-table td {
    text-align: center;
    padding: 12px;
    border: 1px solid #e2e8f0;
    font-size: 1.05rem;
    font-weight: 600;
    color: #0f172a;
}

/* ----------------------------------------------------------
   CATEGORY HEADERS
---------------------------------------------------------- */

.bill-header,
.bond-header {
    font-weight: bold;
    font-size: 1.15rem;
    margin-bottom: 4px;
    text-align: center;
}

.bill-header {
    color: #2563eb;
}

.bond-header {
    color: #0d9488;
}

/* ----------------------------------------------------------
   MATURITY CARDS
---------------------------------------------------------- */

.custom-metric-card {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    padding: 18px 20px !important;
    text-align: center !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    margin-bottom: 10px !important;
}

.custom-metric-label {
    font-size: 0.9rem !important;
    color: #64748b !important;
    font-weight: 600 !important;
}

.custom-metric-value {
    font-size: 1.6rem !important;
    color: #0f172a !important;
    font-weight: 700 !important;
    margin-top: 5px;
}

.custom-metric-delta {
    font-size: 0.85rem !important;
    color: #475569 !important;
    background-color: #f1f5f9 !important;
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
}

/* ----------------------------------------------------------
   MATURITY LADDER
---------------------------------------------------------- */

.ladder-row {
    margin-bottom: 10px;
}

.ladder-label {
    font-size: 0.82rem;
    font-weight: 600;
    color: #475569;
    margin-bottom: 3px;
}

.ladder-bar-bg {
    width: 100%;
    height: 22px;
    background: #e2e8f0;
    border-radius: 5px;
    overflow: hidden;
}

.ladder-bar {
    height: 22px;
    border-radius: 5px;
}

.ladder-value {
    font-size: 0.78rem;
    color: #475569;
    margin-top: 2px;
}

/* ----------------------------------------------------------
   TOP TABLE
---------------------------------------------------------- */

.top-table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 8px;
    overflow: hidden;
}

.top-table th {
    background: #f1f5f9;
    padding: 8px;
    border: 1px solid #e2e8f0;
    color: #334155;
}

.top-table td {
    padding: 8px;
    border: 1px solid #e2e8f0;
    color: #0f172a;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# DATABASE CONNECTION
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
<div style="text-align:center; margin-bottom:1rem;">
    <h1 style="margin-bottom:0;">
        🏛️ GSOM Treasury &amp; Securities Dashboard
    </h1>
    <p style="color:#64748b; font-size:1.05rem; margin-top:0.25rem;">
        Live data for Government Bonds, FRTBs, and T-Bills
    </p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# DATE BOUNDS
# ============================================================

@st.cache_data(ttl=30)
def get_bill_date_bounds():
    try:
        df = pd.read_sql(
            '''
            SELECT
                MIN("Data_Date")::TEXT,
                MAX("Data_Date")::TEXT
            FROM public.daily_bills
            ''',
            engine
        )
        return df.iloc[0, 0], df.iloc[0, 1]

    except Exception as e:
        st.error(f"Error fetching T-Bill date range: {e}")
        return None, None


@st.cache_data(ttl=30)
def get_security_date_bounds():
    try:
        df = pd.read_sql(
            '''
            SELECT
                MIN("Data_Date")::TEXT,
                MAX("Data_Date")::TEXT
            FROM public.daily_securities
            ''',
            engine
        )
        return df.iloc[0, 0], df.iloc[0, 1]

    except Exception as e:
        st.error(f"Error fetching Bond/FRTB date range: {e}")
        return None, None


bill_min, bill_max = get_bill_date_bounds()
sec_min, sec_max = get_security_date_bounds()

if not bill_min and not sec_min:
    st.warning(
        "No data found in the database. "
        "Please check your tables or run scrapers."
    )
    st.stop()


def to_date(s):
    return pd.to_datetime(s).date() if s else None


def default_range(min_s, max_s, lookback_days=30):
    mn = to_date(min_s)
    mx = to_date(max_s)

    if mn is None or mx is None:
        return None, None

    start = max(
        mn,
        mx - timedelta(days=lookback_days)
    )

    return start, mx


# ============================================================
# DATE RANGE PICKERS
# ============================================================

st.markdown("#### 🔎 Select Date Range")

range_col1, range_col2 = st.columns(2)

with range_col1:

    if bill_min:

        b_start_default, b_end_default = default_range(
            bill_min,
            bill_max
        )

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

        s_start_default, s_end_default = default_range(
            sec_min,
            sec_max
        )

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


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=30)
def load_bills_range(start_d, end_d):

    if not start_d or not end_d:
        return pd.DataFrame()

    q = text("""
        SELECT *
        FROM public.daily_bills
        WHERE "Data_Date" BETWEEN :s AND :e
        ORDER BY "Data_Date" DESC
    """)

    return pd.read_sql(
        q,
        engine,
        params={
            "s": str(start_d),
            "e": str(end_d)
        }
    )


@st.cache_data(ttl=30)
def load_securities_range(start_d, end_d):

    if not start_d or not end_d:
        return pd.DataFrame()

    q = text("""
        SELECT *
        FROM public.daily_securities
        WHERE "Data_Date" BETWEEN :s AND :e
        ORDER BY "Data_Date" DESC
    """)

    return pd.read_sql(
        q,
        engine,
        params={
            "s": str(start_d),
            "e": str(end_d)
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
# COMMON DATA FUNCTIONS
# ============================================================

def numeric_column(df, column):

    if column not in df.columns:
        return pd.Series(
            0.0,
            index=df.index
        )

    return pd.to_numeric(
        df[column]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0)


def prepare_snapshot(df):

    if df.empty or "Data_Date" not in df.columns:
        return pd.DataFrame(), None

    temp = df.copy()

    temp["Data_Date"] = pd.to_datetime(
        temp["Data_Date"],
        errors="coerce"
    )

    latest = temp["Data_Date"].max()

    snapshot = temp[
        temp["Data_Date"] == latest
    ].copy()

    if "ISIN" in snapshot.columns:
        snapshot = snapshot.drop_duplicates(
            subset="ISIN"
        )

    return snapshot, latest


def get_outstanding_crore(df):

    if "Outstanding BDT (in Mill)" not in df.columns:
        return pd.Series(0.0, index=df.index)

    return numeric_column(
        df,
        "Outstanding BDT (in Mill)"
    ) / 10.0


def get_yield(df):

    if "Market Yield" not in df.columns:
        return pd.Series(0.0, index=df.index)

    return numeric_column(
        df,
        "Market Yield"
    )


# ============================================================
# PORTFOLIO METRICS
# ============================================================

def calculate_portfolio_metrics(df):

    snapshot, latest = prepare_snapshot(df)

    if snapshot.empty:

        return {
            "latest": None,
            "count": 0,
            "outstanding": 0.0,
            "weighted_yield": 0.0
        }

    snapshot["Outstanding_Crore"] = get_outstanding_crore(
        snapshot
    )

    snapshot["Yield_Val"] = get_yield(
        snapshot
    )

    total = snapshot["Outstanding_Crore"].sum()

    if total > 0:

        weighted_yield = (
            snapshot["Yield_Val"]
            * snapshot["Outstanding_Crore"]
        ).sum() / total

    else:
        weighted_yield = 0.0

    count = (
        snapshot["ISIN"].nunique()
        if "ISIN" in snapshot.columns
        else len(snapshot)
    )

    return {
        "latest": latest,
        "count": int(count),
        "outstanding": float(total),
        "weighted_yield": float(weighted_yield)
    }


# ============================================================
# DAILY CHANGE
# ============================================================

def calculate_daily_change(df):

    if df.empty or "Data_Date" not in df.columns:
        return 0.0, 0.0, None

    temp = df.copy()

    temp["Data_Date"] = pd.to_datetime(
        temp["Data_Date"],
        errors="coerce"
    )

    dates = sorted(
        temp["Data_Date"].dropna().unique()
    )

    if len(dates) < 2:
        return 0.0, 0.0, None

    latest_date = dates[-1]
    previous_date = dates[-2]

    latest = temp[
        temp["Data_Date"] == latest_date
    ].copy()

    previous = temp[
        temp["Data_Date"] == previous_date
    ].copy()

    if "ISIN" in latest.columns:
        latest = latest.drop_duplicates("ISIN")

    if "ISIN" in previous.columns:
        previous = previous.drop_duplicates("ISIN")

    latest_outstanding = get_outstanding_crore(
        latest
    ).sum()

    previous_outstanding = get_outstanding_crore(
        previous
    ).sum()

    outstanding_change = (
        latest_outstanding
        - previous_outstanding
    )

    latest_yield = get_yield(latest)

    previous_yield = get_yield(previous)

    avg_latest = latest_yield.mean()
    avg_previous = previous_yield.mean()

    yield_change = avg_latest - avg_previous

    return (
        float(outstanding_change),
        float(yield_change),
        previous_date
    )


# ============================================================
# MATURITY BUCKETS
# ============================================================

MATURITY_BUCKETS = [
    ("0–7 Days", 0, 7),
    ("8–30 Days", 8, 30),
    ("31–90 Days", 31, 90),
    ("91–180 Days", 91, 180),
    ("181–365 Days", 181, 365),
    ("1–3 Years", 366, 1095),
    ("3+ Years", 1096, 99999),
]


def calculate_maturity_buckets(df):

    snapshot, latest = prepare_snapshot(df)

    results = {
        name: 0.0
        for name, _, _ in MATURITY_BUCKETS
    }

    if snapshot.empty:
        return results

    if "Maturity/ Expiry Date" not in snapshot.columns:
        return results

    snapshot["Maturity_Date"] = pd.to_datetime(
        snapshot["Maturity/ Expiry Date"],
        errors="coerce"
    )

    snapshot["Outstanding_Crore"] = get_outstanding_crore(
        snapshot
    )

    base = pd.Timestamp(latest)

    snapshot["Days_To_Maturity"] = (
        snapshot["Maturity_Date"] - base
    ).dt.days

    for name, min_days, max_days in MATURITY_BUCKETS:

        mask = (
            (snapshot["Days_To_Maturity"] >= min_days)
            &
            (snapshot["Days_To_Maturity"] <= max_days)
        )

        results[name] = float(
            snapshot.loc[
                mask,
                "Outstanding_Crore"
            ].sum()
        )

    return results


# ============================================================
# MATURITY DETAIL
# ============================================================

def compute_maturity_detail(df, days=30):

    if (
        df.empty
        or "Maturity/ Expiry Date" not in df.columns
        or "Data_Date" not in df.columns
    ):
        return pd.DataFrame(), 0.0, 0

    latest_date = df["Data_Date"].max()

    snapshot = df[
        df["Data_Date"] == latest_date
    ].copy()

    if "ISIN" in snapshot.columns:
        snapshot = snapshot.drop_duplicates(
            subset="ISIN"
        )

    base_dt = pd.to_datetime(
        latest_date,
        errors="coerce"
    )

    mat_dt = pd.to_datetime(
        snapshot["Maturity/ Expiry Date"],
        errors="coerce"
    )

    mask = (
        (mat_dt >= base_dt)
        &
        (
            mat_dt
            <= base_dt + pd.Timedelta(days=days)
        )
    )

    maturing = snapshot[mask].copy()

    if maturing.empty:
        return maturing, 0.0, 0

    crore = get_outstanding_crore(
        maturing
    )

    maturing["_mat_sort"] = pd.to_datetime(
        maturing["Maturity/ Expiry Date"],
        errors="coerce"
    )

    maturing = (
        maturing
        .sort_values("_mat_sort")
        .drop(columns="_mat_sort")
    )

    cols_to_drop = [
        col
        for col in ["id", "ID", "Id", "Data_Date"]
        if col in maturing.columns
    ]

    maturing = maturing.drop(
        columns=cols_to_drop,
        errors="ignore"
    )

    sl_col = next(
        (
            c for c in maturing.columns
            if c.lower()
            in [
                "sl. no.",
                "sl. no",
                "sl_no",
                "sl no"
            ]
        ),
        None
    )

    if sl_col:

        maturing[sl_col] = range(
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

    return (
        maturing,
        float(crore.sum()),
        int(
            maturing["ISIN"].nunique()
            if "ISIN" in maturing.columns
            else len(maturing)
        )
    )


# ============================================================
# TOP SECURITIES
# ============================================================

def get_top_securities(df, mode="yield", limit=10):

    snapshot, latest = prepare_snapshot(df)

    if snapshot.empty:
        return pd.DataFrame()

    snapshot["Outstanding_Crore"] = get_outstanding_crore(
        snapshot
    )

    snapshot["Yield_Val"] = get_yield(
        snapshot
    )

    if mode == "yield":

        result = snapshot.sort_values(
            "Yield_Val",
            ascending=False
        ).head(limit)

    else:

        result = snapshot.sort_values(
            "Outstanding_Crore",
            ascending=False
        ).head(limit)

    display_cols = []

    for col in [
        "ISIN",
        "Securities Type",
        "Maturity/ Expiry Date"
    ]:

        if col in result.columns:
            display_cols.append(col)

    display_cols += [
        "Outstanding_Crore",
        "Yield_Val"
    ]

    result = result[
        display_cols
    ].copy()

    result.rename(
        columns={
            "Outstanding_Crore":
                "Outstanding (BDT Cr)",
            "Yield_Val":
                "Market Yield (%)"
        },
        inplace=True
    )

    if "Maturity/ Expiry Date" in result.columns:

        result["Maturity/ Expiry Date"] = pd.to_datetime(
            result["Maturity/ Expiry Date"],
            errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    return result


# ============================================================
# KPI CARD
# ============================================================

def render_kpi(
    label,
    value,
    subtitle="",
    color="#2563eb"
):

    st.markdown(
        f"""
        <div class="kpi-card"
             style="border-top:4px solid {color} !important;">

            <div class="kpi-label">
                {label}
            </div>

            <div class="kpi-value">
                {value}
            </div>

            <div class="kpi-sub">
                {subtitle}
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# CALCULATE MAIN METRICS
# ============================================================

bill_metrics = calculate_portfolio_metrics(
    df_bills
)

bond_metrics = calculate_portfolio_metrics(
    df_securities
)

bill_change, bill_yield_change, _ = calculate_daily_change(
    df_bills
)

bond_change, bond_yield_change, _ = calculate_daily_change(
    df_securities
)

bill_buckets = calculate_maturity_buckets(
    df_bills
)

bond_buckets = calculate_maturity_buckets(
    df_securities
)

bills_maturing, bills_maturing_crore, bills_maturing_count = (
    compute_maturity_detail(df_bills)
)

bonds_maturing, bonds_maturing_crore, bonds_maturing_count = (
    compute_maturity_detail(df_securities)
)

bills_anchor = (
    bill_metrics["latest"]
    if bill_metrics["latest"] is not None
    else "N/A"
)

bonds_anchor = (
    bond_metrics["latest"]
    if bond_metrics["latest"] is not None
    else "N/A"
)


# ============================================================
# 1. PORTFOLIO KPI SECTION
# ============================================================

st.markdown(
    '<div class="section-title">📌 Portfolio KPIs</div>',
    unsafe_allow_html=True
)

k1, k2, k3, k4 = st.columns(4)

combined_outstanding = (
    bill_metrics["outstanding"]
    + bond_metrics["outstanding"]
)

combined_count = (
    bill_metrics["count"]
    + bond_metrics["count"]
)

combined_yield = 0.0

if combined_outstanding > 0:

    combined_yield = (
        (
            bill_metrics["weighted_yield"]
            * bill_metrics["outstanding"]
        )
        +
        (
            bond_metrics["weighted_yield"]
            * bond_metrics["outstanding"]
        )
    ) / combined_outstanding


with k1:

    render_kpi(
        "Total Outstanding",
        f"৳{combined_outstanding:,.2f} Cr",
        "T-Bills + Bonds/FRTBs",
        "#2563eb"
    )


with k2:

    render_kpi(
        "Total ISINs",
        f"{combined_count:,}",
        "Latest available snapshot",
        "#7c3aed"
    )


with k3:

    render_kpi(
        "Portfolio Wtd. Yield",
        f"{combined_yield:.2f}%",
        "Outstanding-weighted",
        "#0d9488"
    )


with k4:

    total_maturing_30 = (
        bills_maturing_crore
        + bonds_maturing_crore
    )

    render_kpi(
        "Maturing in 30 Days",
        f"৳{total_maturing_30:,.2f} Cr",
        f"{bills_maturing_count + bonds_maturing_count:,} ISINs",
        "#dc2626"
    )


# ============================================================
# 2. MARKET SUMMARY
# ============================================================

st.markdown(
    '<div class="section-title">📊 Market Summary</div>',
    unsafe_allow_html=True
)

sum_col1, sum_col2 = st.columns(2)


def render_market_summary(
    title,
    metrics,
    change,
    yield_change,
    color
):

    st.markdown(
        f"""
        <div class="{'bill-header' if color == '#2563eb' else 'bond-header'}">
            {title}
            <span style="
                font-size:0.82rem;
                color:#64748b;
                font-weight:normal;
            ">
                (as of {metrics["latest"]})
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    outstanding_delta = (
        f"+৳{change:,.2f} Cr"
        if change > 0
        else f"-৳{abs(change):,.2f} Cr"
        if change < 0
        else "No change"
    )

    yield_delta = (
        f"+{yield_change:.2f}%"
        if yield_change > 0
        else f"{yield_change:.2f}%"
        if yield_change < 0
        else "No change"
    )

    st.markdown(
        f"""
        <table class="summary-table">
            <thead>
                <tr>
                    <th>ISINs</th>
                    <th>Outstanding</th>
                    <th>Wtd. Avg Yield</th>
                    <th>Daily Change</th>
                </tr>
            </thead>

            <tbody>
                <tr>
                    <td>{metrics["count"]:,}</td>
                    <td>৳{metrics["outstanding"]:,.2f} Cr</td>
                    <td>{metrics["weighted_yield"]:.2f}%</td>
                    <td>{outstanding_delta}</td>
                </tr>
            </tbody>
        </table>

        <div style="
            text-align:center;
            color:#64748b;
            font-size:0.82rem;
            margin-top:-5px;
            margin-bottom:12px;
        ">
            Yield change vs previous available date:
            <b>{yield_delta}</b>
        </div>
        """,
        unsafe_allow_html=True
    )


with sum_col1:

    render_market_summary(
        "Treasury Bills",
        bill_metrics,
        bill_change,
        bill_yield_change,
        "#2563eb"
    )


with sum_col2:

    render_market_summary(
        "Treasury Bonds & FRTBs",
        bond_metrics,
        bond_change,
        bond_yield_change,
        "#0d9488"
    )


st.markdown(
    "<hr style='margin:18px 0; border:0; "
    "border-top:1px solid #e2e8f0;'>",
    unsafe_allow_html=True
)


# ============================================================
# 3. MATURITY LADDER
# ============================================================

st.markdown(
    '<div class="section-title">📅 Maturity Profile</div>',
    unsafe_allow_html=True
)

ladder_col1, ladder_col2 = st.columns(2)


def render_maturity_ladder(
    title,
    buckets,
    color
):

    st.markdown(
        f"##### {title}"
    )

    max_value = max(
        buckets.values()
    ) if buckets else 0

    for name, value in buckets.items():

        if max_value > 0:

            width = (
                value / max_value
            ) * 100

        else:
            width = 0

        st.markdown(
            f"""
            <div class="ladder-row">

                <div class="ladder-label">
                    {name}
                </div>

                <div class="ladder-bar-bg">
                    <div
                        class="ladder-bar"
                        style="
                            width:{width:.1f}%;
                            background:{color};
                        ">
                    </div>
                </div>

                <div class="ladder-value">
                    ৳{value:,.2f} Cr
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )


with ladder_col1:

    render_maturity_ladder(
        "📉 Treasury Bills",
        bill_buckets,
        "#2563eb"
    )


with ladder_col2:

    render_maturity_ladder(
        "📈 Bonds & FRTBs",
        bond_buckets,
        "#0d9488"
    )


st.markdown(
    "<hr style='margin:18px 0; border:0; "
    "border-top:1px solid #e2e8f0;'>",
    unsafe_allow_html=True
)


# ============================================================
# 4. NEXT 30 DAYS MATURITY
# ============================================================

st.markdown(
    '<div class="section-title">⏰ Maturity Snapshot — Next 30 Days</div>',
    unsafe_allow_html=True
)

mat_col1, mat_col2 = st.columns(2)


def render_maturity_snapshot(
    title,
    anchor,
    crore,
    count,
    df,
    color
):

    st.markdown(
        f"""
        <div class="custom-metric-card"
             style="border-top:4px solid {color} !important;">

            <div class="custom-metric-label">
                {title}
                <span style="font-weight:normal;">
                    (from {anchor})
                </span>
            </div>

            <div class="custom-metric-value">
                ৳ {crore:,.2f} Cr
            </div>

            <div class="custom-metric-delta">
                📌 {count} ISINs
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    if not df.empty:

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=200
        )

    else:

        st.caption(
            f"No {title} maturing in the next 30 days."
        )


with mat_col1:

    render_maturity_snapshot(
        "T-Bills Maturing",
        bills_anchor,
        bills_maturing_crore,
        bills_maturing_count,
        bills_maturing,
        "#2563eb"
    )


with mat_col2:

    render_maturity_snapshot(
        "Bonds/FRTBs Maturing",
        bonds_anchor,
        bonds_maturing_crore,
        bonds_maturing_count,
        bonds_maturing,
        "#0d9488"
    )


st.markdown(
    "<hr style='margin:18px 0; border:0; "
    "border-top:1px solid #e2e8f0;'>",
    unsafe_allow_html=True
)


# ============================================================
# 5. TOP SECURITIES
# ============================================================

st.markdown(
    '<div class="section-title">🏆 Security Concentration & Yield</div>',
    unsafe_allow_html=True
)

top_col1, top_col2 = st.columns(2)


with top_col1:

    st.markdown("##### 🔥 Highest Yielding Securities")

    top_yield_bills = get_top_securities(
        df_bills,
        mode="yield",
        limit=5
    )

    top_yield_bonds = get_top_securities(
        df_securities,
        mode="yield",
        limit=5
    )

    if not top_yield_bills.empty:

        st.caption("T-Bills")

        st.dataframe(
            top_yield_bills,
            use_container_width=True,
            hide_index=True
        )

    if not top_yield_bonds.empty:

        st.caption("Bonds / FRTBs")

        st.dataframe(
            top_yield_bonds,
            use_container_width=True,
            hide_index=True
        )

    if (
        top_yield_bills.empty
        and top_yield_bonds.empty
    ):

        st.info("No securities available.")


with top_col2:

    st.markdown("##### 💰 Largest Securities by Outstanding")

    top_size_bills = get_top_securities(
        df_bills,
        mode="outstanding",
        limit=5
    )

    top_size_bonds = get_top_securities(
        df_securities,
        mode="outstanding",
        limit=5
    )

    if not top_size_bills.empty:

        st.caption("T-Bills")

        st.dataframe(
            top_size_bills,
            use_container_width=True,
            hide_index=True
        )

    if not top_size_bonds.empty:

        st.caption("Bonds / FRTBs")

        st.dataframe(
            top_size_bonds,
            use_container_width=True,
            hide_index=True
        )

    if (
        top_size_bills.empty
        and top_size_bonds.empty
    ):

        st.info("No securities available.")


st.markdown(
    "<hr style='margin:18px 0; border:0; "
    "border-top:1px solid #e2e8f0;'>",
    unsafe_allow_html=True
)


# ============================================================
# 6. DETAIL TABS
# ============================================================

tab1, tab2 = st.tabs(
    [
        "📉 Treasury Bills",
        "📈 Bonds & FRTBs"
    ]
)


# ============================================================
# EXCEL EXPORT
# ============================================================

def to_excel_bytes(df, sheet_name):

    buffer = io.BytesIO()

    export_df = df.copy()

    # Remove database IDs
    export_df = export_df.drop(
        columns=[
            c for c in ["id", "ID", "Id"]
            if c in export_df.columns
        ],
        errors="ignore"
    )

    # Remove timezone from datetime columns
    for col in export_df.columns:

        try:

            if (
                pd.api.types.is_datetime64tz_dtype(
                    export_df[col]
                )
            ):

                export_df[col] = (
                    export_df[col]
                    .dt.tz_localize(None)
                )

        except Exception:
            pass

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        export_df.to_excel(
            writer,
            index=False,
            sheet_name=sheet_name[:31]
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# T-BILL TAB
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

        display_bills = df_bills.drop(
            columns=[
                c for c in ["id", "ID", "Id"]
                if c in df_bills.columns
            ],
            errors="ignore"
        )

        st.dataframe(
            display_bills,
            use_container_width=True
        )

        try:

            excel_bills = to_excel_bytes(
                df_bills,
                "T-Bills"
            )

            st.download_button(
                "⬇️ Download T-Bills (Excel)",
                data=excel_bills,
                file_name=(
                    f"tbills_{bill_start}"
                    f"_to_{bill_end}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                )
            )

        except Exception as e:

            st.error(
                f"Excel export failed: {e}"
            )

    else:

        st.info(
            "No T-Bill records available "
            "for this range."
        )


# ============================================================
# BOND / FRTB TAB
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

        display_sec = df_securities.drop(
            columns=[
                c for c in ["id", "ID", "Id"]
                if c in df_securities.columns
            ],
            errors="ignore"
        )

        st.dataframe(
            display_sec,
            use_container_width=True
        )

        try:

            excel_bonds = to_excel_bytes(
                df_securities,
                "Bonds_FRTB"
            )

            st.download_button(
                "⬇️ Download Bonds/FRTBs (Excel)",
                data=excel_bonds,
                file_name=(
                    f"bonds_frtb_{bond_start}"
                    f"_to_{bond_end}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                )
            )

        except Exception as e:

            st.error(
                f"Excel export failed: {e}"
            )

    else:

        st.info(
            "No Bond or FRTB records available "
            "for this range."
        )
