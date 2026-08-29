import os
import time
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

URL = "https://gsom.bb.org.bd/index.php/tbill"
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL secret is missing!")

engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=5,
    max_overflow=2,
)

UPSERT_SQL = text("""
    INSERT INTO public.daily_bills
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date",
     "Maturity/ Expiry Date", "Issue Price", "Remaining Maturity",
     "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date")
    VALUES (:sl, :isin, :name, :stype, :issue, :mat, :iprice, :rem, :yield_, :price, :out, :cat, :ddate)
    ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
        "Market Yield" = EXCLUDED."Market Yield",
        "Market Price" = EXCLUDED."Market Price",
        "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)",
        "Remaining Maturity" = EXCLUDED."Remaining Maturity",
        "Category" = EXCLUDED."Category";
""")

def get_existing_dates():
    """Fetches dates already in DB so we never re-scrape or duplicate them."""
    with engine.connect() as conn:
        res = conn.execute(text('SELECT DISTINCT "Data_Date"::TEXT FROM public.daily_bills'))
        return set(row[0] for row in res.fetchall())

def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def scrape_single_date(session, date_str):
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    payload = {"picker_date": picker_value, "submit": "Submit"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": URL
    }

    try:
        resp = session.post(URL, data=payload, headers=headers, timeout=25)
        if resp.status_code != 200:
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find("table", {"class": "table"})
        if not table or not table.find("tbody"):
            return 0

        rows = table.find("tbody").find_all("tr")
        records = []
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 11:
                continue
            try:
                out_val = float(cols[10].replace(",", "").strip())
            except Exception:
                out_val = 0.0

            records.append({
                "sl": cols[0],
                "isin": cols[1],
                "name": cols[2],
                "stype": cols[3],
                "issue": cols[4],
                "mat": cols[5],
                "iprice": cols[6],
                "rem": cols[7],
                "yield_": cols[8],
                "price": cols[9],
                "out": out_val,
                "cat": "T-Bill",
                "ddate": date_str,
            })

        if records:
            upsert_records(records)
            return len(records)
        return 0

    except Exception as e:
        print(f"Error on {date_str}: {e}", flush=True)
        return 0

def main():
    start_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    end_date = datetime.strptime("2026-08-27", "%Y-%m-%d").date()

    existing_dates = get_existing_dates()
    print(f"Found {len(existing_dates)} existing T-Bill dates in DB. Skipping duplicate requests...", flush=True)

    dates = []
    curr = start_date
    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        if curr.weekday() not in (4, 5) and d_str not in existing_dates:
            dates.append(d_str)
        curr += timedelta(days=1)

    dates.reverse()

    if not dates:
        print("All T-Bill dates in range are already stored in the database. Nothing to backfill.", flush=True)
        return

    print(f"Starting ingestion for {len(dates)} missing T-Bill dates...", flush=True)

    session = create_session()
    total_rows = 0

    for idx, d_str in enumerate(dates, 1):
        row_count = scrape_single_date(session, d_str)
        if row_count > 0:
            total_rows += row_count
            print(f"[{idx}/{len(dates)}] [OK] {d_str} -> +{row_count} records", flush=True)
        else:
            print(f"[{idx}/{len(dates)}] [SKIP/EMPTY] {d_str}", flush=True)
        time.sleep(0.15)

    session.close()
    print(f"\nFINISHED! Synced a total of {total_rows} new T-Bill records.", flush=True)

if __name__ == "__main__":
    main()
