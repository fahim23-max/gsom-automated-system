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
    print(f"Trying to fetch: {url}")
    
    try:
        response = requests.get(url, timeout=20)
        print(f"Status Code for {date_str}: {response.status_code}")
        
        if response.status_code != 200:
            return None
            
        tables = pd.read_html(response.text)
        print(f"Found {len(tables)} tables on {date_str}")
        
        if not tables:
            return None
            
        df_list = []
        for table in tables:
            if len(table) > 1:
                temp_df = table.copy()
                temp_df["Data_Date"] = date_str
                df_list.append(temp_df)
                
        if df_list:
            combined_df = pd.concat(df_list, ignore_index=True)
            print(f"Successfully parsed {len(combined_df)} rows for {date_str}")
            return combined_df
    except Exception as e:
        print(f"Error scraping {date_str}: {e}")
        
    return None

if __name__ == "__main__":
    # Test a single known trading date in 2025 (e.g., January 15, 2025)
    test_date = datetime.strptime("2025-01-15", "%Y-%m-%d").date()
    df = scrape_bb_securities(test_date)
    
    if df is not None and not df.empty:
        try:
            df.to_sql("daily_securities", engine, if_exists="append", index=False)
            print(f"SUCCESS: Saved test data for {test_date} into Supabase!")
        except Exception as db_err:
            print(f"Database save error: {db_err}")
    else:
        print(f"No data returned or parsed for {test_date}")
