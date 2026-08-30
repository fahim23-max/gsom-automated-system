import os
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

# URLs for both pages on Bangladesh Bank GSOM
BOND_URL = "https://gsom.bb.org.bd/index.php/tbond"
FRTB_URL = "https://gsom.bb.org.bd/index.php/frtb"
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is missing.")

engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

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

def upsert_records(records):
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

def scrape_url_for_date(target_url, date_str, category_default):
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    payload = {"picker_date": picker_value, "submit": "Submit"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": target_url}

    try:
        resp = requests.post(target_url, data=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find("table", {"class": "table"})
        if not table or not table.find("tbody"):
            return []

        rows = table.find("tbody").find_all("tr")
        records = []
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 14:
                continue
            try:
                out_val = float(cols[13].replace(",", "").strip())
            except Exception:
                out_val = 0.0

            cat_val = "FRTB" if ("FRTB" in cols[2].upper() or "FRTB" in cols[3].upper() or category_default == "FRTB") else "BGTB"
            
            records.append({
                "sl": cols[0], "isin": cols[1], "name": cols[2], "stype": cols[3],
                "issue": cols[4], "mat": cols[5], "coupon": cols[6], "freq": cols[7],
                "last_c": cols[8], "next_c": cols[9], "iprice": cols[10], "rem": cols[11],
                "yield_": cols[12], "price": cols[10], "out": out_val, "cat": cat_val,
                "ddate": date_str,
            })
        return records
    except Exception as e:
        print(f"  -> Error scraping {target_url} for {date_str}: {e}")
        return []

def main():
    base_date = datetime.now()
    success = False
    
    for i in range(10):
        target_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"Checking Securities for {target_date}...", flush=True)
        
        # Scrape both regular Bonds and FRTBs for this date
        bond_records = scrape_url_for_date(BOND_URL, target_date, "BGTB")
        frtb_records = scrape_url_for_date(FRTB_URL, target_date, "FRTB")
        
        all_records = bond_records + frtb_records
        
        if all_records:
            upsert_records(all_records)
            print(f"SUCCESS: Synced {len(bond_records)} Bonds and {len(frtb_records)} FRTBs for {target_date}.", flush=True)
            success = True
            break
            
    if not success:
        print("CRITICAL: No Security records found in the last 10 days.", flush=True)

if __name__ == "__main__":
    main()
