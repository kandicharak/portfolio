"""
Reporting utilities for the Zomato Jammu Scraper.
Generates Markdown summary reports of scraping results.
"""

import asyncio
import datetime

from database.crud import (
    get_all_restaurants,
    get_reviews_by_restaurant,
    get_menu_items_by_restaurant,
)
from loguru import logger


async def generate_report() -> str:
    """Generate a Markdown summary of scraping results."""
    restaurants = get_all_restaurants()

    if not restaurants:
        return "# Zomato Jammu Scraper Report\n\nNo restaurants scraped yet."

    total_restaurants = len(restaurants)
    total_reviews = 0
    total_menu_items = 0
    ratings = []

    for r in restaurants:
        rid = r["id"]
        reviews = get_reviews_by_restaurant(rid)
        menu_items = get_menu_items_by_restaurant(rid)
        total_reviews += len(reviews)
        total_menu_items += len(menu_items)
        if r["rating"] is not None:
            ratings.append(r["rating"])

    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    # Top 5 restaurants by rating
    sorted_restaurants = sorted(
        restaurants, key=lambda x: x["rating"] or 0, reverse=True
    )
    top_5 = sorted_restaurants[:5]

    # Build markdown
    lines = []
    lines.append("# Zomato Jammu Scraper Report")
    lines.append(f"**Generated:** {datetime.datetime.now().isoformat()}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- **Total Restaurants:** {total_restaurants}")
    lines.append(f"- **Total Reviews:** {total_reviews}")
    lines.append(f"- **Total Menu Items:** {total_menu_items}")
    lines.append(f"- **Average Rating:** {avg_rating:.2f} / 5.0")
    lines.append("")
    lines.append("## Top 5 Restaurants by Rating")
    lines.append("| # | Name | Rating | Price for Two | Reviews | Menu Items |")
    lines.append("|---|------|--------|---------------|---------|------------|")

    for i, r in enumerate(top_5, 1):
        rid = r["id"]
        review_count = len(get_reviews_by_restaurant(rid))
        menu_count = len(get_menu_items_by_restaurant(rid))
        price = f"\u20b9{r['price_for_two']:.0f}" if r["price_for_two"] else "N/A"
        rating = f"{r['rating']:.1f}" if r["rating"] else "N/A"
        name = r["name"] or "Unknown"
        lines.append(
            f"| {i} | {name} | {rating} | {price} | {review_count} | {menu_count} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Report generated automatically by Zomato Jammu Scraper*")

    return "\n".join(lines)


def save_report(report: str, filepath: str = None) -> str:
    """Save report to file. Returns the filepath used."""
    if filepath is None:
        from config import LOGS_DIR

        filepath = str(LOGS_DIR / "scrape_report.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"Report saved to {filepath}")
    return filepath


if __name__ == "__main__":
    report = asyncio.run(generate_report())
    save_report(report)
    print(report)
    print("Reporter test passed")
