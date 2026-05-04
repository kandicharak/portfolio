"""
Extract detailed information from a single Zomato restaurant page.

Uses JSON-LD structured data as the primary source, with DOM-based
Playwright extraction as a fallback for fields not found in JSON-LD.
Also performs deep recursive search of the ``__PRELOADED_STATE__`` JSON
for latitude, longitude, votes, and highlights.
"""

import asyncio
import json
import re
from typing import Optional

from loguru import logger

from config import BASE_URL
from scraper.browser import BrowserManager
from utils.delays import human_delay, human_like_click, micro_delay
from utils.selectors import (
    ADDRESS_SELECTORS,
    CUISINE_SELECTORS,
    PRICE_FOR_TWO_SELECTORS,
    RATING_SELECTORS,
    RESTAURANT_NAME_SELECTORS,
    RESTAURANT_PHONE_SELECTORS,
    TIMING_SELECTORS,
    find_selector,
)

# Regex to extract JSON-LD script blocks from raw HTML
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_json_ld(html: str) -> Optional[dict]:
    """
    Parse the first ``@type: Restaurant`` JSON-LD block from the page HTML.

    Returns the parsed dict, or ``None`` if no Restaurant JSON-LD is found.
    """
    for block_text in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block_text.strip())
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                type_str = " ".join(item_type)
            else:
                type_str = str(item_type)
            if "Restaurant" in type_str:
                return item
    return None


# Regex to extract __PRELOADED_STATE__ JSON from HTML
_PRELOADED_STATE_RE = re.compile(
    r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\("(.*?)"\)\s*;',
    re.DOTALL,
)


def _parse_preloaded_state(html: str) -> Optional[dict]:
    """Parse the ``__PRELOADED_STATE__`` JSON from the page HTML."""
    m = _PRELOADED_STATE_RE.search(html)
    if not m:
        return None
    try:
        raw = m.group(1)
        raw = raw.replace('\\"', '"').replace('\\\\', '\\')
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return None


def _deep_search(obj, target_key: str, case_sensitive: bool = True) -> list:
    """
    Recursively search for *all* values matching *target_key* in a nested
    dict / list structure.

    Returns a list of values found (any depth).  Matching is done against
    the *exact* key name by default; set ``case_sensitive=False`` for a
    case‑insensitive match.
    """
    found: list = []

    def _recurse(sub):
        if isinstance(sub, dict):
            for k, v in sub.items():
                if case_sensitive:
                    key_match = k == target_key
                else:
                    key_match = k.lower() == target_key.lower()
                if key_match:
                    found.append(v)
                else:
                    _recurse(v)
        elif isinstance(sub, list):
            for item in sub:
                _recurse(item)

    _recurse(obj)
    return found


async def extract_restaurant_detail(page, restaurant_url: str) -> dict:
    """
    Navigate to a single restaurant page and extract:
    - name, phone, price_for_two, rating
    - cuisines, address, open_status, timings
    - latitude, longitude, exact_votes, highlights

    Uses JSON-LD structured data as the primary source, with DOM-based
    Playwright extraction as fallback.  Also performs a deep recursive
    search of the ``__PRELOADED_STATE__`` JSON for lat/long, votes, and
    highlights.

    Returns a dict with those fields (``None`` for missing values).
    """
    data: dict[str, Optional[str]] = {
        "name": None,
        "phone": None,
        "price_for_two": None,
        "rating": None,
        "cuisines": None,
        "address": None,
        "open_status": None,
        "timings": None,
        "latitude": None,
        "longitude": None,
        "exact_votes": None,
        "dining_rating": None,
        "dining_votes": None,
        "delivery_rating": None,
        "delivery_votes": None,
        "highlights": None,
    }

    try:
        # 1. Navigate to URL
        logger.info("Navigating to restaurant page: {}", restaurant_url)
        await page.goto(restaurant_url)

        # 2. Wait for content to load
        await page.wait_for_load_state("domcontentloaded")

        # 3. Human-like pause after page load (Reduced for Speed Mode)
        await human_delay(1, 3)

        # 4. Extract JSON-LD structured data (primary source)
        html = await page.content()
        json_ld = _parse_json_ld(html)

        if json_ld:
            logger.info("Found Restaurant JSON-LD structured data")

            # Name from JSON-LD
            if json_ld.get("name"):
                data["name"] = str(json_ld["name"]).strip()

            # Phone from JSON-LD
            if json_ld.get("telephone"):
                data["phone"] = str(json_ld["telephone"]).strip()

            # Price for two from JSON-LD (e.g. "₹400 for two people (approx.)")
            if json_ld.get("priceRange"):
                data["price_for_two"] = str(json_ld["priceRange"]).strip()

            # Rating from JSON-LD aggregateRating
            agg_rating = json_ld.get("aggregateRating", {})
            if isinstance(agg_rating, dict) and agg_rating.get("ratingValue"):
                data["rating"] = str(agg_rating["ratingValue"]).strip()

            # Cuisines from JSON-LD (e.g. "Street Food, Fast Food, Chinese, Beverages")
            if json_ld.get("servesCuisine"):
                data["cuisines"] = str(json_ld["servesCuisine"]).strip()

            # Address from JSON-LD
            address = json_ld.get("address", {})
            if isinstance(address, dict) and address.get("streetAddress"):
                data["address"] = str(address["streetAddress"]).strip()

            # Opening hours / timings from JSON-LD
            if json_ld.get("openingHours"):
                data["timings"] = str(json_ld["openingHours"]).strip()
                # Determine open/closed status
                if "open" in data["timings"].lower():
                    data["open_status"] = "Open"
                elif "closed" in data["timings"].lower():
                    data["open_status"] = "Closed"

        # 5. Deep recursive search of __PRELOADED_STATE__ JSON
        #    (Zomato moves fields around frequently — deep search is more robust)
        state = _parse_preloaded_state(html)
        if state:
            logger.info("Found __PRELOADED_STATE__ — performing deep recursive search")

            # ── Latitude / Longitude ────────────────────────────────────
            # Deep search for 'latitude' and 'longitude' keys anywhere in the
            # state object (e.g. under pages.restaurant.{resId}.sections.SECTION_RES_CONTACT)
            lat_values = _deep_search(state, "latitude")
            if lat_values and data["latitude"] is None:
                # Take the first non-None, numeric-looking value
                for v in lat_values:
                    if v is not None and str(v).strip():
                        data["latitude"] = str(v).strip()
                        break

            lon_values = _deep_search(state, "longitude")
            if lon_values and data["longitude"] is None:
                for v in lon_values:
                    if v is not None and str(v).strip():
                        data["longitude"] = str(v).strip()
                        break

            # ── Ratings & Votes (Dining vs Delivery) ──────────────────────
            # Try Preloaded State first
            for vote_key in ("aggregate_rating", "rating_new", "rating"):
                agg_ratings = _deep_search(state, vote_key)
                for ar in agg_ratings:
                    if isinstance(ar, dict):
                        dining = ar.get("dining")
                        if isinstance(dining, dict):
                            data["dining_rating"] = str(dining.get("rating") or "").strip() or data["dining_rating"]
                            data["dining_votes"] = str(dining.get("votes") or "").strip() or data["dining_votes"]
                        delivery = ar.get("delivery")
                        if isinstance(delivery, dict):
                            data["delivery_rating"] = str(delivery.get("rating") or "").strip() or data["delivery_rating"]
                            data["delivery_votes"] = str(delivery.get("votes") or "").strip() or data["delivery_votes"]

            # DOM-based Fallback for Ratings (Live site uses specific labels)
            if not data["dining_rating"] or not data["delivery_rating"]:
                try:
                    # Find containers for Dining/Delivery ratings
                    rating_boxes = await page.locator("div:has-text('Ratings')").all()
                    for box in rating_boxes:
                        text = await box.inner_text()
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        
                        target_data = None
                        if "Dining Ratings" in text: target_data = ("dining_rating", "dining_votes")
                        elif "Delivery Ratings" in text: target_data = ("delivery_rating", "delivery_votes")
                        
                        if target_data:
                            r_key, v_key = target_data
                            # Lines usually: ["4.5", "2,334", "Dining Ratings"] OR ["2,334", "Dining Ratings"]
                            for l in lines:
                                if re.match(r'^[1-5]\.[0-9]$|^[1-5]$', l): # It's a rating
                                    data[r_key] = l
                                elif re.search(r'[\d,kK]+', l) and "Ratings" not in l: # It's a vote count
                                    data[v_key] = l
                except Exception: pass

            # ── Highlights ──────────────────────────────────────────────
            # Search for HIGHLIGHTS (exact) or highlights (case-insensitive)
            # and join text / name fields with commas
            raw_highlights = _deep_search(state, "HIGHLIGHTS", case_sensitive=True)
            if not raw_highlights:
                raw_highlights = _deep_search(state, "highlights", case_sensitive=False)

            for hlist in raw_highlights:
                if isinstance(hlist, list):
                    texts = []
                    for h in hlist:
                        if isinstance(h, dict):
                            txt = h.get("text") or h.get("name") or h.get("title")
                        elif isinstance(h, str):
                            txt = h
                        else:
                            txt = None
                        if txt and str(txt).strip():
                            texts.append(str(txt).strip())
                    if texts:
                        data["highlights"] = ", ".join(texts)
                        break
                elif isinstance(hlist, str):
                    data["highlights"] = hlist
                    break

        # 6. DOM-based fallback for any fields still missing
        #    (JSON-LD is preferred, but DOM extraction can catch edge cases)

        # Name fallback
        if data["name"] is None:
            name_selector = await find_selector(page, RESTAURANT_NAME_SELECTORS)
            if name_selector:
                try:
                    name = await page.locator(name_selector).first.text_content()
                    if name:
                        data["name"] = name.strip()
                except Exception:
                    logger.warning("Could not extract restaurant name from DOM")

        # Phone fallback
        if data["phone"] is None:
            phone_selector = await find_selector(page, RESTAURANT_PHONE_SELECTORS)
            if phone_selector:
                try:
                    phone = await page.locator(phone_selector).first.text_content()
                    if phone and phone.strip():
                        data["phone"] = phone.strip()
                except Exception:
                    logger.debug("Phone not directly visible — trying Call button")

            # If not found, look for a "Call" button and click it to reveal
            if data["phone"] is None:
                try:
                    call_button = page.locator(
                        "button:has-text('Call'), a:has-text('Call'), "
                        "button[class*='call'], a[class*='call']"
                    )
                    if await call_button.count() > 0:
                        await human_like_click(page, call_button)
                        await micro_delay()
                        phone_selector = await find_selector(page, RESTAURANT_PHONE_SELECTORS)
                        if phone_selector:
                            phone = await page.locator(phone_selector).first.text_content()
                            if phone:
                                data["phone"] = phone.strip()
                except Exception as e:
                    logger.warning("Failed to reveal phone number: {}", e)

        # Price for two fallback
        if data["price_for_two"] is None:
            price_selector = await find_selector(page, PRICE_FOR_TWO_SELECTORS)
            if price_selector:
                try:
                    price = await page.locator(price_selector).first.text_content()
                    if price:
                        data["price_for_two"] = price.strip()
                except Exception:
                    logger.warning("Could not extract price for two from DOM")

        # Rating fallback
        if data["rating"] is None:
            rating_selector = await find_selector(page, RATING_SELECTORS)
            if rating_selector:
                try:
                    rating = await page.locator(rating_selector).first.get_attribute(
                        "aria-label"
                    )
                    if not rating:
                        rating = await page.locator(rating_selector).first.text_content()
                    if rating:
                        data["rating"] = rating.strip()
                except Exception:
                    logger.warning("Could not extract rating from DOM")

        # Cuisines fallback
        if data["cuisines"] is None:
            cuisines_selector = await find_selector(page, CUISINE_SELECTORS)
            if cuisines_selector:
                try:
                    cuisine_els = page.locator(cuisines_selector)
                    cuisine_texts = await cuisine_els.all_text_contents()
                    if cuisine_texts:
                        data["cuisines"] = ", ".join(
                            [c.strip() for c in cuisine_texts if c.strip()]
                        )
                except Exception:
                    logger.warning("Could not extract cuisines from DOM")

        # Address fallback
        if data["address"] is None:
            address_selector = await find_selector(page, ADDRESS_SELECTORS)
            if address_selector:
                try:
                    address_el = page.locator(address_selector).first
                    address = await address_el.text_content()
                    if address:
                        data["address"] = address.strip()
                except Exception:
                    logger.warning("Could not extract address from DOM")

        # Open/closed status and timings fallback
        if data["open_status"] is None and data["timings"] is None:
            timing_selector = await find_selector(page, TIMING_SELECTORS)
            if timing_selector:
                try:
                    timing_el = page.locator(timing_selector).first
                    timing_text = await timing_el.text_content()
                    if timing_text:
                        timing_text = timing_text.strip()
                        if "open" in timing_text.lower():
                            data["open_status"] = "Open"
                            data["timings"] = timing_text
                        elif "closed" in timing_text.lower():
                            data["open_status"] = "Closed"
                            data["timings"] = timing_text
                        else:
                            data["timings"] = timing_text
                except Exception:
                    logger.warning("Could not extract timing information from DOM")

    except Exception as e:
        logger.warning("Error extracting detail from {}: {}", restaurant_url, e)

    return data


if __name__ == "__main__":

    async def main() -> None:
        """Test extract_restaurant_detail with a hardcoded URL."""
        async with BrowserManager() as browser:
            test_url = "https://www.zomato.com/jammu/samosa-junction-gandhi-nagar"
            result = await extract_restaurant_detail(browser.page, test_url)
            print(result)

    asyncio.run(main())
