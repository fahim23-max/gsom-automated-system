import os
import asyncio
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

CONCURRENCY = 3
engine = create_engine(
    DATABASE_URL,
    connect_args={'prepare_threshold': None},
    pool_size=CONCURRENCY + 5,
    max_overflow=5,
)

CATEGORIES = {
    "FRTB": "https://gsom.bb.org.bd/index.php/frtb?date={date_str}",
    "T-Bond": "https://gsom.bb.org.bd/index.php/tbond_mtm?date={date_str}",
    "T-Bill": "https://gsom.bb.org.bd/index.php/tbill_mtm?date={date_str}"
}

INSERT_SQL = text("""
    INSERT INTO public.daily_securities
    ("Sl. No.", "ISIN", "Securities Name", "Securities Type", "Issue Date",
     "Maturity/ Expiry Date", "Coupon Rate", "Coupon Freqency", "Last Coupon Date",
     "Next Coupon Date", "Issue Price", "Remaining Maturity", "Market Yield",
     "Market Price", "Outstanding BDT (in Mill)", "Category", "Data_Date")
    VALUES (:sl_no, :isin, :sec_name, :sec_type, :issue_date,
            :maturity_date, :coupon_rate, :coupon_freq, :last_coupon,
            :next_coupon, :issue_price, :rem_maturity, :market_yield,
            :market_price, :outstanding_bdt, :category, :extracted_date);
""")


def parse_bb_date(date_str):
    try:
        clean_str = date_str.replace("[", "").replace("]", "").strip()
        dt = datetime.strptime(clean_str, "%d-%b-%y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_row(cat_name, cols, extracted_date):
    if cat_name == "T-Bill":
        if len(cols) < 11:
            return None
        sl_no = cols[0].get_text(strip=True)
        isin = cols[1].get_text(strip=True)
        sec_name = cols[2].get_text(strip=True)
        sec_type = cols[3].get_text(strip=True)
        issue_date = cols[4].get_text(strip=True)
        maturity_date = cols[5].get_text(strip=True)

        coupon_rate = "0"
        coupon_freq = "-"
        last_coupon = "-"
        next_coupon = "-"

        issue_price = cols[6].get_text(strip=True)
        rem_maturity = cols[7].get_text(strip=True)
        market_yield = cols[8].get_text(strip=True)
        market_price = cols[9].get_text(strip=True)

        try:
            outstanding_bdt = float(cols[10].get_text(strip=True).replace(",", "").strip())
        except Exception:
            outstanding_bdt = 0.0
    else:
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
        conn.execute(INSERT_SQL, records)


async def scrape_one(page, date_str, cat_name, url_template, day_counts, retries=3):
    url = url_template.format(date_str=date_str)

    html_content = None
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            html_content = await page.content()
            break
        except Exception as e:
            if attempt == retries:
                print(f"FAILED {cat_name} {date_str}: {e}", flush=True)
                return
            await asyncio.sleep(2)

    soup = BeautifulSoup(html_content, 'html.parser')

    yield_date_div = soup.find(string=re.compile(r"Yield date:"))
    extracted_date = date_str
    if yield_date_div:
        match = re.search(r"([0-9]{2}-[A-Z]{3}-[0-9]{2})", yield_date_div)
        if match:
            parsed = parse_bb_date(match.group(1))
            if parsed:
                extracted_date = parsed

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


async def scrape_historical_range():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)

        queue = asyncio.Queue()
        current_date = start_date
        task_count = 0
        while current_date <= end_date:
            if current_date.weekday() not in (5, 6):
                date_str = current_date.strftime("%Y-%m-%d")
                for cat_name, url_template in CATEGORIES.items():
                    queue.put_nowait((date_str, cat_name, url_template))
                    task_count += 1
            current_date += timedelta(days=1)

        print(f"Queued {task_count} (date, category) tasks with {CONCURRENCY} concurrent workers", flush=True)

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
        print(f"DONE: {total} total rows across {len(day_counts)} days with data", flush=True)


if __name__ == "__main__":
    asyncio.run(scrape_historical_range())
