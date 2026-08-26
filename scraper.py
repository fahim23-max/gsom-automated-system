import os
import io
import pandas as pd
import requests
import urllib3
from datetime import datetime
from sqlalchemy import create_engine

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL is not set!")

engine = create_engine(DB_URL)

urls = {
    "T_Bonds": "https://gsom.bb.org.bd/index.php/tbond",
    "T_Bills": "https://gsom.bb.org.bd/index.php/tbill",
    "FRTB": "https://gsom.bb.org.bd/index.php/frtb"
}

headers = {"User-Agent": "Mozilla/5.0"}
all_dfs = []
today = datetime.now().strftime('%Y-%m-%d')

for category, url in urls.items():
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=20)
        tables = pd.read_html(io.StringIO(res.text))
        df = max(tables, key=len)
        if 'Total Outstanding Balance' in str(df.iloc[-1].values):
            df = df.iloc[:-1]
        df['Category'] = category
        all_dfs.append(df)
        print(f"Scraped {category}")
    except Exception as e:
        print(f"Error scraping {category}: {e}")

if all_dfs:
    combined = pd.concat(all_dfs, ignore_index=True)
    combined['Data_Date'] = today
    combined.to_sql('daily_securities', engine, if_exists='append', index=False)
    print(f"Successfully saved data for {today}")
