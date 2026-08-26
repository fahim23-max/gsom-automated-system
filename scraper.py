import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

def scrape_bb_securities(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://gsom.bb.org.bd/index.php/frtb?date={date_str}"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None
            
        tables = pd.read_html(response.text)
        if not tables:
            return None
            
        df_list = []
        for table in tables:
            if len(table) > 1:
                temp_df = table.copy()
                temp_df["Data_Date"] = date_str
                df_list.append(temp_df)
                
        if df_list:
            return pd.concat(df_list, ignore_index=True)
    except:
        pass
    return None

def run_backfill(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    current_date = start_date
    while current_date <= end_date:
        df = scrape_bb_securities(current_date)
        if df is not None and not df.empty:
            try:
                df.to_sql("daily_securities", engine, if_exists="append", index=False)
                print(f"Saved: {current_date}")
            except:
                pass
        current_date += timedelta(days=1)

if __name__ == "__main__":
    # Backfilling Year 2025
    print("Starting 2025 backfill...")
    run_backfill("2025-01-01", "2025-12-31")
    print("2025 backfill complete!")
