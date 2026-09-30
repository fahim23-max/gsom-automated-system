import os
import time
from datetime import datetime, timedelta
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
    pool_size=12,
    max_overflow=6,
)

UPSERT_SQL = text("""
    INSERT INTO public.treasury_monthly_data 
    ("Month", "Year", "ISIN", "Securities_Name", "Tenor", "Bids_Received", 
     "Face_Value_Received", "Range_Yields_Received", "Bids_Accepted", 
     "Face_Value_Accepted", "Sale_Value", "Range_Yields_Accepted", 
     "Weighted_Avg_Price", "Cut_Off_Yield", "Data_Period")
    VALUES (:month, :year, :isin, :name, :tenor, :bids_rec, :fv_rec, 
            :range_rec, :bids_acc, :fv_acc, :sale_val, :range_acc, 
            :waprice, :cutoff, :period)
    ON CONFLICT ("ISIN", "Data_Period") DO UPDATE SET
        "Face_Value_Accepted" = EXCLUDED."Face_Value_Accepted",
        "Sale_Value" = EXCLUDED."Sale_Value",
        "Cut_Off_Yield" = EXCLUDED."Cut_Off_Yield",
        "Weighted_Avg_Price" = EXCLUDED."Weighted_Avg_Price",
        "Bids_Accepted" = EXCLUDED."Bids_Accepted";
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

def parse_treasury_table(html_text, month_str, year_str):
    soup = BeautifulSoup(html_text, 'html.parser')
    table = soup.find("table", {"class": "table"})
    if not table:
        tables = soup.find_all("table")
        table = tables[0] if tables else None

    if not table or not table.find("tbody"):
        return []

    rows = table.find("tbody").find_all("tr")
    records = []
    period_tag = f"{month_str}-{year_str}"

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 10:
            continue
        
        try:
            fv_acc = float(cols[9].replace(",", "").strip()) if cols[9] else 0.0
        except Exception:
            fv_acc = 0.0

        try:
            sale_val = float(cols[10].replace(",", "").strip()) if len(cols) > 10 and cols[10] else 0.0
        except Exception:
            sale_val = 0.0

        records.append({
            "month": month_str,
            "year": int(year_str),
            "isin": cols[1] if len(cols) > 1 else "",
            "name": cols[3] if len(cols) > 3 else "",
            "tenor": cols[2] if len(cols) > 2 else "",
            "bids_rec": cols[4] if len(cols) > 4 else "",
            "fv_rec": 0.0,
            "range_rec": "",
            "bids_acc": cols[5] if len(cols) > 5 else "",
            "fv_acc": fv_acc,
            "sale_val": sale_val,
            "range_acc": cols[11] if len(cols) > 11 else "",
            "waprice": 0.0,
            "cutoff": 0.0,
            "period": period_tag
        })
    return records

def main():
    existing_periods = get_existing_periods()
    print(f"Found {len(existing_periods)} existing periods in DB. Skipping duplicates...", flush=True)

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_date = datetime.now()
    target_tasks = []
    
    for i in range(120): # Past 10 years
        d = current_date - timedelta(days=30 * i)
        m_str = months[d.month - 1]
        y_str = str(d.year)
        period_key = f"{m_str}-{y_str}"
        
        if period_key not in existing_periods:
            if (m_str, y_str) not in target_tasks:
                target_tasks.append((m_str, y_str))

    if not target_tasks:
        print("All monthly data for the past 10 years is already stored in the database.", flush=True)
        return

    print(f"Starting stealth Playwright scraper for {len(target_tasks)} periods...", flush=True)

    total_rows = 0
    completed = 0

    with sync_playwright() as p:
        # Launch browser with arguments to disable automation flags that trigger Radware TSPD
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        
        # Open base URL and wait for Radware script/cookie challenge to resolve
        page.goto(TREASURY_URL, timeout=60000)
        page.wait_for_timeout(4000) # Allow security fingerprint script to execute

        for month_name, year_str in target_tasks:
            completed += 1
            dt = datetime.strptime(f"{month_name} {year_str}", "%b %Y")
            picker_value = dt.strftime("%B, %Y")
            period_label = f"{month_name} {year_str}"

            try:
                # Type the date and submit
                page.locator("input.datepicker-here").fill("")
                page.locator("input.datepicker-here").type(picker_value)
                
                page.locator("input[name='submit'], button[type='submit']").click()
                page.wait_for_timeout(3000) # Wait for table update

                html_content = page.content()
                records = parse_treasury_table(html_content, month_name, year_str)

                if records:
                    upsert_records(records)
                    total_rows += len(records)
                    print(f"[{completed}/{len(target_tasks)}] [OK] {period_label} -> +{len(records)} records", flush=True)
                else:
                    print(f"[{completed}/{len(target_tasks)}] [SKIP/EMPTY] {period_label}", flush=True)

            except Exception as e:
                print(f"[{completed}/{len(target_tasks)}] [ERROR] {period_label}: {e}", flush=True)

        browser.close()

    print(f"\nFINISHED! Synced a total of {total_rows} records across all historical months.", flush=True)

if __name__ == "__main__":
    main()
