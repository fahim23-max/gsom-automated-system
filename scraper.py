import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from bs4 import BeautifulSoup

# Connect to Supabase with transaction pooler settings
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

def scrape_bb_securities(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"Scraping data for: {date_str}...")
    
    # URL for Bangladesh Bank GSOM portal (adjust endpoint if needed based on your current setup)
    url = f"https://gsom.bb.org.bd/index.php/frtb?date={date_str}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"Failed to fetch {date_str}, status code: {response.status_code}")
            return None
            
        # Parse tables using pandas
        tables = pd.read_html(response.text)
        if not tables:
            print(f"No tables found for {date_str}")
            return None
            
        # Combine or select the relevant tables for T_Bonds, T_Bills, FRTB
        # (Assuming your tables parse into a consolidated DataFrame or list)
        df_list = []
        for i, table in enumerate(tables):
            if len(table) > 1: # Basic check to ensure it's a data table
                temp_df = table.copy()
                temp_df["Data_Date"] = date_str
                df_list.append(temp_df)
                
        if df_list:
            final_df = pd.concat(df_list, ignore_index=True)
            return final_df
            
    except Exception as e:
        print(f"Error scraping {date_str}: {e}")
        
    return None

def run_backfill(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends or holidays if desired, or try fetching anyway
        df = scrape_bb_securities(current_date)
        if df is not None and not df.empty:
            try:
                df.to_sql("daily_securities", engine, if_exists="append", index=False)
                print(f"Successfully saved data for {current_date}")
            except Exception as db_err:
                print(f"Database save error for {current_date}: {db_err}")
                
        current_date += timedelta(days=1)

if __name__ == "__main__":
    # To run your one-time historical backfill from 2005-01-01 to today:
    today_str = datetime.now().strftime("%Y-%m-%d")
    run_backfill("2005-01-01", today_str)
