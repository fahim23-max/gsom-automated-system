import os
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

CONCURRENCY = 6  
engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=CONCURRENCY + 5,
    max_overflow=5,
)

# Combined categories for FRTB and T-Bonds
CATEGORIES = {
    "FRTB": "https://gsom.bb.org.bd/index.php/frtb?date={date_str}",
    "T-Bond": "https://gsom.bb.org.bd/index.php/tbond?date={date_str}"
}

# Updated with ON CONFLICT so re-scraping the same date overwrites instead of throwing errors
UPSERT_SQL = text("""
    INSERT INTO public.daily_securities
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date",
     "Maturity/ Expiry Date", "Coupon Rate", "Coupon Freqency", "Last Coupon Date",
     "Next Coupon Date", "Issue Price", "Remaining Maturity", "Market Yield",
     "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date")
    VALUES (:sl_no, :isin, :sec_name, :sec_type, :issue_date,
            :maturity_date, :coupon_rate, :coupon_freq, :last_coupon,
            :next_coupon, :issue_price, :rem_maturity, :market_yield,
            :market_price, :outstanding_bdt, :category, :extracted_date)
    ON CONFLICT ("ISIN", "Data_Date") DO UPDATE SET
        "Market Yield" = EXCLUDED."Market Yield",
        "Market Price" = EXCLUDED."Market Price",
        "Outstanding BDT (in Mill)" = EXCLUDED."Outstanding BDT (in Mill)",
        "Remaining Maturity" = EXCLUDED."Remaining Maturity";
""")

def parse_row(cat_name, cols, extracted_date):
    if len(cols) < 15:
        return None
    
    sl_no = cols[0].get_text(strip=True)
    isin = cols[1].get_text(strip=True)
    sec_name = cols[2].get_text(strip=True)
    sec_type = cols[3].get_text(strip=True)
    issue_date = cols[4].get_text(strip=True)
    maturity_date = cols[5].get_text(strip=True)
    coupon_rate = cols[6].get_text(strip=True)
    coupon_freq = cols[7].get_text(strip=True)
    last_coupon = cols[8].get_text(strip=True)
    next_coupon = cols[9].get_text(strip=True)
    issue_price = cols[10].get_text(strip=True)
    rem_maturity = cols[11].get_text(strip=True)
    market_yield = cols[12].get_text(strip=True)
    market_price = cols[13].get_text(strip=True)

    try:
        outstanding_bdt = float(cols[14].get_text(strip=True).replace(",", "").strip())
    except Exception:
        outstanding_bdt = 0.0

    return {
        "sl_no": sl_no, "isin": isin, "sec_name": sec_name, "sec_type": sec_type,
        "issue_date": issue_date, "maturity_date": maturity_date, "coupon_rate": coupon_rate,
        "coupon_freq": coupon_freq, "last_coupon": last_coupon, "next_coupon": next_coupon,
        "issue_price": issue_price, "rem_maturity": rem_maturity, "market_yield": market_yield,
        "market_price": market_price, "outstanding_bdt": outstanding_bdt,
        "category": cat_name, "extracted_date": extracted_date,
    }

def insert_records(records):
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)

async def scrape_one(page, date_str, cat_name, url_template, day_counts, retries=3):
    url = url_template.format(date_str=date_str)
    extracted_date = date_str

    html_content = None
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            
            try:
                await page.wait_for_selector("table.table tbody tr", timeout=4000)
            except Exception:
                pass

            html_content = await page.content()
            break
        except Exception as e:
            if attempt == retries:
                print(f"FAILED {cat_name} {date_str}: {e}", flush=True)
                return
            await asyncio.sleep(2)

    soup = BeautifulSoup(html_content, 'html.parser')

    table = soup.find("table", {"class": "table"})
    if not table or not table.find("tbody"):
        return

    rows = table.find("tbody").find_all("tr")
    records = []
    for row in rows:
        cols = row.find_all("td")
        rec = parse_row(cat_name, cols, extracted_date)
        if rec:
            records.append(rec)

    if not records:
        return

    try:
        await asyncio.to_thread(insert_records, records)
    except Exception as e:
        print(f"DB INSERT FAILED {cat_name} {date_str}: {e}", flush=True)
        return

    day_counts[date_str] = day_counts.get(date_str, 0) + len(records)
    print(f"  {cat_name} {date_str}: +{len(records)} rows", flush=True)

async def worker(worker_id, queue, context, day_counts):
    page = await context.new_page()
    await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())
    try:
        while True:
            task = await queue.get()
            if task is None:
                queue.task_done()
                break
            date_str, cat_name, url_template = task
            await scrape_one(page, date_str, cat_name, url_template, day_counts)
            queue.task_done()
    finally:
        await page.close()

async def scrape_recent_range():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Smart 5-day backtracking to gracefully handle holidays/weekends when today's data is blank
        base_date = datetime.now()
        dates_to_check = [(base_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]

        queue = asyncio.Queue()
        task_count = 0
        
        for date_str in dates_to_check:
            for cat_name, url_template in CATEGORIES.items():
                queue.put_nowait((date_str, cat_name, url_template))
                task_count += 1

        print(f"Queued {task_count} tasks across recent dates {dates_to_check} with {CONCURRENCY} workers", flush=True)

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

        total = sum(day_counts.values())
        print(f"DONE: {total} total rows successfully synced across {len(day_counts)} available active dates", flush=True)

if __name__ == "__main__":
    asyncio.run(scrape_recent_range())
