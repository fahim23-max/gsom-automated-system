import os
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

BASE_URL = "https://gsom.bb.org.bd/index.php/tbill"
DATABASE_URL = os.environ.get("DATABASE_URL")
CONCURRENCY = 3  # Matches your bond scraper concurrency if needed

async def scrape_date(date_str, context):
    print(f"Scraping T-Bills for date: {date_str}...")
    page = await context.new_page()
    try:
        # Block unnecessary assets for speed
        await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())
        
        await page.goto(BASE_URL, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=10000)

        picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()
        await page.fill("#picker_date", picker_value)
        await page.keyboard.press("Escape")

        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        try:
            await page.wait_for_selector("table.table tbody tr", timeout=5000)
        except Exception:
            print(f"No table found for {date_str}")
            return None

        html_content = await page.content()
    except Exception as e:
        print(f"Error scraping {date_str}: {e}")
        return None
    finally:
        await page.close()

    # Parse rows using BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find("table", {"class": "table"})
    
    if not table or not table.find("tbody"):
        return None

    rows = table.find("tbody").find_all("tr")
    parsed_data = []

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) >= 11:
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
                "Outstanding BDT (in Mill)": cols[10].replace(",", ""),
                "Data_Date": date_str
            })

    if parsed_data:
        df = pd.DataFrame(parsed_data)
        print(f"Successfully extracted {len(df)} rows for {date_str}")
        return df
    return None

async def worker(name, queue, context, engine):
    while True:
        date_str = await queue.get()
        if date_str is None:
            queue.task_done()
            break
        
        try:
            df = await scrape_date(date_str, context)
            if df is not None and not df.empty:
                # Insert or Update into Supabase using raw SQL connection for conflict safety
                with engine.begin() as conn:
                    for _, row in df.iterrows():
                        sql = text("""
                            INSERT INTO public.daily_bills 
                            ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date", 
                             "Maturity/ Expiry Date", "Issue Price", "Remaining Maturity", 
                             "Market Yield", "Market Price", "Outstanding BDT (in Mill)", "Data_Date")
                            VALUES (:sl, :isin, :name, :stype, :issue, :mat, :iprice, :rem, :yield_, :price, :out, :ddate)
                            ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
                                "Market Yield" = EXCLUDED."Market Yield",
                                "Market Price" = EXCLUDED."Market Price",
                                "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)";
                        """)
                        conn.execute(sql, {
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
                print(f"Saved {len(df)} T-Bill rows to database for {date_str}")
        except Exception as e:
            print(f"Worker {name} failed on {date_str}: {e}")
        finally:
            queue.task_done()

async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set.")
        return

    engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Target today's date (or you can expand this to a date range list if backfilling)
        date_list = [datetime.now().strftime("%Y-%m-%d")]

        queue = asyncio.Queue()
        for d in date_list:
            queue.put_nowait(d)

        workers = [
            asyncio.create_task(worker(i, queue, context, engine))
            for i in range(CONCURRENCY)
        ]

        await queue.join()
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
        await browser.close()
        print("T-Bill Daily Scrape & Database Sync Complete!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
