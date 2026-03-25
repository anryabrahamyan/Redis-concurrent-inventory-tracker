import json
import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_USER = os.getenv("REDIS_USER")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

def init_inventory():
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            username=REDIS_USER,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
        
        # Test connection
        r.ping()
        print("Successfully connected to Redis.")

        # Clean up Redis before populating
        print("Flushing existing Redis database...")
        r.flushdb()

        # Load product data
        with open("hobbygames_full_export.json", "r", encoding="utf-8") as f:
            products = json.load(f)

        # Set initial inventory for each product
        # The key in Redis will be "inventory:{product_code}"
        # Setting initial inventory to 1000 items as requested (more than 500)
        initial_stock = 1000
        count = 0
        for p in products:
            product_code = p.get("details", {}).get("product_code")
            if product_code:
                # We use set only if it doesn't exist, or just overwrite for initialization
                r.set(f"inventory:{product_code}", initial_stock)
                count += 1
        
        print(f"Initialized inventory for {count} products with {initial_stock} items each.")

    except Exception as e:
        print(f"Error initializing inventory: {e}")

if __name__ == "__main__":
    init_inventory()
