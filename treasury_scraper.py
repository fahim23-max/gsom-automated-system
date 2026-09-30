import os
import time
import threading
import concurrent.futures
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

# Target URL for monthly treasury/monetary activity data
TREASURY_URL = "https://www.bb.org.bd/en/index.php/monetaryactivity/treasury"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL secret is missing!")

# Database connection pool scaled for 6+ worker threads
engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=12,
    max_overflow=6,
)

# UPSERT statement mapping to your Supabase treasury_monthly_data table schema
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

thread_local = threading.local()

def get_session():
    """Provides a thread-isolated Session object with robust connection retries."""
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        thread_local.session = session
    return thread_local.session

def get_existing_periods():
    """Queries the database to skip monthly periods that already exist."""
    with engine.connect() as conn:
        res = conn.execute(text('SELECT DISTINCT "Data_Period" FROM public.treasury_monthly_data'))
        return set(row[0] for row in res.fetchall())

def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def parse_treasury_table(html_text, month_str, year_str):
    """Parses the HTML table rows for the given month and year."""
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Locate the target table
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

def scrape_month_worker(period_tuple):
    """Worker function to fetch data for a specific month and year via POST request."""
    month_name, year_str = period_tuple
    session = get_session()
    
    # Format date to match data-date-format="MM, yyyy" (e.g., "January, 2020")
    dt = datetime.strptime(f"{month_name} {year_str}", "%b %Y")
    picker_value = dt.strftime("%B, %Y")
    
    payload = {
        "date_picker": picker_value,
        "submit": "Submit"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": TREASURY_URL
    }

    try:
        time.sleep(0.2)  # Micro-throttle to prevent socket saturation
        resp = session.post(TREASURY_URL, data=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            records = parse_treasury_table(resp.text, month_name, year_str)
            if records:
                upsert_records(records)
                return f"{month_name} {year_str}", len(records)
    except Exception as e:
        print(f"[ERROR] {month_name} {year_str}: {e}", flush=True)

    return f"{month_name} {year_str}", 0

def main():
    existing_periods = get_existing_periods()
    print(f"Found {len(existing_periods)} existing periods in Supabase DB. Skipping duplicates...", flush=True)

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    current_date = datetime.now()
    target_tasks = []
    
    # Generate past 10 years of month-year combinations (120 months)
    for i in range(120):
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

    NUM_WORKERS = 6
    print(f"Starting historical monthly ingestion for {len(target_tasks)} periods using {NUM_WORKERS} concurrent workers...", flush=True)

    total_rows = 0
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(scrape_month_worker, task): task for task in target_tasks}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            period_label, row_count = future.result()
            if row_count > 0:
                total_rows += row_count
                print(f"[{completed}/{len(target_tasks)}] [OK] {period_label} -> +{row_count} records", flush=True)
            else:
                print(f"[{completed}/{len(target_tasks)}] [SKIP/EMPTY] {period_label}", flush=True)

    print(f"\nFINISHED! Synced a total of {total_rows} records across all historical months.", flush=True)

if __name__ == "__main__":
    main()
