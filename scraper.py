import os
import asyncio
from datetime import datetime, timedelta
import pandas as pd
from playwright.async_api import async_playwright
from sqlalchemy import create_engine

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

async def scrape_historical_range():
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Define date range to backfill (e.g., past 1 year or adjust as needed)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)
        
        current_date = start_date
        while current_date <= end_date:
            # Skip weekends if needed or let the portal handle it
            if current_date.weekday() in [5, 6]: # Friday/Saturday in Bangladesh or standard weekends
                current_date += timedelta(days=1)
                continue
                
            date_str = current_date.strftime("%Y-%m-%d")
            url = f"https://gsom.bb.org.bd/index.php/frtb?date={date_str}"
            
            try:
                print(f"Fetching data for {date_str}...", flush=True)
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle")

                # Extract tables using pandas read_html from the page content
                html_content = await page.content()
                tables = pd.read_html(html_content)

                if tables:
                    df_list = []
                    for table in tables:
                        if len(table) > 1:
                            temp_df = table.copy()
                            temp_df["Data_Date"] = date_str
                            df_list.append(temp_df)
                            
                    if df_list:
                        combined_df = pd.concat(df_list, ignore_index=True)
                        combined_df.to_sql("daily_securities", engine, if_exists="append", index=False)
                        print(f"SUCCESS: Saved {len(combined_df)} rows for {date_str}", flush=True)
            except Exception as e:
                print(f"No data or error for {date_str}: {e}", flush=True)

            current_date += timedelta(days=1)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_historical_range())
