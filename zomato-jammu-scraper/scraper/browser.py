"""
Browser manager module for the Zomato Jammu Scraper.

Provides a persistent Playwright browser context with stealth
enhancements and proper resource cleanup.
"""

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import BrowserContext, Page, Playwright
from playwright_stealth import Stealth

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import CHROME_USER_DATA, LOGS_DIR


class BrowserManager:
    """Manages a persistent Playwright browser context."""

    def __init__(self, user_data_dir: str = r"D:\zomato_scraper_profile"):
        self.user_data_dir = user_data_dir
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def __aenter__(self) -> "BrowserManager":
        """Launch persistent context and apply stealth."""
        from playwright.async_api import async_playwright

        try:
            logger.info("Starting Playwright…")
            self.playwright = await async_playwright().start()

            logger.info(f"Launching persistent browser context using profile: {CHROME_USER_DATA}")
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=CHROME_USER_DATA,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--disable-http2", "--blink-settings=imagesEnabled=false"],
                viewport={"width": 1920, "height": 1080},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            # Route to block images for all pages
            await self.context.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}*", lambda route: route.abort())
            self.browser = None

            logger.info("Creating new page…")
            self.page = await self.context.new_page()
            # ensure stealth is applied to any page created in this context
            async def _apply_stealth(page: Page) -> None:
                try:
                    stealth = Stealth()
                    await stealth.apply_stealth_async(page)
                except Exception:
                    logger.exception("Failed to apply stealth to page")

            # attach handler so pages created by the site also get stealth
            self.context.on("page", lambda page: asyncio.create_task(_apply_stealth(page)))

            # apply stealth for the initial page
            await _apply_stealth(self.page)
            logger.info("Browser context ready.")
            return self
        except Exception:
            logger.exception("Failed to initialise browser context")
            await self.close()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up resources."""
        if exc_type:
            logger.error("Exiting with exception: {}: {}", exc_type.__name__, exc_val)
        await self.close()

    async def new_page(self) -> Page:
        """Create a new tab in the existing context."""
        try:
            if not self.context:
                raise Exception("Browser context is missing — cannot create page")
            page = await self.context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            logger.debug("New page created.")
            return page
        except Exception:
            logger.exception("Failed to create new page")
            raise

    async def close(self) -> None:
        """Graceful shutdown."""
        try:
            if self.page:
                await self.page.close()
                logger.debug("Page closed.")
            if self.context:
                await self.context.close()
                logger.debug("Context closed.")
            if hasattr(self, 'browser') and self.browser:
                await self.browser.close()
                logger.debug("Browser closed.")
            if self.playwright:
                await self.playwright.stop()
                logger.info("Playwright stopped.")
        except Exception:
            logger.exception("Error during browser shutdown")


async def _main() -> None:
    """Quick smoke-test: open Zomato Jammu and take a screenshot."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = LOGS_DIR / "test_homepage.png"

    async with BrowserManager() as bm:
        logger.info("Navigating to https://www.zomato.com/jammu …")
        await bm.page.goto("https://www.zomato.com/jammu")
        await bm.page.screenshot(path=str(screenshot_path))
        logger.info("Screenshot saved to {}", screenshot_path)
        print("Browser test passed")


if __name__ == "__main__":
    asyncio.run(_main())

