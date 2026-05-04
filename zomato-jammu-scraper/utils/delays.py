"""
Human-like delay utilities for the Zomato Jammu Scraper.

Provides async delay functions that introduce realistic timing
variation to avoid detection by anti-bot systems.
"""

import asyncio
import random

from config import MIN_DELAY, MAX_DELAY
from loguru import logger


async def human_delay(
    min_seconds: float = MIN_DELAY, max_seconds: float = MAX_DELAY
) -> None:
    """Sleep for a random duration between *min_seconds* and *max_seconds*.

    This is the primary delay used between major scraping actions such
    as navigating between restaurant pages or loading new sections.
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)
    logger.info(f"Human-like delay of {delay:.2f} seconds")


async def micro_delay() -> None:
    """Short delay between fine-grained actions (mouse moves, clicks).

    Simulates the small hesitation a human has between sub-actions.
    """
    delay = random.uniform(0.3, 1.2)
    await asyncio.sleep(delay)


async def scroll_delay() -> None:
    """Delay after each scroll chunk.

    Mimics a human pausing to read before scrolling further.
    """
    delay = random.uniform(1.5, 3.0)
    await asyncio.sleep(delay)


async def human_like_click(page, selector: str) -> None:
    """Move the mouse in a natural arc over *selector* before clicking.

    Steps:
    1. Retrieve the bounding box of the target element.
    2. Move toward the element in 5 small steps with random jitter.
    3. Click the element.

    This helps bypass behavioural detection heuristics.
    """
    # Locate the element and get its bounding box
    locator = page.locator(selector)
    box = await locator.bounding_box()
    if box is None:
        logger.warning(f"Element '{selector}' not found — skipping click")
        return

    # Pick a random target point inside the element
    target_x = box["x"] + random.uniform(0, box["width"])
    target_y = box["y"] + random.uniform(0, box["height"])

    # Get the current mouse position (Playwright defaults to viewport centre)
    current_pos = await page.evaluate(
        "() => ({x: window.__mouseX ?? window.innerWidth / 2, "
        "y: window.__mouseY ?? window.innerHeight / 2})"
    )

    # Move in 5 steps along an eased path
    for step in range(1, 6):
        progress = step / 5.0
        # Cubic ease-out for a more natural deceleration
        eased = 1 - (1 - progress) ** 3

        mid_x = current_pos["x"] + (target_x - current_pos["x"]) * eased
        mid_y = current_pos["y"] + (target_y - current_pos["y"]) * eased

        # Add random jitter that decreases as we approach the target
        jitter_scale = 1.0 - eased
        jitter_x = random.uniform(-3, 3) * jitter_scale
        jitter_y = random.uniform(-3, 3) * jitter_scale

        await page.mouse.move(mid_x + jitter_x, mid_y + jitter_y)
        await micro_delay()

    # Final click
    await page.click(selector)
    logger.debug(f"Clicked '{selector}' with human-like motion")


if __name__ == "__main__":
    """Quick smoke-test: run :func:`human_delay` three times and report."""

    async def _test() -> None:
        for i in range(1, 4):
            start = asyncio.get_event_loop().time()
            await human_delay(1, 2)
            elapsed = asyncio.get_event_loop().time() - start
            print(f"Iteration {i}: actual delay = {elapsed:.2f} s")

        print("All delay tests passed!")

    asyncio.run(_test())
