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
    try:
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

        await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)
        
        categories = {
            "FRTB": "https://gsom.bb.org.bd/index.php/frtb?date={date_str}",
            "T-Bond": "https://gsom.bb.org.bd/index.php/tbond?date={date_str}",
            "T-Bill": "https://gsom.bb.org.bd/index.php/tbill?date={date_str}"
        }

        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() in [5, 6]:
                current_date += timedelta(days=1)
                continue
                
            date_str = current_date.strftime("%Y-%m-%d")
            total_inserted_for_day = 0

            for cat_name, url_template in categories.items():
                url = url_template.format(date_str=date_str)
                try:
                    await page.goto(url, timeout=15000)
                    await page.wait_for_load_state("domcontentloaded")

                    html_content = await page.content()
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
                        continue

                    rows = table.find("tbody").find_all("tr")
                    
                    with engine.begin() as conn:
                        for row in rows:
                            cols = row.find_all("td")
                            
                            # T-Bills have fewer columns (~11), Bonds/FRTBs have 15+
                            if cat_name == "T-Bill":
                                if len(cols) < 10:
                                    continue
                                sl_no = cols[0].get_text(strip=True)
                                isin = cols[1].get_text(strip=True)
                                sec_name = cols[2].get_text(strip=True)
                                sec_type = cols[3].get_text(strip=True)
                                issue_date = cols[4].get_text(strip=True)
                                maturity_date = cols[5].get_text(strip=True)
                                
                                # T-Bills don't have coupons, set defaults
                                coupon_rate = "0"
                                coupon_freq = "-"
                                last_coupon = "-"
                                next_coupon = "-"
                                
                                issue_price = cols[6].get_text(strip=True) if len(cols) > 6 else "0"
                                rem_maturity = cols[7].get_text(strip=True) if len(cols) > 7 else "0"
                                market_yield = cols[8].get_text(strip=True) if len(cols) > 8 else "0"
                                market_price = cols[9].get_text(strip=True) if len(cols) > 9 else "0"
                                
                                try:
                                    outstanding_bdt = float(cols[10].get_text(strip=True).replace(",", "").strip()) if len(cols) > 10 else 0.0
                                except:
                                    outstanding_bdt = 0.0
                            else:
                                if len(cols) < 15:
                                    continue
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
                                except:
                                    outstanding_bdt = 0.0

                            sql = text("""
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
                            
                            conn.execute(sql, {
                                "sl_no": sl_no, "isin": isin, "sec_name": sec_name, "sec_type": sec_type,
                                "issue_date": issue_date, "maturity_date": maturity_date, "coupon_rate": coupon_rate,
                                "coupon_freq": coupon_freq, "last_coupon": last_coupon, "next_coupon": next_coupon,
                                "issue_price": issue_price, "rem_maturity": rem_maturity, "market_yield": market_yield,
                                "market_price": market_price, "outstanding_bdt": outstanding_bdt, 
                                "category": cat_name, "extracted_date": extracted_date
                            })
                            total_inserted_for_day += 1

                except Exception as e:
                    pass

            if total_inserted_for_day > 0:
                print(f"SUCCESS: Saved {total_inserted_for_day} total rows for {date_str}", flush=True)

            current_date += timedelta(days=1)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_historical_range())
