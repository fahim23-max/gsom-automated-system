import os
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

BASE_URL = "https://gsom.bb.org.bd/index.php/tbill"
DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

UPSERT_SQL = text("""
    INSERT INTO public.daily_bills
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date",
     "Maturity/ Expiry Date", "Issue Price", "Remaining Maturity",
     "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Data_Date")
    VALUES (:sl, :isin, :name, :stype, :issue, :mat, :iprice, :rem, :yield_, :price, :out, :ddate)
    ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
        "Market Yield" = EXCLUDED."Market Yield",
        "Market Price" = EXCLUDED."Market Price",
        "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)",
        "Remaining Maturity" = EXCLUDED."Remaining Maturity";
""")

def upsert_records(records):
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

async def scrape_date(page, date_str):
    picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
    try:
        await page.goto(BASE_URL, timeout=30000)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

        await page.evaluate(f"""
            const el = document.querySelector('#picker_date');
            if (el) {{
                el.value = '{picker_value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)

        await page.click("input[type='submit']")
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

        try:
            await page.wait_for_selector("table.table tbody tr", timeout=5000)
        except Exception:
            return None

        html_content = await page.content()
    except Exception:
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
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
            "yield_": cols[8], "price": cols[9], "out": out_val, "ddate": date_str,
        })
    return records or None

async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())

        base_date = datetime.now()
        success = False

        for i in range(5):
            target_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            print(f"Checking T-Bills for {target_date}...", flush=True)

            records = await scrape_date(page, target_date)
            if records:
                upsert_records(records)
                print(f"SUCCESS: Synced {len(records)} T-Bills for {target_date}.", flush=True)
                success = True
                break

        await browser.close()
        if not success:
            print("No T-Bill records published in the last 5 days.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
