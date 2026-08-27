async def main():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set.")
        return

    engine = create_engine(DATABASE_URL, connect_args={'prepare_threshold': None})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        base_date = datetime.now()
        success = False

        for i in range(5):
            target_date = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            print(f"Checking T-Bill data for date: {target_date}...", flush=True)
            
            queue = asyncio.Queue()
            queue.put_nowait(target_date)

            workers = [
                asyncio.create_task(worker(w_id, queue, context, engine))
                for w_id in range(CONCURRENCY)
            ]

            # Let worker process
            await queue.join()
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers)

            # If records were written for this date, stop searching further back
            with engine.connect() as conn:
                res = conn.text(f"SELECT COUNT(*) FROM public.daily_bills WHERE \"Data_Date\" = '{target_date}'")
                count = conn.execute(res).scalar()
            
            if count and count > 0:
                print(f"SUCCESS: Found and synced latest T-Bill data for {target_date} ({count} rows). Stopping search.", flush=True)
                success = True
                break
            else:
                print(f"No T-Bill data published yet for {target_date}, checking previous day...", flush=True)

        await browser.close()
        if not success:
            print("Could not find any published T-Bill data in the last 5 days.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
