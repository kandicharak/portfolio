"""
Scrape the Zomato Jammu restaurant listing page for all restaurant cards.

Uses JSON-LD structured data only — no DOM-based Playwright extraction.
"""

import asyncio
import json
import re

from loguru import logger

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import BASE_URL
from scraper.browser import BrowserManager
from utils.delays import scroll_delay
from utils.selectors import find_selector, RESTAURANT_CARD_SELECTORS

# Regex to extract JSON-LD script blocks from raw HTML
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _normalise_restaurant_url(raw_url: str) -> str:
    """
    Normalise a restaurant URL extracted from JSON-LD.

    - Strips any trailing ``/info`` or ``/order`` suffix.
    - If the URL is relative (starts with ``/``), prepends
      ``https://www.zomato.com``.
    - Returns a fully qualified absolute URL.
    """
    url = raw_url.strip()
    # Strip trailing /info or /order segments (guard against double suffixes)
    while url.endswith("/info") or url.endswith("/order"):
        if url.endswith("/info"):
            url = url[: -len("/info")]
        elif url.endswith("/order"):
            url = url[: -len("/order")]
    # Make absolute — every URL must be fully qualified
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.zomato.com{url}"
    # Fallback for bare words (shouldn't happen, but be safe)
    return f"https://www.zomato.com/{url}"


def _extract_name_url(item: dict, accumulator: list[dict]) -> None:
    """
    Extract ``name`` and ``url`` from a single JSON-LD restaurant item.

    Appends a dict with only ``name`` and ``url`` populated; all other
    fields are ``None``.  ``restaurant_detail.py`` will fill those later.
    """
    name = item.get("name")
    raw_url = item.get("url")

    if not name or not raw_url:
        return

    url = _normalise_restaurant_url(raw_url)

    accumulator.append(
        {
            "name": str(name).strip(),
            "url": url,
            "rating": None,
            "price_for_two": None,
            "cuisines": None,
            "delivery_time": None,
        }
    )


async def extract_restaurant_cards(page) -> list[dict]:
    """
    Scrape the main listing page for all restaurant cards.

    **No DOM-based Playwright extraction.**  This function reads the raw
    HTML via ``await page.content()``, extracts every
    ``<script type="application/ld+json">`` block, parses the JSON, and
    looks for items whose ``@type`` contains ``Restaurant`` (either as a
    top-level object or nested inside an ``ItemList`` / ``RestaurantList``).

    Returns a list of dicts with keys:
    *name*, *url*, *rating*, *price_for_two*, *cuisines*, *delivery_time*.

    Only ``name`` and ``url`` are populated; everything else is ``None``.
    The downstream ``restaurant_detail.py`` module is responsible for
    extracting the remaining fields from each restaurant's dedicated page.
    """
    # Get the full page HTML
    html = await page.content()

    restaurants: list[dict] = []

    # First attempt: parse __PRELOADED_STATE__ which often contains full internal URLs
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\(', html)
    if m:
        start = m.end()
        try:
            if html[start] != '"':
                raise ValueError("unexpected preloaded state start")
            end = html.find('")', start)
            if end == -1:
                raise ValueError("preloaded state end not found")
            raw = html[start + 1:end]
            raw = raw.replace('\\"', '"').replace('\\\\', '\\')
            state = json.loads(raw)

            # Look under entities for RESTAURANTS-like dicts
            entities = state.get("entities", {}) if isinstance(state, dict) else {}
            if isinstance(entities, dict):
                for key in ("RESTAURANTS", "RESTAURANT", "RETAIL_ENTITY", "RETAIL"):
                    node = entities.get(key)
                    if isinstance(node, dict):
                        for rid, robj in node.items():
                            if not isinstance(robj, dict):
                                continue
                            name = robj.get("name") or robj.get("title")
                            raw_url = robj.get("url") or robj.get("restaurant_url") or robj.get("link") or robj.get("slug")
                            if raw_url:
                                url = _normalise_restaurant_url(str(raw_url))
                                restaurants.append({
                                    "name": str(name).strip() if name else None,
                                    "url": url,
                                    "rating": None,
                                    "price_for_two": None,
                                    "cuisines": None,
                                    "delivery_time": None,
                                })
            # Also try pages.current.restaurants
            pages_current = state.get("pages", {}).get("current", {}) if isinstance(state, dict) else {}
            if isinstance(pages_current, dict):
                pr = pages_current.get("restaurants") or pages_current.get("restaurantList") or pages_current.get("restaurantsList")
                if isinstance(pr, list):
                    for entry in pr:
                        if not isinstance(entry, dict):
                            continue
                        name = entry.get("name") or entry.get("title")
                        raw_url = entry.get("url") or entry.get("link") or entry.get("slug")
                        if raw_url:
                            url = _normalise_restaurant_url(str(raw_url))
                            restaurants.append({
                                "name": str(name).strip() if name else None,
                                "url": url,
                                "rating": None,
                                "price_for_two": None,
                                "cuisines": None,
                                "delivery_time": None,
                            })
        except Exception:
            # Fall back to JSON-LD parsing below
            logger.debug("Preloaded state parse failed — falling back to JSON-LD")

    # If preloaded-state yielded results, dedupe and return them
    if restaurants:
        # dedupe by url
        seen = set()
        uniq = []
        for r in restaurants:
            if r.get("url") and r["url"] not in seen:
                seen.add(r["url"])
                uniq.append(r)
        logger.info(f"Extracted {len(uniq)} restaurants from preloaded state")
        return uniq

    # Fallback: Extract all JSON-LD script blocks and parse Restaurant entries
    matches = _JSONLD_RE.findall(html)
    if not matches:
        logger.warning("No <script type='application/ld+json'> blocks found on the page")
        return []

    for block_text in matches:
        try:
            data = json.loads(block_text.strip())
        except json.JSONDecodeError as exc:
            logger.debug(f"Failed to parse JSON-LD block: {exc}")
            continue

        # The JSON-LD may be a single object or an array
        items = data if isinstance(data, list) else [data]

        for item in items:
            item_type = item.get("@type", "")

            # Normalise @type to a flat string for easy matching
            if isinstance(item_type, list):
                type_str = " ".join(item_type)
            else:
                type_str = str(item_type)

            # Direct Restaurant entry
            if "Restaurant" in type_str:
                _extract_name_url(item, restaurants)
            # ItemList / RestaurantList containing restaurant entries
            elif "ItemList" in type_str or "RestaurantList" in type_str:
                for element in item.get("itemListElement", []):
                    rest_item = element.get("item") or element
                    _extract_name_url(rest_item, restaurants)

    logger.info(f"Extracted {len(restaurants)} restaurants from JSON-LD structured data")
    return restaurants


async def scroll_to_load_all(page, max_cards: int = 5000) -> int:
    """
    Scroll down in chunks until no new cards load or max_cards is reached.
    """
    previous_count = 0
    no_change_count = 0

    while no_change_count < 5:  # Give it more chances to load
        await page.evaluate("window.scrollBy(0, 1500)")
        await asyncio.sleep(2) # Faster but steady

        active_selector = await find_selector(page, RESTAURANT_CARD_SELECTORS)
        if not active_selector:
            logger.warning("Card selector lost during scroll — stopping")
            break

        current_count = await page.locator(active_selector).count()
        
        if current_count >= max_cards:
            logger.info(f"Reached massive card limit ({max_cards}) — proceeding")
            return current_count

        if current_count == previous_count:
            no_change_count += 1
            logger.debug(f"Scroll round — no change ({no_change_count}/5), count={current_count}")
        else:
            no_change_count = 0
            logger.debug(f"Scroll round — new cards loaded, count={current_count}")

        previous_count = current_count

    logger.info(f"Finished scrolling — total restaurants found: {previous_count}")
    return previous_count


async def _main() -> None:
    """Smoke-test: navigate to Zomato Jammu, scroll, and print restaurant cards."""
    async with BrowserManager() as bm:
        logger.info(f"Navigating to {BASE_URL} …")
        await bm.page.goto(BASE_URL, wait_until="domcontentloaded")

        total = await scroll_to_load_all(bm.page)
        cards = await extract_restaurant_cards(bm.page)

        print(f"\n{'='*60}")
        print(f"Found {total} restaurant cards on the page")
        print(f"Extracted {len(cards)} restaurant details")
        print(f"{'='*60}\n")

        for i, card in enumerate(cards, start=1):
            print(f"{i:>3}. {card['name']}")
            print(f"     URL  : {card['url']}")
            print(f"     Rating: {card['rating']}")
            print(f"     Price : {card['price_for_two']}")
            print(f"     Cuisines: {card['cuisines']}")
            print(f"     Time  : {card['delivery_time']}")
            print()

        print(f"{'='*60}")
        print(f"Total restaurants extracted: {len(cards)}")


if __name__ == "__main__":
    asyncio.run(_main())
