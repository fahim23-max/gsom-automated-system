import os
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from playwright.sync_api import sync_playwright

TREASURY_URL = "https://www.bb.org.bd/en/index.php/monetaryactivity/treasury"
DEBUG_DIR = "debug_output"  # saved as a GitHub Actions artifact - see note at bottom of file

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL secret is missing!")

engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=12,
    max_overflow=6,
)

# NOTE: adds two columns beyond the original schema - Issue_Date (the real
# per-security auction date, since a single month can contain several
# distinct issue dates) and Standard_Devolvement_Yield (the 14th column,
# present for bonds, usually blank for T-Bills). Run this once before using
# the script, if these columns don't already exist:
#
#   ALTER TABLE public.treasury_monthly_data
#     ADD COLUMN IF NOT EXISTS "Issue_Date" TEXT,
#     ADD COLUMN IF NOT EXISTS "Standard_Devolvement_Yield" TEXT;
UPSERT_SQL = text("""
    INSERT INTO public.treasury_monthly_data
    ("Month", "Year", "ISIN", "Securities_Name", "Tenor", "Bids_Received",
     "Face_Value_Received", "Range_Yields_Received", "Bids_Accepted",
     "Face_Value_Accepted", "Sale_Value", "Range_Yields_Accepted",
     "Weighted_Avg_Price", "Cut_Off_Yield", "Data_Period",
     "Issue_Date", "Standard_Devolvement_Yield")
    VALUES (:month, :year, :isin, :name, :tenor, :bids_rec, :fv_rec,
            :range_rec, :bids_acc, :fv_acc, :sale_val, :range_acc,
            :waprice, :cutoff, :period, :issue_date, :std_devol)
    ON CONFLICT ("ISIN", "Data_Period") DO UPDATE SET
        "Face_Value_Accepted" = EXCLUDED."Face_Value_Accepted",
        "Sale_Value" = EXCLUDED."Sale_Value",
        "Cut_Off_Yield" = EXCLUDED."Cut_Off_Yield",
        "Weighted_Avg_Price" = EXCLUDED."Weighted_Avg_Price",
        "Bids_Accepted" = EXCLUDED."Bids_Accepted",
        "Issue_Date" = EXCLUDED."Issue_Date",
        "Standard_Devolvement_Yield" = EXCLUDED."Standard_Devolvement_Yield";
""")


def get_existing_periods():
    with engine.connect() as conn:
        res = conn.execute(text('SELECT DISTINCT "Data_Period" FROM public.treasury_monthly_data'))
        return set(row[0] for row in res.fetchall())


def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)


ISIN_RE = re.compile(r"^(\S+)\s*(.*)$")


def split_isin(raw):
    """'BD0929441204 (Re-issuance: 2.73 Yr.)' -> ('BD0929441204', '(Re-issuance: 2.73 Yr.)')"""
    raw = raw.strip()
    m = ISIN_RE.match(raw)
    if not m:
        return raw, ""
    return m.group(1), m.group(2).strip()


def to_float(val):
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return 0.0


def parse_treasury_table(html_text, month_str, year_str):
    """
    Confirmed table layout (14 columns, 2-row header):
      [0]  Issue date
      [1]  ISIN Number (may include a re-issuance note in parentheses)
      [2]  Remaining Maturity (aprx)
      [3]  Tenor and name
      [4]  Bids received - No of bids
      [5]  Bids received - Face value (Cr.Tk.)
      [6]  Bids received - Range of yields (%)
      [7]  Bids accepted - No of bids
      [8]  Bids accepted - Face value (Cr.Tk.)
      [9]  Bids accepted - Sale value (Cr.Tk.)
      [10] Bids accepted - Range of yields (%)
      [11] Bids accepted - Weighted average Price (taka)
      [12] Bids accepted - Cut off yield (%)
      [13] Bids accepted - Standard/Devolvement Yield (%) (often blank for T-Bills)
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    table = soup.find("table")
    if not table:
        return []

    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

    records = []
    period_tag = f"{month_str}-{year_str}"

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 14:
            continue

        isin_clean, reissue_note = split_isin(cols[1])
        tenor_remaining = cols[2]
        tenor_name = cols[3]
        # Keep the re-issuance note visible in the name field, since it's
        # genuinely useful context, without letting it corrupt the ISIN
        # used for ON CONFLICT matching.
        display_name = f"{tenor_name} {reissue_note}".strip() if reissue_note else tenor_name

        records.append({
            "month": month_str,
            "year": int(year_str),
            "isin": isin_clean,
            "name": display_name,
            "tenor": tenor_remaining,
            "bids_rec": cols[4],
            "fv_rec": to_float(cols[5]),
            "range_rec": cols[6],
            "bids_acc": cols[7],
            "fv_acc": to_float(cols[8]),
            "sale_val": to_float(cols[9]),
            "range_acc": cols[10],
            "waprice": to_float(cols[11]),
            "cutoff": to_float(cols[12]),
            "period": period_tag,
            "issue_date": cols[0],
            "std_devol": cols[13] if len(cols) > 13 else "",
        })
    return records


def main():
    existing_periods = get_existing_periods()
    print(f"Found {len(existing_periods)} existing periods in DB. Skipping duplicates...", flush=True)

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_date = datetime.now()
    target_tasks = []
    seen = set()

    # Calendar-accurate month stepping (not a 30-day approximation) - a
    # day-based approximation drifts noticeably over 240 months and would
    # start skipping/duplicating months by the time it reaches ~2006.
    from dateutil.relativedelta import relativedelta

    for i in range(240):  # past 20 years
        d = current_date - relativedelta(months=i)
        m_str = months[d.month - 1]
        y_str = str(d.year)
        period_key = f"{m_str}-{y_str}"

        if period_key not in existing_periods and period_key not in seen:
            target_tasks.append((m_str, y_str))
            seen.add(period_key)

    if not target_tasks:
        print("All monthly data for the past 10 years is already stored in the database.", flush=True)
        return

    print(f"Starting Playwright scraper for {len(target_tasks)} periods...", flush=True)

    total_rows = 0
    completed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Dhaka",
        )
        # Hide the most common headless tell - harmless if it's not the
        # cause, but cheap to include given bot-defense is the leading
        # suspect for "works locally, empty in CI".
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        response = page.goto(TREASURY_URL, timeout=60000)
        print(f"Initial page load status: {response.status if response else 'no response'}", flush=True)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        os.makedirs(DEBUG_DIR, exist_ok=True)
        debug_saved = False

        for month_name, year_str in target_tasks:
            completed += 1
            dt = datetime.strptime(f"{month_name} {year_str}", "%b %Y")
            picker_value = dt.strftime("%B, %Y")  # e.g. "September, 2026" - confirmed working format
            period_label = f"{month_name} {year_str}"

            try:
                page.evaluate(f"""
                    const input = document.querySelector('input.datepicker-here');
                    if (input) {{
                        input.value = "{picker_value}";
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                """)
                page.wait_for_timeout(800)

                submit_btn = page.locator("input[name='submit'], button[type='submit']")
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                else:
                    page.evaluate("document.querySelector('form#search-form').submit();")

                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(1000)

                html_content = page.content()
                records = parse_treasury_table(html_content, month_name, year_str)

                if records:
                    upsert_records(records)
                    total_rows += len(records)
                    print(f"[{completed}/{len(target_tasks)}] [OK] {period_label} -> +{len(records)} records", flush=True)
                else:
                    print(f"[{completed}/{len(target_tasks)}] [SKIP/EMPTY] {period_label}", flush=True)
                    # Save exactly what the CI runner received, the first
                    # time this happens, so we can inspect it - e.g. a bot
                    # challenge page, a login wall, or a genuinely-empty
                    # month look very different from each other here.
                    if not debug_saved:
                        with open(f"{DEBUG_DIR}/empty_{period_label.replace(' ', '_')}.html", "w", encoding="utf-8") as f:
                            f.write(html_content)
                        page.screenshot(path=f"{DEBUG_DIR}/empty_{period_label.replace(' ', '_')}.png", full_page=True)
                        debug_saved = True
                        print(f"  Saved debug snapshot to {DEBUG_DIR}/ for inspection", flush=True)

            except Exception as e:
                print(f"[{completed}/{len(target_tasks)}] [ERROR] {period_label}: {e}", flush=True)

        browser.close()

    print(f"\nFINISHED! Synced a total of {total_rows} records across all historical months.", flush=True)


if __name__ == "__main__":
    main()
