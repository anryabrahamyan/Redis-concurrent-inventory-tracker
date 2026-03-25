import asyncio
import httpx
import time
import json
import os
import redis
from dotenv import load_dotenv

load_dotenv()

import random

# We need to know a few product_ids from the JSON to target randomly
with open("hobbygames_full_export.json", "r", encoding="utf-8") as f:
    products = json.load(f)
    # Grab the first 5 product codes for the test
    ALL_PRODUCT_IDS = [p.get("details", {}).get("product_code") for p in products if p.get("details", {}).get("product_code")][:5]

URL = "http://127.0.0.1:8000"
TOTAL_REQUESTS = 2000 # Distribute requests across the 5 products
CONCURRENT_USERS = 50

# Reuse Redis connection to check final state
r = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=os.getenv("REDIS_PORT"),
    username=os.getenv("REDIS_USER"),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True
)

async def buy(client, i, sem, product_id):
    async with sem:
        try:
            resp = await client.post(f"{URL}/buy/{product_id}")
            return resp.status_code, resp.json()
        except Exception as e:
            return 500, str(e)

async def run_stress_test():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Starting stress test: {TOTAL_REQUESTS} requests with {CONCURRENT_USERS} concurrent users.")
        start_time = time.time()
        
        # Split into chunks of concurrent users using a Semaphore
        sem = asyncio.Semaphore(CONCURRENT_USERS)
        tasks = []
        for i in range(TOTAL_REQUESTS):
            target_pid = random.choice(ALL_PRODUCT_IDS)
            tasks.append(buy(client, i, sem, target_pid))
        
        results = []
        done_count = 0
        for coro in asyncio.as_completed(tasks):
            res = await coro
            results.append(res)
            done_count += 1
            if done_count % 10 == 0 or done_count == TOTAL_REQUESTS:
                elapsed = time.time() - start_time
                print(f"[{elapsed:.2f}s] Completed {done_count}/{TOTAL_REQUESTS} requests...", end="\\r")
        
        print()  # clear line after progress finishes
        end_time = time.time()
        
        duration = end_time - start_time
        success_count = sum(1 for status, _ in results if status == 200)
        failed_count = sum(1 for status, _ in results if status == 400)
        error_count = sum(1 for status, _ in results if status == 500)
        
        throughput = TOTAL_REQUESTS / duration if duration > 0 else 0
        
        print("\n" + "="*50)
        print("STRESS TEST RESULTS")
        print("="*50)
        print(f"Products Targeted:  {len(ALL_PRODUCT_IDS)} unique items")
        print(f"Total Requests:     {TOTAL_REQUESTS}")
        print(f"Duration:           {duration:.2f} seconds")
        print(f"Throughput:         {throughput:.2f} requests/sec")
        print(f"Successfully Bought: {success_count}")
        print(f"Failed (Sold Out):  {failed_count}")
        print(f"Errors:             {error_count}")
        print("="*50)
        
        # Verify final stock in Redis
        print("\nFinal stock in Redis for all targeted products:")
        overselling = False
        for pid in ALL_PRODUCT_IDS:
            final_stock = r.get(f"inventory:{pid}")
            waitlist_count = r.llen(f"waitlist:{pid}")
            print(f"Product [{pid}]: Stock = {final_stock} | Waitlist Queue = {waitlist_count} people")
            if final_stock is not None and int(final_stock) < 0:
                overselling = True
                
        if not overselling:
            print("\nStatus: No overselling detected anywhere! Atomic operations and Waitlists working correctly.")
        else:
            print("\nStatus: OVERSELLING DETECTED! Race condition happened.")

if __name__ == "__main__":
    # Check if the server is running or if the user needs to start it
    # We can try to ping the server first or just run it synchronously
    asyncio.run(run_stress_test())
