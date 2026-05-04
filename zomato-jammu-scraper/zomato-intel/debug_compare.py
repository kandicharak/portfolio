import asyncio
import json
import re
from playwright.async_api import async_playwright

async def debug_page(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"\n--- Checking URL: {url} ---")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = await page.content()
            
            # 1. Check JSON-LD
            json_ld_re = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
            for block in json_ld_re.findall(content):
                try:
                    data = json.loads(block.strip())
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if "Restaurant" in str(item.get("@type", "")):
                            print("Found Restaurant JSON-LD:")
                            print(f"  Name: {item.get('name')}")
                            print(f"  PriceRange: {item.get('priceRange')}")
                except: pass

            # 2. Check Preloaded State
            m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\("(.*?)"\)\s*;', content, re.DOTALL)
            if m:
                raw = m.group(1).replace('\\"', '"').replace('\\\\', '\\')
                state = json.loads(raw)
                
                def deep_search(obj, key):
                    found = []
                    def _recurse(sub):
                        if isinstance(sub, dict):
                            for k, v in sub.items():
                                if k == key: found.append(v)
                                else: _recurse(v)
                        elif isinstance(sub, list):
                            for item in sub: _recurse(item)
                    _recurse(obj)
                    return found

                ratings = deep_search(state, "rating_new") or deep_search(state, "aggregate_rating")
                if ratings:
                    print(f"Found {len(ratings)} Rating Objects in Preloaded State.")
                    print(json.dumps(ratings[0], indent=2))
                else:
                    print("No Rating Objects found in Preloaded State.")
            else:
                print("Preloaded state not found.")
        except Exception as e:
            print(f"Error: {e}")
        
        await browser.close()

async def main():
    base = "https://www.zomato.com/jammu/starbucks-coffee-1-trinity-tower-jammu"
    await debug_page(base)
    await debug_page(base + "/reviews")

if __name__ == "__main__":
    asyncio.run(main())
