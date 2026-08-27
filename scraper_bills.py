import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_URL = "https://gsom.bb.org.bd/index.php/tbill"

async def test_tab_picking():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Block unnecessary assets for speed
        await page.route("**/*.{png,jpg,jpeg,css,font,woff,svg}", lambda route: route.abort())
        
        print(f"Navigating to T-Bill portal: {BASE_URL}")
        await page.goto(BASE_URL, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=10000)

        # Test date matching your active session format
        date_str = "2026-08-25"
        picker_value = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%y").upper()

        print(f"Filling date input with: {picker_value}")
        await page.fill("#picker_date", picker_value)
        
        # Dismiss calendar overlay
        await page.keyboard.press("Escape")

        print("Triggering form submission ('Show Result')...")
        await page.click("input[type='submit']")

        # Wait for table to render data rows
        await page.wait_for_load_state("networkidle", timeout=15000)
        try:
            await page.wait_for_selector("table.table tbody tr", timeout=5000)
        except Exception:
            print("Warning: Selector wait timed out, checking current DOM.")

        html_content = await page.content()
        await browser.close()

    # Parse and verify picked rows
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find("table", {"class": "table"})
    
    if not table or not table.find("tbody"):
        print("TEST FAILED: No data table found.")
        return

    rows = table.find("tbody").find_all("tr")
    print(f"TEST SUCCESS: Picked {len(rows)} rows from the T-Bill tab!\n")

    # Print a quick sample of the first 3 rows
    for i, row in enumerate(rows[:3], start=1):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) >= 11:
            print(f"Row {i} -> ISIN: {cols[1]} | Name: {cols[2]} | Yield: {cols[8]} | Price: {cols[9]}")

if __name__ == "__main__":
    asyncio.run(test_tab_picking())
