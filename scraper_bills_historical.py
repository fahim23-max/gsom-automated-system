import os
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

BASE_URL = "https://gsom.bb.org.bd/index.php/tbill"
DATABASE_URL = os.environ.get("DATABASE_URL")

# Bumped up concurrency to 6 workers specifically for historical backfill
CONCURRENCY = 6  
engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=CONCURRENCY + 5,
    max_overflow=5,
)

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

async def scrape_date(date_str, context):
    page = await context.new_page()
    try:
        await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())
        
        url = f"{BASE_URL}?date={date_str}"
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
        try:
            await page.fill("#picker_date", picker_value)
            await page.keyboard.press("Escape")
            await page.click("input[type='submit']")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        
        try:
            await page.wait_for_selector("table.table tbody tr", timeout=4000)
        except Exception:
            return None

        html_content = await page.content()
    except Exception:
        return None
    finally:
        await page.close()

    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find("table", {"class": "table"})
    
    if not table or not table.find("tbody"):
        return None

    rows = table.find("tbody").find_all("tr")
    parsed_data = []

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) >= 11:
            try:
                out_val = float(cols[10].replace(",", "").strip())
            except Exception:
                out_val = 0.0

            parsed_data.append({
                "Sl. No.": cols[0],
                "ISIN": cols[1],
                "Securities Name": cols[2],
                "Securities Type": cols[3],
                "Issue Date": cols[4],
                "Maturity/ Expiry Date": cols[5],
                "Issue Price": cols[6],
                "Remaining Maturity": cols[7],
                "Market Yield": cols[8],
                "Market Price": cols[9],
                "Outstanding BDT (in Mill)": out_val,
                "Data_Date": date_str
            })

    if parsed_data:
        return pd.DataFrame(parsed_data)
    return None

async def worker(worker_id, queue, context, day_counts):
    page = await context.new_page()
    await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())
    try:
        while True:
            date_str = await queue.get()
            if date_str is None:
                queue.task_done()
                break
            
            try:
                df = await scrape_date(date_str, page)
                if df is not None and not df.empty:
                    with engine.begin() as conn:
                        for _, row in df.iterrows():
                            conn.execute(UPSERT_SQL, {
                                "sl": row["Sl. No."],
                                "isin": row["ISIN"],
                                "name": row["Securities Name"],
                                "stype": row["Securities Type"],
                                "issue": row["Issue Date"],
                                "mat": row["Maturity/ Expiry Date"],
                                "iprice": row["Issue Price"],
                                "rem": row["Remaining Maturity"],
                                "yield_": row["Market Yield"],
                                "price": row["Market Price"],
                                "out": row["Outstanding BDT (in Mill)"],
                                "ddate": row["Data_Date"]
                            })
                    day_counts[date_str] = len(df)
                    print(f"[Worker {worker_id}] Synced T-Bills for {date_str}: +{len(df)} rows", flush=True)
            except Exception as e:
                print(f"[Worker {worker_id}] Failed on {date_str}: {e}", flush=True)
            finally:
                queue.task_done()
    finally:
        await page.close()

async def scrape_historical():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        start_date = datetime.strptime("2018-01-01", "%Y-%m-%d").date()
        end_date = datetime.strptime("2026-08-26", "%Y-%m-%d").date()

        queue = asyncio.Queue()
        current_date = start_date
        task_count = 0

        while current_date <= end_date:
            # Skip Friday (4) and Saturday (5) as per Bangladesh market schedule
            if current_date.weekday() not in (4, 5):
                queue.put_nowait(current_date.strftime("%Y-%m-%d"))
                task_count += 1
            current_date += timedelta(days=1)

        print(f"Queued {task_count} historical T-Bill dates (2018-01-01 to 2026-08-26) with {CONCURRENCY} workers.", flush=True)

        day_counts = {}
        workers = [
            asyncio.create_task(worker(i, queue, context, day_counts))
            for i in range(CONCURRENCY)
        ]

        await queue.join()
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
        await browser.close()

        total_rows = sum(day_counts.values())
        print(f"HISTORICAL T-BILL BACKFILL COMPLETE: {total_rows} total rows synced across {len(day_counts)} active days.", flush=True)

if __name__ == "__main__":
    asyncio.run(scrape_historical())
