import os
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

def scrape_bb_securities(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://gsom.bb.org.bd/index.php/frtb?date={date_str}"
    print(f"DEBUG: Trying to fetch URL -> {url}", flush=True)
    
    try:
        response = requests.get(url, timeout=20)
        print(f"DEBUG: Status Code Received: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            return None
            
        tables = pd.read_html(response.text)
        print(f"DEBUG: Number of tables found: {len(tables)}", flush=True)
        
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
            print(f"DEBUG: Parsed {len(combined_df)} rows successfully!", flush=True)
            return combined_df
    except Exception as e:
        print(f"DEBUG: Error encountered -> {e}", flush=True)
        
    return None

if __name__ == "__main__":
    print("SCRIPT STARTED", flush=True)
    test_date = datetime.strptime("2025-01-15", "%Y-%m-%d").date()
    df = scrape_bb_securities(test_date)
    
    if df is not None and not df.empty:
        try:
            df.to_sql("daily_securities", engine, if_exists="append", index=False)
            print("SUCCESS: Data written to Supabase!", flush=True)
        except Exception as db_err:
            print(f"DATABASE ERROR: {db_err}", flush=True)
    else:
        print("RESULT: No table data returned from Bangladesh Bank for this date.", flush=True)
    print("SCRIPT FINISHED", flush=True)
