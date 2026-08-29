import os
import concurrent.futures
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

# Base URL for GSOM Bonds MTM
URL = "https://gsom.bb.org.bd/index.php/tbond"
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL secret is missing!")

engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=20,
    max_overflow=10,
)

UPSERT_SQL = text("""
    INSERT INTO public.daily_securities
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Coupon Rate/ Spread",
     "Issue Date", "Maturity/ Expiry Date", "Issue Price", "Remaining Maturity",
     "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Data_Date")
    VALUES (:sl, :isin, :name, :stype, :coupon, :issue, :mat, :iprice, :rem, :yield_, :price, :out, :ddate)
    ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
        "Market Yield" = EXCLUDED."Market Yield",
        "Market Price" = EXCLUDED."Market Price",
        "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)",
        "Remaining Maturity" = EXCLUDED."Remaining Maturity",
        "Coupon Rate/ Spread" = EXCLUDED."Coupon Rate/ Spread";
""")

def upsert_records(records):
    if not records:
        return
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def scrape_single_date(date_str):
    """Submits the direct HTTP POST payload that PHP expects."""
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    
    payload = {
        "picker_date": picker_value,
        "submit": "Submit"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": URL
    }

    try:
        resp = requests.post(URL, data=payload, headers=headers, timeout=12)
        if resp.status_code != 200:
            return date_str, 0

        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find("table", {"class": "table"})
        if not table or not table.find("tbody"):
            return date_str, 0

        rows = table.find("tbody").find_all("tr")
        records = []
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 12:
                continue
            try:
                out_val = float(cols[11].replace(",", "").strip())
            except Exception:
                out_val = 0.0

            records.append({
                "sl": cols[0], "isin": cols[1], "name": cols[2], "stype": cols[3],
                "coupon": cols[4], "issue": cols[5], "mat": cols[6], "iprice": cols[7],
                "rem": cols[8], "yield_": cols[9], "price": cols[10], "out": out_val, "ddate": date_str,
            })

        if records:
            upsert_records(records)
            return date_str, len(records)
        return date_str, 0

    except Exception as e:
        print(f"Error on {date_str}: {e}", flush=True)
        return date_str, 0

def main():
    start_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    end_date = datetime.strptime("2026-08-27", "%Y-%m-%d").date()

    dates = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() not in (4, 5):  # Exclude Friday & Saturday
            dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    print(f"Starting ultra-fast HTTP ingestion for {len(dates)} dates...", flush=True)

    total_rows = 0
    # Use ThreadPoolExecutor for lightweight, non-blocking requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(scrape_single_date, d): d for d in dates}
        for future in concurrent.futures.as_completed(futures):
            d_str, row_count = future.result()
            if row_count > 0:
                total_rows += row_count
                print(f"[OK] {d_str} -> +{row_count} records", flush=True)

    print(f"\nFINISHED! Synced a total of {total_rows} Bond/FRTB records.", flush=True)

if __name__ == "__main__":
    main()
