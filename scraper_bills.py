async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set.")
        return

    engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Generate the last 5 days (e.g. today and recent past days to bypass holidays/weekends)
        base_date = datetime.now()
        date_list = [(base_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]

        print(f"Checking recent dates for publishing availability: {date_list}")

        queue = asyncio.Queue()
        for d in date_list:
            queue.put_nowait(d)

        workers = [
            asyncio.create_task(worker(i, queue, context, engine))
            for i in range(CONCURRENCY)
        ]

        await queue.join()
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
        await browser.close()
        print("Scrape & Database Sync Complete!", flush=True)
