"""
Zomato Jammu Scraper — Entry Point

Orchestrates the full scraping pipeline:
  1. Initialize database
  2. Launch browser (persistent context)
  3. Extract restaurant listings
  4. For each restaurant: extract details, reviews, menu
  5. Store everything in SQLite
  6. Generate summary report

Usage:
    python main.py              # Normal run (resume from checkpoint)
    python main.py --reset      # Reset database and start fresh
"""

import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

from config import DB_PATH, BASE_URL, CHROME_USER_DATA, MIN_DELAY, MAX_DELAY, MAX_REVIEWS, LOGS_DIR, DEFAULT_CITY, DEFAULT_STATE
from database.schema import create_tables
from database.crud import (
    insert_restaurant,
    insert_review,
    insert_menu_item,
    get_restaurant_by_url,
    delete_restaurant_reviews,
)
from scraper.browser import BrowserManager
from scraper.restaurant_list import extract_restaurant_cards, scroll_to_load_all
from scraper.restaurant_detail import extract_restaurant_detail
from scraper.reviews import extract_reviews
from scraper.menu import extract_menu
from utils.delays import human_delay
from utils.error_handler import retry_on_failure, NavigationError, ExtractionError, AntiBotDetected
from utils.reporter import generate_report, save_report


# ── Logging setup ──────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger.add(
    LOGS_DIR / "scraper.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)
logger.add(sys.stderr, level="INFO")

# ── Checkpoint file ────────────────────────────────────────────────────────
CHECKPOINT_FILE = Path("data/checkpoint.txt")


def _load_checkpoint() -> set[str]:
    """Return the set of already-scraped restaurant URLs from the checkpoint file."""
    if not CHECKPOINT_FILE.exists():
        return set()
    try:
        raw = CHECKPOINT_FILE.read_text(encoding="utf-8").strip()
        return set(line.strip() for line in raw.splitlines() if line.strip())
    except Exception:
        logger.warning("Could not read checkpoint file — starting fresh")
        return set()


def _save_checkpoint(url: str) -> None:
    """Append a successfully scraped URL to the checkpoint file."""
    try:
        with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
    except Exception as e:
        logger.warning("Failed to save checkpoint: {}", e)


# ── Scraper class ──────────────────────────────────────────────────────────


class ZomatoJammuScraper:
    """Orchestrates the full Zomato Jammu scraping pipeline."""

    def __init__(self):
        self.db_path = DB_PATH
        self.base_url = BASE_URL
        self.stats: dict[str, int] = {
            "restaurants": 0,
            "reviews": 0,
            "menu_items": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    async def run(self) -> None:
        """Execute the full pipeline."""
        logger.info("=" * 60)
        logger.info("Zomato Jammu Scraper — Starting")
        logger.info(f"Database: {DB_PATH}")
        logger.info("=" * 60)

        # 1. Initialise database
        create_tables()
        logger.info("Database tables ready.")

        # 2. Load checkpoint (already-scraped URLs)
        scraped_urls = _load_checkpoint()
        logger.info("Loaded {} already-scraped URLs from checkpoint.", len(scraped_urls))

        # 3. Launch browser
        async with BrowserManager(CHROME_USER_DATA) as browser:
            page = browser.page

            # 4. Navigate to the main listing page
            logger.info("Navigating to {}", self.base_url)
            await page.goto(self.base_url)
            await page.wait_for_load_state("domcontentloaded")
            
            # 4a. Wait 60s for manual login / OTP entry
            logger.info("Waiting 60 seconds for manual login/OTP entry. Please check the browser window!")
            await page.wait_for_timeout(60000)

            # 5. Extract restaurant listings (Full Scan)
            logger.info("Starting full scan of restaurant listings...")
            await scroll_to_load_all(page)
            cards = await extract_restaurant_cards(page)
            logger.info("Found {} restaurants to process.", len(cards))

            # 7. Process remaining restaurants
            for i, card in enumerate(cards, start=1):
                restaurant_url = card.get("url")
                if not restaurant_url:
                    continue

                if restaurant_url in scraped_urls:
                    logger.debug("Skipping already scraped restaurant: {}", restaurant_url)
                    continue

                logger.info("[{}/{}] Processing: {}", i, len(cards), restaurant_url)
                try:
                    # Prevent hanging on single restaurant for more than 10 minutes
                    await asyncio.wait_for(
                        self._process_restaurant(browser, restaurant_url, card),
                        timeout=600.0
                    )
                except asyncio.TimeoutError:
                    logger.error("TIMEOUT: {} took too long. Skipping.", restaurant_url)
                    continue
                except Exception as e:
                    logger.error("ERROR: Failed to process {}: {}", restaurant_url, e)
                    continue

                # Save checkpoint
                _save_checkpoint(restaurant_url)
                scraped_urls.add(restaurant_url)
                
                # Safe delay between restaurants
                await asyncio.sleep(1)

                # Log progress every 5 restaurants
                if self.stats["restaurants"] % 5 == 0 and self.stats["restaurants"] > 0:
                    logger.info(
                        "Progress: {} restaurants scraped ({} errors so far)",
                        self.stats["restaurants"],
                        self.stats["errors"],
                    )

                # Human delay between restaurants
                await asyncio.sleep(1)

        # 8. Generate and save report
        logger.info("Generating report…")
        report = await generate_report()
        report_path = save_report(report)
        logger.info("Report saved to: {}", report_path)

        # 9. Log final stats
        logger.info("=" * 60)
        logger.info("Scraping complete!")
        logger.info("  Restaurants: {}", self.stats["restaurants"])
        logger.info("  Reviews:     {}", self.stats["reviews"])
        logger.info("  Menu items:  {}", self.stats["menu_items"])
        logger.info("  Errors:      {}", self.stats["errors"])
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    @retry_on_failure(max_retries=2, backoff_base=10)
    async def _process_restaurant(self, browser: BrowserManager, restaurant_url: str, card: dict) -> None:
        """Scrape a single restaurant: details, menu, reviews — with retry logic."""
        # Open a new tab for this restaurant
        tab = await browser.new_page()
        try:
            # a. Navigate to main page first (Crucial for Price for Two & Ratings)
            logger.info("Navigating to main restaurant page: {}", restaurant_url)
            try:
                await tab.goto(restaurant_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Failed to load main page: {}", e)
                return

            # b. Extract Detail & Ratings from the Main page
            detail = await extract_restaurant_detail(tab, restaurant_url)
            
            # If name is missing, likely a 404 / invalid page — log and skip
            if not detail or not detail.get("name"):
                logger.error("Could not extract detail from main page for URL: {}", restaurant_url)
                return

            # c. Extract menu
            menu_items, menu_images = await extract_menu(tab, restaurant_url)
            menu_images_str = ", ".join(menu_images) if menu_images else None

            # c. Store restaurant — get back the id
            restaurant_id = insert_restaurant(
                name=detail.get("name"),
                phone=detail.get("phone"),
                price_for_two=detail.get("price_for_two"),
                rating=detail.get("rating"),
                zomato_url=restaurant_url,
                distance=card.get("distance"),
                delivery_time=card.get("delivery_time"),
                offer=card.get("offer"),
                total_orders=card.get("total_orders"),
                safety_badge=card.get("safety_badge"),
                cuisines=detail.get("cuisines"),
                address=detail.get("address"),
                open_status=detail.get("open_status"),
                timings=detail.get("timings"),
                latitude=detail.get("latitude"),
                longitude=detail.get("longitude"),
                exact_votes=detail.get("exact_votes"),
                dining_rating=detail.get("dining_rating"),
                dining_votes=detail.get("dining_votes"),
                delivery_rating=detail.get("delivery_rating"),
                delivery_votes=detail.get("delivery_votes"),
                highlights=detail.get("highlights"),
                menu_images=menu_images_str,
                city=DEFAULT_CITY,
                state=DEFAULT_STATE,
            )
            if restaurant_id is None:
                logger.warning("Could not insert restaurant (may be duplicate) — skipping reviews")

            if not restaurant_id:
                logger.warning("Could not insert restaurant — skipping reviews")
                return

            # e. Delete old reviews and extract new ones
            delete_restaurant_reviews(restaurant_id)
            reviews = await extract_reviews(tab, restaurant_url, MAX_REVIEWS)
            logger.debug("Extracted {} reviews.", len(reviews))

            for rev in reviews:
                insert_review(
                    restaurant_id=restaurant_id,
                    review_text=rev.get("review_text"),
                    rating=rev.get("rating"),
                    review_order=rev.get("review_order"),
                    reviewer_name=rev.get("reviewer_name"),
                    review_timestamp=rev.get("review_timestamp"),
                )

            # e. Insert menu items
            for item in menu_items:
                insert_menu_item(
                    restaurant_id=restaurant_id,
                    item_name=item["item_name"],
                    price=item["price"],
                    category=item.get("category"),
                    is_veg=item.get("is_veg"),
                    bestseller=item.get("bestseller"),
                    description=item.get("description"),
                )

            # f. Update stats
            self.stats["restaurants"] += 1
            self.stats["reviews"] += len(reviews)
            self.stats["menu_items"] += len(menu_items)

            logger.info(
                "Stored: {} | dist={}, time={}, offer={}, orders={} | cuisines={} | {} reviews, {} menu items, {} menu images",
                detail.get("name", restaurant_url),
                card.get("distance", "?"),
                card.get("delivery_time", "?"),
                card.get("offer", "?"),
                card.get("total_orders", "?"),
                detail.get("cuisines", "?"),
                len(reviews),
                len(menu_items),
                len(menu_images),
            )

        except (NavigationError, ExtractionError, AntiBotDetected) as e:
            logger.warning("Error processing {}: {}", restaurant_url, e)
            self.stats["errors"] += 1
            raise  # let retry_on_failure handle it
        except Exception as e:
            logger.warning("Unexpected error processing {}: {}", restaurant_url, e)
            self.stats["errors"] += 1
            raise
        finally:
            await tab.close()
            logger.debug("Tab closed for: {}", restaurant_url)


# ── Entry point ────────────────────────────────────────────────────────────


async def main():
    """Main entry point for the scraper."""
    import sys

    # Handle --reset flag
    if "--reset" in sys.argv:
        from database.schema import reset_database
        logger.warning("--reset flag detected — dropping and recreating all tables!")
        reset_database()
        # Also clear the checkpoint file so all restaurants are re-scraped
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
            logger.info("Checkpoint file deleted.")
        logger.info("Database reset complete. Starting fresh scrape...")

    scraper = ZomatoJammuScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
