import os
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

URL = "https://gsom.bb.org.bd/index.php/tbill"
DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

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
        "Remaining Maturity" = EXCLUDED."Remaining Maturity";
""")

def upsert_records(records):
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def scrape_single_date(date_str):
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    payload = {"picker_date": picker_value, "submit": "Submit"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": URL}

    try:
        resp = requests.post(URL, data=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find("table", {"class": "table"})
        if not table or not table.find("tbody"):
            return None

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
                "sl": cols[0], "isin": cols[1], "name": cols[2], "stype": cols[3],
                "issue": cols[4], "mat": cols[5], "iprice": cols[6], "rem": cols[7],
                "yield_": cols[8], "price": cols[9], "out": out_val, "cat": "T-Bill",
                "ddate": date_str,
            })
        return records or None
    except Exception:
        return None

def main():
    base_date = datetime.now()
    success = False
    for i in range(5):
        target_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"Checking T-Bills for {target_date}...", flush=True)
        records = scrape_single_date(target_date)
        if records:
            upsert_records(records)
            print(f"SUCCESS: Synced {len(records)} T-Bills for {target_date}.", flush=True)
            success = True
            break
    if not success:
        print("No T-Bill records found in the last 5 days.", flush=True)

if __name__ == "__main__":
    main()
