import asyncio
import json
import re
from playwright.async_api import async_playwright

async def debug_rating(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded")
        content = await page.content()
        
        # Find preloaded state
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

            ratings = deep_search(state, "rating_new")
            if not ratings:
                ratings = deep_search(state, "aggregate_rating")
            
            print("Found Rating Objects:")
            for r in ratings:
                print(json.dumps(r, indent=2))
        else:
            print("Preloaded state not found")
        
        await browser.close()

if __name__ == "__main__":
    test_url = "https://www.zomato.com/jammu/starbucks-coffee-1-trinity-tower-jammu"
    asyncio.run(debug_rating(test_url))
