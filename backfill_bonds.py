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

ENDPOINTS = {
    "BGTB": "https://gsom.bb.org.bd/index.php/tbond",
    "FRTB": "https://gsom.bb.org.bd/index.php/frtb"
}

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

UPSERT_SQL = text("""
    INSERT INTO public.daily_securities
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date",
     "Maturity/ Expiry Date", "Coupon Rate", "Coupon Freqency", "Last Coupon Date",
     "Next Coupon Date", "Issue Price", "Remaining Maturity", "Market Yield",
     "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date")
    VALUES (:sl, :isin, :name, :stype, :issue, :mat, :coupon, :freq, :last_c, :next_c,
            :iprice, :rem, :yield_, :price, :out, :cat, :ddate)
    ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
        "Market Yield" = EXCLUDED."Market Yield",
        "Market Price" = EXCLUDED."Market Price",
        "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)",
        "Remaining Maturity" = EXCLUDED."Remaining Maturity",
        "Coupon Rate" = EXCLUDED."Coupon Rate",
        "Next Coupon Date" = EXCLUDED."Next Coupon Date",
        "Category" = EXCLUDED."Category";
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

def get_existing_dates():
    """Queries the database to skip dates that already exist."""
    with engine.connect() as conn:
        res = conn.execute(text('SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_securities'))
        return set(row[0] for row in res.fetchall())

def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def parse_table(html_text, date_str, category_name):
    soup = BeautifulSoup(html_text, 'html.parser')
    table = soup.find("table", {"class": "table"})
    if not table or not table.find("tbody"):
        return []

    rows = table.find("tbody").find_all("tr")
    records = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 15:
            continue
        try:
            out_val = float(cols[14].replace(",", "").strip())
        except Exception:
            out_val = 0.0

        records.append({
            "sl": cols[0],
            "isin": cols[1],
            "name": cols[2],
            "stype": cols[3],
            "issue": cols[4],
            "mat": cols[5],
            "coupon": cols[6],
            "freq": cols[7],
            "last_c": cols[8],
            "next_c": cols[9],
            "iprice": cols[10],
            "rem": cols[11],
            "yield_": cols[12],
            "price": cols[13],
            "out": out_val,
            "cat": category_name,
            "ddate": date_str,
        })
    return records

def scrape_date_worker(date_str):
    session = get_session()
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    payload = {"picker_date": picker_value, "submit": "Submit"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    all_records = []
    for cat_name, url in ENDPOINTS.items():
        headers["Referer"] = url
        try:
            time.sleep(0.1)  # Micro-throttle per thread to prevent socket saturation
            resp = session.post(url, data=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                recs = parse_table(resp.text, date_str, cat_name)
                all_records.extend(recs)
        except Exception as e:
            print(f"[ERROR] {date_str} ({cat_name}): {e}", flush=True)

    if all_records:
        upsert_records(all_records)
        return date_str, len(all_records)
    return date_str, 0

def main():
    start_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    end_date = datetime.strptime("2026-08-27", "%Y-%m-%d").date()

    existing_dates = get_existing_dates()
    print(f"Found {len(existing_dates)} existing Bond dates in DB. Skipping duplicate requests...", flush=True)

    dates = []
    curr = start_date
    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        if curr.weekday() not in (4, 5) and d_str not in existing_dates:
            dates.append(d_str)
        curr += timedelta(days=1)

    dates.reverse()

    if not dates:
        print("All Bond dates in range are already stored in the database.", flush=True)
        return

    NUM_WORKERS = 6
    print(f"Starting ingestion for {len(dates)} dates using {NUM_WORKERS} concurrent workers...", flush=True)

    total_rows = 0
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(scrape_date_worker, d): d for d in dates}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            d_str, row_count = future.result()
            if row_count > 0:
                total_rows += row_count
                print(f"[{completed}/{len(dates)}] [OK] {d_str} -> +{row_count} records (BGTB + FRTB)", flush=True)
            else:
                print(f"[{completed}/{len(dates)}] [SKIP/EMPTY] {d_str}", flush=True)

    print(f"\nFINISHED! Synced a total of {total_rows} records.", flush=True)

if __name__ == "__main__":
    main()
