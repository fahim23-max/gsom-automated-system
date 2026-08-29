import os
import time
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

URL = "https://gsom.bb.org.bd/index.php/tbond"
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
        "Next Coupon Date" = EXCLUDED."Next Coupon Date";
""")

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
            if len(cols) < 15:
                continue
            try:
                out_val = float(cols[14].replace(",", "").strip())
            except Exception:
                out_val = 0.0

            cat_val = "FRTB" if "FRTB" in cols[2].upper() or "FRTB" in cols[3].upper() else "BGTB"

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
                "cat": cat_val,
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
    start_date = datetime.strptime("2020-01-01", "%Y-%m-%d").date()
    end_date = datetime.strptime("2026-08-27", "%Y-%m-%d").date()

    dates = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() not in (4, 5):  # Exclude Friday & Saturday
            dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    print(f"Starting reliable sequential ingestion for {len(dates)} Bond dates...", flush=True)

    session = create_session()
    total_rows = 0

    for idx, d_str in enumerate(dates, 1):
        row_count = scrape_single_date(session, d_str)
        if row_count > 0:
            total_rows += row_count
            print(f"[{idx}/{len(dates)}] [OK] {d_str} -> +{row_count} records", flush=True)
        else:
            print(f"[{idx}/{len(dates)}] [SKIP/EMPTY] {d_str}", flush=True)
        time.sleep(0.15)  # Safe delay to prevent IP bans

    session.close()
    print(f"\nFINISHED! Synced a total of {total_rows} Bond/FRTB records.", flush=True)

if __name__ == "__main__":
    main()
