"""
Extract reviews from a Zomato restaurant page.

Zomato reviews are loaded dynamically on a dedicated ``/reviews`` page.
This module navigates to that page and attempts to extract review data
from the ``__PRELOADED_STATE__`` JSON, with DOM-based fallback.
"""

import asyncio
import json
import re

from loguru import logger

from config import MAX_REVIEWS
from utils.delays import human_delay, scroll_delay, human_like_click
from utils.selectors import REVIEW_TEXT_SELECTORS, REVIEW_RATING_SELECTORS, find_selector


def _extract_reviews_from_preloaded_state(html: str, max_reviews: int) -> list[dict]:
    """
    Attempt to extract reviews from the ``__PRELOADED_STATE__`` JSON.

    Checks multiple key paths Zomato uses to store review data:
      1. ``restaurant.{resId}.sections.SECTION_REVIEWS``
      2. ``restaurant.{resId}.sections.SECTION_REVIEW``
      3. ``restaurant.{resId}.reviews``
      4. ``pages.current.reviews``
      5. ``entities.REVIEWS``
      6. ``reviews`` (top-level)

    Uses flexible field name matching for the review text
    (``review_text``, ``reviewText``, ``text``, ``content``, ``comment``, ``reviewContent``).

    Returns a list of dicts with keys:
    ``review_text``, ``rating``, ``review_order``.
    """
    reviews: list[dict] = []

    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\(', html)
    if not m:
        return reviews

    start = m.end()
    if html[start] != '"':
        return reviews

    end = html.find('")', start)
    if end == -1:
        return reviews

    try:
        raw = html[start + 1:end]
        raw = raw.replace('\\"', '"').replace('\\\\', '\\')
        state = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return reviews

    # ── Helper: flexible field matching ────────────────────────────
    TEXT_FIELDS = ("review_text", "reviewText", "text", "content", "comment", "reviewContent", "description")
    RATING_FIELDS = ("rating", "ratingValue", "rating_v2", "rate")
    NAME_FIELDS = ("user_name", "userName", "name", "username", "reviewer_name", "reviewerName")
    TIMESTAMP_FIELDS = ("timestamp", "review_time", "reviewTime", "date", "created_at", "createdAt", "review_date", "reviewDate")

    def _get_text(rd: dict) -> str | None:
        for f in TEXT_FIELDS:
            val = rd.get(f)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def _get_rating(rd: dict) -> float | None:
        for f in RATING_FIELDS:
            val = rd.get(f)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    if isinstance(val, dict):
                        # rating might be nested (e.g. {"ratingValue": 4.0})
                        for nested_field in ("ratingValue", "value", "aggregate_rating"):
                            nv = val.get(nested_field)
                            if nv is not None:
                                try:
                                    return float(nv)
                                except (ValueError, TypeError):
                                    pass
        return None

    def _get_reviewer_name(rd: dict) -> str | None:
        # Check direct name fields first
        for f in NAME_FIELDS:
            val = rd.get(f)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        # Check if name is nested under a "user" object
        user = rd.get("user", {})
        if isinstance(user, dict):
            for f in ("name", "user_name", "userName"):
                val = user.get(f)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    def _get_timestamp(rd: dict) -> str | None:
        for f in TIMESTAMP_FIELDS:
            val = rd.get(f)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    # Log available top-level keys for debugging
    logger.debug("PRELOADED_STATE top-level keys: {}", list(state.keys()))

    # ── Path 1: restaurant.{resId}.sections.SECTION_REVIEWS ─────────
    restaurant_data = state.get("restaurant", {})
    if isinstance(restaurant_data, dict):
        for res_id, res_obj in restaurant_data.items():
            if not isinstance(res_obj, dict):
                continue
            sections = res_obj.get("sections", {})
            if not isinstance(sections, dict):
                continue
            # Try known review section names
            for section_key in ("SECTION_REVIEWS", "SECTION_REVIEW", "SECTION_REVIEWS_LIST"):
                section = sections.get(section_key, {})
                if not isinstance(section, dict):
                    continue
                # Could be a list of reviews directly, or have entities/reviews sub-key
                for candidate_key in ("reviews", "entities", "reviewList", "list", "data"):
                    candidate = section.get(candidate_key)
                    if candidate is None:
                        continue
                    if isinstance(candidate, dict):
                        for review_id, review_data in candidate.items():
                            if not isinstance(review_data, dict):
                                continue
                            text = _get_text(review_data)
                            if text:
                                reviews.append({
                                    "review_text": text,
                                    "rating": _get_rating(review_data),
                                    "review_order": len(reviews) + 1,
                                    "reviewer_name": _get_reviewer_name(review_data),
                                    "review_timestamp": _get_timestamp(review_data),
                                })
                                if len(reviews) >= max_reviews:
                                    return reviews
                    elif isinstance(candidate, list):
                        for review_data in candidate:
                            if not isinstance(review_data, dict):
                                continue
                            text = _get_text(review_data)
                            if text:
                                reviews.append({
                                    "review_text": text,
                                    "rating": _get_rating(review_data),
                                    "review_order": len(reviews) + 1,
                                    "reviewer_name": _get_reviewer_name(review_data),
                                    "review_timestamp": _get_timestamp(review_data),
                                })
                                if len(reviews) >= max_reviews:
                                    return reviews

    if reviews:
        logger.debug("Extracted {} reviews from restaurant.sections", len(reviews))
        return reviews

    # ── Path 2: restaurant.{resId}.reviews (direct) ─────────────────
    if isinstance(restaurant_data, dict):
        for res_id, res_obj in restaurant_data.items():
            if not isinstance(res_obj, dict):
                continue
            direct_reviews = res_obj.get("reviews")
            if isinstance(direct_reviews, list):
                for review_data in direct_reviews:
                    if not isinstance(review_data, dict):
                        continue
                    text = _get_text(review_data)
                    if text:
                        reviews.append({
                            "review_text": text,
                            "rating": _get_rating(review_data),
                            "review_order": len(reviews) + 1,
                            "reviewer_name": _get_reviewer_name(review_data),
                            "review_timestamp": _get_timestamp(review_data),
                        })
                        if len(reviews) >= max_reviews:
                            return reviews

    if reviews:
        logger.debug("Extracted {} reviews from restaurant.reviews", len(reviews))
        return reviews

    # ── Path 3: pages.current.reviews ─────────────────────────────
    current = state.get("pages", {}).get("current", {})
    page_reviews = current.get("reviews")
    if isinstance(page_reviews, list):
        for review_data in page_reviews:
            if not isinstance(review_data, dict):
                continue
            text = _get_text(review_data)
            if text:
                reviews.append({
                    "review_text": text,
                    "rating": _get_rating(review_data),
                    "review_order": len(reviews) + 1,
                    "reviewer_name": _get_reviewer_name(review_data),
                    "review_timestamp": _get_timestamp(review_data),
                })
                if len(reviews) >= max_reviews:
                    return reviews

    if reviews:
        logger.debug("Extracted {} reviews from pages.current.reviews", len(reviews))
        return reviews

    # ── Path 4: entities.REVIEWS (legacy path) ────────────────────
    entities = state.get("entities", {})
    if isinstance(entities, dict):
        for entity_key in ("REVIEWS", "reviews", "REVIEW", "review"):
            entity_reviews = entities.get(entity_key, {})
            if isinstance(entity_reviews, dict):
                for review_id, review_data in entity_reviews.items():
                    if not isinstance(review_data, dict):
                        continue
                    text = _get_text(review_data)
                    if text:
                        reviews.append({
                            "review_text": text,
                            "rating": _get_rating(review_data),
                            "review_order": len(reviews) + 1,
                            "reviewer_name": _get_reviewer_name(review_data),
                            "review_timestamp": _get_timestamp(review_data),
                        })
                        if len(reviews) >= max_reviews:
                            return reviews

    if reviews:
        logger.debug("Extracted {} reviews from entities", len(reviews))
        return reviews

    # ── Path 5: top-level "reviews" key ────────────────────────────
    top_reviews = state.get("reviews")
    if isinstance(top_reviews, list):
        for review_data in top_reviews:
            if not isinstance(review_data, dict):
                continue
            text = _get_text(review_data)
            if text:
                reviews.append({
                    "review_text": text,
                    "rating": _get_rating(review_data),
                    "review_order": len(reviews) + 1,
                    "reviewer_name": _get_reviewer_name(review_data),
                    "review_timestamp": _get_timestamp(review_data),
                })
                if len(reviews) >= max_reviews:
                    return reviews

    if reviews:
        logger.debug("Extracted {} reviews from top-level key", len(reviews))

    # ── Diagnostic: log available keys if still empty ──────────────
    if not reviews:
        logger.warning(
            "PRELOADED_STATE extracted 0 reviews. Top-level keys: {} | "
            "pages keys: {} | restaurant res-ids: {} | entities present: {}",
            list(state.keys()),
            list(state.get("pages", {}).get("current", {}).keys()) if state.get("pages", {}).get("current") else "N/A",
            list(restaurant_data.keys()) if isinstance(restaurant_data, dict) else "N/A",
            bool(state.get("entities")),
        )

    return reviews


async def click_load_more_reviews(page) -> bool:
    """Click 'Load More Reviews' button if present. Return True if clicked."""
    load_more_selectors = [
        "span:has-text('Load More')",
        "div.sc-1s0s0s0-0:has-text('Load More')",
        "button:has-text('Load More')",
        "button:has-text('Show More')",
        "div[class*='load-more']",
        "//button[contains(text(), 'Load More')]",
    ]
    for selector in load_more_selectors:
        try:
            if await page.locator(selector).is_visible():
                await human_like_click(page, selector)
                await human_delay(3, 7)
                return True
        except Exception:
            continue
    return False


async def extract_reviews(page, restaurant_url: str, max_reviews: int = MAX_REVIEWS) -> list[dict]:
    """
    Navigate to the dedicated ``/reviews`` page and extract reviews.

    Strategy:
    1. Navigate to the ``/reviews`` page.
    2. Try to extract from the ``__PRELOADED_STATE__`` JSON.
    3. Fall back to DOM-based extraction with scrolling.

    Each review: ``{review_text, rating, review_order}``
    """
    # 1. Navigate to the /reviews page — always use the pure base URL
    reviews_url = restaurant_url.rstrip("/") + "/reviews"
    logger.info("Navigating to reviews page: {}", reviews_url)

    try:
        await page.goto(reviews_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning("Failed to navigate to reviews page: {}", e)
        return []

    # 2. Skip networkidle for speed refresh
    pass

    # 3. Get page HTML
    html = await page.content()

    # 4. Try preloaded state extraction first
    reviews = _extract_reviews_from_preloaded_state(html, max_reviews)
    # If preloaded reviews meet the requested count, return immediately.
    # Otherwise continue to DOM extraction to collect up to `max_reviews` total.
    if reviews and len(reviews) >= max_reviews:
        logger.info(f"Extracted {len(reviews)} reviews from preloaded state")
        return reviews

    # 5. Fall back to DOM-based extraction with scrolling
    logger.info("No structured review data found — trying DOM-based extraction")

    # 5a. Try clicking the "Reviews" tab if the page landed on a different tab
    try:
        reviews_tab = page.locator("a[href*='/reviews']").first
        if await reviews_tab.is_visible():
            await human_like_click(page, reviews_tab)
            await human_delay(2, 4)
    except Exception:
        pass

    # 5b. Wait for review content to appear
    try:
        # Wait a short time for reviews to appear
        await page.wait_for_selector(active_rev_selector, timeout=2000)
    except Exception:
        pass

    # Initialize collected reviews with any preloaded reviews so DOM extraction
    # continues from where the preloaded state left off.
    collected = reviews if reviews else []
    seen_texts = {r["review_text"] for r in collected if r.get("review_text")}
    no_new_reviews_count = 0
    max_scroll_rounds = 20  # safety limit

    # Trigger lazy-rendered reviews before starting the collection loop.
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await human_delay(1, 2)
    except Exception:
        logger.debug("Initial scroll-to-bottom failed; continuing with DOM extraction")

    # Deduplicate any overlap between preloaded-state reviews and DOM reviews.
    collected = list({
        review["review_text"]: review
        for review in collected
        if review.get("review_text")
    }.values())
    seen_texts = {review["review_text"] for review in collected if review.get("review_text")}

    if len(collected) >= max_reviews:
        logger.info(f"Extracted {len(collected)} reviews")
        return collected[:max_reviews]

    page_number = 1
    while (
        len(collected) < max_reviews
        and no_new_reviews_count < 3 
    ):
        review_selectors = [
            "div[class*='sc-'] p", 
            "div[class*='review'] p",
            "section p",
            "div.sc-1s0s0s0-0 p"
        ]
        
        active_rev_selector = await find_selector(page, review_selectors)
        if not active_rev_selector:
            active_rev_selector = "p"
            
        review_elements = await page.locator(active_rev_selector).all()
        
        new_on_this_page = 0
        for el in review_elements:
            if len(collected) >= max_reviews:
                break
            try:
                text = await el.text_content()
                text = text.strip() if text else ""
                if len(text) > 15 and text not in seen_texts:
                    seen_texts.add(text)
                    collected.append({
                        "review_text": text,
                        "rating": 5.0,
                        "review_order": len(collected) + 1,
                    })
                    new_on_this_page += 1
            except Exception:
                continue
        
        logger.info(f"Page {page_number} processed. Unique reviews so far: {len(collected)}/{max_reviews}")

        if len(collected) >= max_reviews or page_number >= 8:
            break

        if new_on_this_page == 0:
            no_new_reviews_count += 1
        else:
            no_new_reviews_count = 0

        # Jump to next page
        page_number += 1
        next_url = f"{restaurant_url.rstrip('/')}/reviews?page={page_number}"
        logger.info(f"Navigating to Page {page_number}...")
        
        try:
            await page.goto(next_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Failed to load Page {page_number}: {e}")
            break
    
    # Final deduplication
    final_collected = list({
        r["review_text"]: r for r in collected if r.get("review_text")
    }.values())

    logger.info(f"Extracted {len(final_collected)} reviews total")
    return final_collected[:max_reviews]


if __name__ == "__main__":
    async def main():
        from scraper.browser import BrowserManager

        async with BrowserManager() as bm:
            test_url = "https://www.zomato.com/jammu/samosa-junction-gandhi-nagar"
            await bm.page.goto(test_url, wait_until="domcontentloaded")
            await human_delay(3, 5)

            reviews = await extract_reviews(bm.page, test_url)

            for review in reviews:
                print(f"Review #{review['review_order']}:")
                print(f"  Text: {review['review_text'][:80]}...")
                print(f"  Rating: {review['rating']}")
                print("-" * 40)

            print(f"\nTotal reviews extracted: {len(reviews)}")

    asyncio.run(main())
