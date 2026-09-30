"""
Daily incremental Treasury scraper - run this on a schedule (not the
one-time backfill script). Re-scrapes the CURRENT month and the PREVIOUS
month every run (not the whole 10-year history), relying on
ON CONFLICT ... DO UPDATE to safely refresh records without duplicating.

This catches:
  - new auctions added to the current month as the month progresses
  - late corrections to last month's figures after the month rolled over
"""
import os
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from playwright.sync_api import sync_playwright

TREASURY_URL = "https://www.bb.org.bd/en/index.php/monetaryactivity/treasury"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL secret is missing!")

engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=6,
    max_overflow=3,
)

# Requires the same schema additions as the backfill script:
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

ISIN_RE = re.compile(r"^(\S+)\s*(.*)$")


def split_isin(raw):
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


def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)


def scrape_month(page, month_str, year_str):
    dt = datetime.strptime(f"{month_str} {year_str}", "%b %Y")
    picker_value = dt.strftime("%B, %Y")
    period_label = f"{month_str} {year_str}"

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
    records = parse_treasury_table(html_content, month_str, year_str)

    if records:
        upsert_records(records)
        print(f"[OK] {period_label} -> +{len(records)} records (refreshed)", flush=True)
    else:
        print(f"[SKIP/EMPTY] {period_label}", flush=True)

    return len(records)


def main():
    today = datetime.now()
    last_month = today - relativedelta(months=1)

    targets = [
        (today.strftime("%b"), str(today.year)),
        (last_month.strftime("%b"), str(last_month.year)),
    ]

    print(f"Daily Treasury refresh: {targets}", flush=True)

    total = 0
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
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        page.goto(TREASURY_URL, timeout=60000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        for month_str, year_str in targets:
            try:
                total += scrape_month(page, month_str, year_str)
            except Exception as e:
                print(f"[ERROR] {month_str} {year_str}: {e}", flush=True)

        browser.close()

    print(f"\nDaily Treasury refresh complete. {total} records upserted across {len(targets)} months.", flush=True)


if __name__ == "__main__":
    main()
