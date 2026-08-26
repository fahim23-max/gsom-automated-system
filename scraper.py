import os
import asyncio
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

def parse_bb_date(date_str):
    # Converts '25-AUG-26' or similar formats to standard YYYY-MM-DD
    try:
        # Clean up brackets if captured
        clean_str = date_str.replace("[", "").replace("]", "").strip()
        dt = datetime.strptime(clean_str, "%d-%b-%y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None

async def scrape_historical_range():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Adjust backfill range (e.g., past 60 days to test cleanly or expand as needed)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=60)
        
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() in [5, 6]: # Skip weekends
                current_date += timedelta(days=1)
                continue
                
            date_str = current_date.strftime("%Y-%m-%d")
            url = f"https://gsom.bb.org.bd/index.php/frtb?date={date_str}"
            
            try:
                print(f"Fetching data for {date_str}...", flush=True)
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle")

                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'html.parser')

                # Extract exact yield date from page banner if available
                yield_date_div = soup.find(string=re.compile(r"Yield date:"))
                extracted_date = date_str
                if yield_date_div:
                    match = re.search(r"([0-9]{2}-[A-Z]{3}-[0-9]{2})", yield_date_div)
                    if match:
                        parsed = parse_bb_date(match.group(1))
                        if parsed:
                            extracted_date = parsed

                # Find the main data table
                table = soup.find("table", {"class": "table"})
                if not table:
                    print(f"No table found for {date_str}", flush=True)
                    current_date += timedelta(days=1)
                    continue

                rows = table.find("tbody").find_all("tr")
                inserted_count = 0

                with engine.begin() as conn:
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 15:
                            continue
                        
                        # Extract and clean values safely
                        isin = cols[1].get_text(strip=True)
                        sec_name = cols[2].get_text(strip=True)
                        sec_type = cols[3].get_text(strip=True)
                        issue_date = cols[4].get_text(strip=True)
                        maturity_date = cols[5].get_text(strip=True)
                        
                        def safe_float(val):
                            try:
                                return float(val.replace(",", "").strip())
                            except:
                                return 0.0

                        coupon_rate = safe_float(cols[6].get_text(strip=True))
                        coupon_freq = cols[7].get_text(strip=True)
                        last_coupon = cols[8].get_text(strip=True)
                        next_coupon = cols[9].get_text(strip=True)
                        issue_price = safe_float(cols[10].get_text(strip=True))
                        rem_maturity = safe_float(cols[11].get_text(strip=True))
                        market_yield = safe_float(cols[12].get_text(strip=True))
                        market_price = safe_float(cols[13].get_text(strip=True))
                        outstanding_bdt = safe_float(cols[14].get_text(strip=True))

                        # Insert or upsert into database table
                        sql = text("""
                            INSERT INTO daily_securities 
                            (isin, securities_name, securities_type, issue_date, maturity_date, 
                             coupon_rate, coupon_freq, last_coupon_date, next_coupon_date, 
                             issue_price, remaining_maturity, market_yield, market_price, 
                             outstanding_bdt, data_date)
                            VALUES (:isin, :sec_name, :sec_type, :issue_date, :maturity_date,
                                    :coupon_rate, :coupon_freq, :last_coupon, :next_coupon,
                                    :issue_price, :rem_maturity, :market_yield, :market_price,
                                    :outstanding_bdt, :extracted_date)
                            ON CONFLICT DO NOTHING;
                        """)
                        
                        conn.execute(sql, {
                            "isin": isin, "sec_name": sec_name, "sec_type": sec_type,
                            "issue_date": issue_date, "maturity_date": maturity_date,
                            "coupon_rate": coupon_rate, "coupon_freq": coupon_freq,
                            "last_coupon": last_coupon, "next_coupon": next_coupon,
                            "issue_price": issue_price, "rem_maturity": rem_maturity,
                            "market_yield": market_yield, "market_price": market_price,
                            "outstanding_bdt": outstanding_bdt, "extracted_date": extracted_date
                        })
                        inserted_count += 1

                if inserted_count > 0:
                    print(f"SUCCESS: Saved {inserted_count} rows for {extracted_date}", flush=True)

            except Exception as e:
                print(f"Error processing {date_str}: {e}", flush=True)

            current_date += timedelta(days=1)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_historical_range())
