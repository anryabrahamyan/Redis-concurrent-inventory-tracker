# High-Throughput Inventory Tracker (Assignment 2)

This project implements a high-throughput inventory system for a flash-sale event where thousands of users attempt to buy a limited stock of items simultaneously.

## Features
- **FastAPI Backend**: Efficiently handles incoming buy requests.
- **Distributed Caching (Redis Remote)**: Uses atomic operations (`DECR`) to manage inventory without race conditions.
- **Concurrency Control**: Prevents overselling by ensuring the stock never drops below zero, even under heavy parallel load.
- **Stress Test & Metrics**: A simulation script that measures throughput (requests/sec) and verifies the final inventory count.

## Project Structure
- `app.py`: The FastAPI application.
- `init_redis.py`: Populates Redis with sample product data from `hobbygames_full_export.json`.
- `stress_test.py`: A script using `asyncio` and `httpx` to simulate a flood of buy requests.
- `.env`: Contains Redis Cloud credentials (already configured).

## Installation
Recommended to use a virtual environment:
```bash
pip install -r requirements.txt
```

## Running the System
1. **Initialize Inventory**:
   ```bash
   python init_redis.py
   ```
2. **Start the FastAPI Server**:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```
3. **Run Stress Test**:
   ```bash
   python stress_test.py
   ```

## Concurrency Note
We use `r.decr(key)` which is an atomic operation in Redis. It decrements the value of a key and returns the result at the same time. This is much faster and safer than traditional "GET-Modify-SET" patterns because it happens entirely on the Redis server's single-threaded event loop, effectively acting as a distributed lock without the overhead of lock management.

## Handling Redis Cloud Client Limits
When working with free-tier cloud databases like Redis Cloud, there is often a strict limitation on the maximum number of concurrent client connections (e.g., 30 active connections). During a stress test or a flash-sale event, sudden bursts of traffic can easily overwhelm this limit, resulting in `redis.exceptions.ConnectionError: max number of clients reached` and dropped requests.

To overcome this bottleneck, we use `redis.BlockingConnectionPool` in our FastAPI application with a fixed `max_connections` cap (e.g., set to `20`). This enforces a strict bound on the connections our application can open. When traffic spikes beyond this threshold, the connection pool acts as a bouncer, politely queuing incoming requests to wait up to a few seconds for a connection to free up rather than failing outright. This prevents 500 Internal Server errors, protects the remote database from being overwhelmed by a connection storm, and leaves a safe buffer of open connection slots for external services (like our `stress_test.py` script) to successfully connect and monitor the final inventory.

## Waitlist/Backorder Queue Implementation
When stock eventually drops completely to zero (`new_stock < 0`), we don't just blindly drop or fail incoming user requests!
To prevent permanently losing legitimate consumer intent, our endpoints dynamically intercept these "Out Of Stock" events and save the request details (like timestamp profiles) directly to a newly partitioned **Redis List** representing a `waitlist:<product_id>`.