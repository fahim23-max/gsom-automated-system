async def scrape_latest_available():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Check today, then step back day-by-day until we find the latest published date
        base_date = datetime.now()
        success = False

        for i in range(5):
            target_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            print(f"Checking bond data for date: {target_date}...", flush=True)
            
            day_counts = {}
            queue = asyncio.Queue()
            for cat_name, url_template in CATEGORIES.items():
                queue.put_nowait((target_date, cat_name, url_template))

            workers = [
                asyncio.create_task(worker(w_id, queue, context, day_counts))
                for w_id in range(CONCURRENCY)
            ]

            await queue.join()
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers)

            if sum(day_counts.values()) > 0:
                print(f"SUCCESS: Found and synced latest bond data for {target_date} ({sum(day_counts.values())} rows). Stopping search.", flush=True)
                success = True
                break
            else:
                print(f"No bond data published yet for {target_date}, checking previous day...", flush=True)

        await browser.close()
        if not success:
            print("Could not find any published bond data in the last 5 days.", flush=True)

if __name__ == "__main__":
    asyncio.run(scrape_latest_available())
