import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
import redis
from dotenv import load_dotenv
import time

load_dotenv()

app = FastAPI(title="Flash Sale Inventory Tracker")

# Redis connection details
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_USER = os.getenv("REDIS_USER")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# Use a connection pool for efficiency
pool = redis.BlockingConnectionPool(
    max_connections=20,
    timeout=10,
    host=REDIS_HOST,
    port=REDIS_PORT,
    username=REDIS_USER,
    password=REDIS_PASSWORD,
    decode_responses=True
)
r = redis.Redis(connection_pool=pool)

@app.on_event("startup")
def startup():
    try:
        r.ping()
        print("Successfully connected to Redis.")
    except Exception as e:
        print(f"Error connecting to Redis: {e}")

@app.post("/buy/{product_id}")
def buy_product(product_id: str):
    """
    Increments buy request and decrements inventory atomically.
    We use Redis DECR to handle concurrency.
    """
    key = f"inventory:{product_id}"
    
    # 1. Check if product exists in inventory
    if not r.exists(key):
        raise HTTPException(status_code=404, detail="Product not found in inventory.")

    # 2. Use DECR to decrement stock atomically
    # DECR returns the value after decrement
    # Note: If value was 0, DECR returns -1.
    new_stock = r.decr(key)

    if new_stock < 0:
        # Overselling prevented. Reverting the decrement to keep stock at 0 (optional)
        r.incr(key)
        
        # Store the unmet request in a Redis List (acting as a waitlist queue) so it isn't lost
        waitlist_key = f"waitlist:{product_id}"
        r.rpush(waitlist_key, str(time.time()))
        
        raise HTTPException(status_code=400, detail="Out of stock. Added to waitlist.")
    
    return {
        "status": "success",
        "product_id": product_id,
        "remaining_stock": max(0, new_stock),
        "message": f"Successfully purchased {product_id}."
    }

@app.get("/inventory/{product_id}")
def get_inventory(product_id: str):
    stock = r.get(f"inventory:{product_id}")
    if stock is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return {"product_id": product_id, "stock": int(stock)}

@app.get("/", response_class=HTMLResponse)
def root():
    # Fetch first 10 products and their inventory for dashboard display
    with open("hobbygames_full_export.json", "r", encoding="utf-8") as f:
        products = json.load(f)[:10]
    
    inventory_html = ""
    for p in products:
        pid = p.get("details", {}).get("product_code")
        title = p.get("title")
        stock = r.get(f"inventory:{pid}") or "N/A"
        stock_class = 'stock-zero' if stock != "N/A" and int(stock) <= 0 else 'stock-high'
        inventory_html += f"""
            <tr>
                <td>{pid}</td>
                <td>{title}</td>
                <td class='{stock_class}'>{stock}</td>
            </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>High-Throughput Inventory Tracker</title>
            <meta name="description" content="A premium distributed inventory tracking dashboard handling millions of requests with Redis." />
            <style>
                :root {{
                    --bg-dark: #0f172a;
                    --primary: #8b5cf6;
                    --secondary: #ec4899;
                    --surface: rgba(30, 41, 59, 0.7);
                    --text: #f8fafc;
                    --success: #10b981;
                    --danger: #ef4444;
                }}
                body {{ 
                    font-family: 'Inter', sans-serif; 
                    background: radial-gradient(circle at top, #1e1b4b, #09090b);
                    color: var(--text); 
                    display: flex; 
                    justify-content: center; 
                    padding: 40px; 
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{ 
                    width: 100%; 
                    max-width: 1000px; 
                    padding: 40px; 
                    background: var(--surface); 
                    backdrop-filter: blur(20px); 
                    -webkit-backdrop-filter: blur(20px);
                    border-radius: 24px; 
                    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5), inset 0 1px 1px rgba(255,255,255,0.1); 
                    border: 1px solid rgba(255,255,255,0.05); 
                    animation: fadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1);
                }}
                @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(30px); }} to {{ opacity: 1; transform: translateY(0); }} }}
                h1 {{ 
                    font-size: 2.5rem;
                    background: linear-gradient(135deg, #a855f7, #ec4899);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    font-weight: 800; 
                    margin-bottom: 15px; 
                    letter-spacing: -1px; 
                }}
                .header-flex {{ display: flex; justify-content: space-between; align-items: center; margin-top: 40px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 15px; }}
                h2 {{ color: #fff; font-size: 1.4rem; font-weight: 600; margin: 0; }}
                table {{ width: 100%; border-collapse: separate; border-spacing: 0 8px; margin-top: 20px; }}
                th {{ text-align: left; padding: 16px; color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 1.5px; }}
                tr {{ transition: all 0.2s ease-out; }}
                tbody tr {{ background: rgba(255,255,255,0.02); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
                tbody tr:hover {{ background: rgba(255,255,255,0.05); transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.2); }}
                td {{ padding: 16px; color: #e2e8f0; font-size: 0.95rem; }}
                td:first-child {{ border-radius: 12px 0 0 12px; font-family: monospace; color: #c084fc; letter-spacing: 0.5px; }}
                td:last-child {{ border-radius: 0 12px 12px 0; font-weight: 700; font-size: 1.1rem; }}
                
                .hero {{ 
                    padding: 40px; 
                    border-radius: 20px; 
                    margin-bottom: 30px; 
                    color: white; 
                    position: relative;
                    overflow: hidden;
                    background: rgba(15, 23, 42, 0.4);
                    border: 1px solid rgba(139, 92, 246, 0.3);
                    box-shadow: 0 0 40px rgba(139, 92, 246, 0.1);
                }}
                .hero::before {{
                    content: '';
                    position: absolute;
                    top: -50%; left: -50%; width: 200%; height: 200%;
                    background: radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.15) 0%, transparent 60%);
                    animation: rotate 15s linear infinite;
                    pointer-events: none;
                }}
                @keyframes rotate {{ 100% {{ transform: rotate(360deg); }} }}
                .hero-content {{ position: relative; z-index: 10; }}
                .hero p {{ margin: 0; font-size: 1.1rem; color: #cbd5e1; line-height: 1.6; max-width: 600px; }}
                
                .badges {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
                .badge {{ 
                    padding: 6px 14px; 
                    border-radius: 20px; 
                    background: rgba(236, 72, 153, 0.1); 
                    border: 1px solid rgba(236, 72, 153, 0.3);
                    color: #f472b6; 
                    font-size: 0.75rem; 
                    font-weight: 700; 
                    letter-spacing: 1px;
                    text-transform: uppercase;
                }}
                .badge:nth-child(2) {{ background: rgba(56, 189, 248, 0.1); border-color: rgba(56, 189, 248, 0.3); color: #38bdf8; }}
                .badge:nth-child(3) {{ background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.3); color: #34d399; }}
                
                .stock-zero {{ color: var(--danger) !important; text-shadow: 0 0 12px rgba(239,68,68,0.5); }}
                .stock-high {{ color: var(--success) !important; text-shadow: 0 0 12px rgba(16,185,129,0.5); }}
                
                .api-ref {{ margin-top: 40px; padding: 24px; background: rgba(15, 23, 42, 0.6); border-radius: 16px; border-left: 4px solid var(--primary); box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }}
                .api-ref h3 {{ margin-top: 0; color: #fff; font-size: 1.2rem; }}
                .api-ref p {{ color: #cbd5e1; line-height: 1.6; }}
                .api-ref code {{ background: rgba(0,0,0,0.6); padding: 4px 8px; border-radius: 6px; color: #c084fc; font-family: monospace; font-size: 0.9em; }}
                
                .live-indicator {{ display: inline-flex; align-items: center; gap: 8px; font-size: 0.85rem; color: #94a3b8; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; }}
                .dot {{ width: 8px; height: 8px; background: var(--success); border-radius: 50%; box-shadow: 0 0 10px var(--success); animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }}
                @keyframes pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: 0.5; transform: scale(1.3); }} }}
            </style>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        </head>
        <body>
            <div class="container">
                <div class="hero">
                    <div class="hero-content">
                        <h1>Flash Sale Control Room</h1>
                        <div class="badges">
                            <span class="badge">Distributed Cache</span>
                            <span class="badge">Concurrency Control</span>
                            <span class="badge">Millisecond Latency</span>
                        </div>
                        <p>High-throughput distributed inventory tracking using <b>Redis Atomic (DECR)</b>. View real-time stock levels safely decrementing under immense concurrent load.</p>
                    </div>
                </div>
                
                <div class="header-flex">
                    <h2>Live Inventory Feed</h2>
                    <div class="live-indicator"><div class="dot"></div> Live Sync</div>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>Product Code</th>
                            <th>Product Title</th>
                            <th>Stock Level</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inventory_html}
                    </tbody>
                </table>
                
                <div class="api-ref">
                    <h3>API Quick Reference</h3>
                    <p><b>Buy Endpoint:</b> <code>POST /buy/{{product_id}}</code></p>
                    <p><b>Action:</b> To test concurrency, run the <code>stress_test.py</code> script. The database handles race conditions through atomic transactions.</p>
                </div>
            </div>
            <script>
                // Auto refresh every 15 seconds
                setTimeout(() => location.reload(), 15000);
            </script>
        </body>
    </html>
    """
