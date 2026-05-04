from loguru import logger

RESTAURANT_CARD_SELECTORS = [
    "div[class*='sc-'] > a",
    "div[class*='jumbo']",
    "a:has(h4)",
    "a.sc-1hp8d8a-0",
    "a.sc-hzDkRC",
    "div[class*='restaurant'] a[href*='/jammu/']",
    "a[data-testid='restaurant-card']",
    "//a[contains(@href, '/jammu/') and contains(@href, '/info')]",
    "div.jumbo-tracker",
    "a[href*='/jammu/'][href*='/order']",
]

RESTAURANT_NAME_SELECTORS = [
    # Prefer structural heading selector; React classes are unstable
    "h4",
    "h1",
]

RESTAURANT_PHONE_SELECTORS = [
    "a[href^='tel:']",
    "span[class*='phone']",
    "div[class*='phone']",
    "//a[contains(@href, 'tel:')]",
]

PRICE_FOR_TWO_SELECTORS = [
    "p:has-text('\u20b9')",
    "span:has-text('\u20b9')",
    "span[class*='price']",
    "div[class*='price']",
    "//p[contains(text(), '\u20b9')]",
    "//span[contains(text(), '\u20b9')]",
]

RATING_SELECTORS = [
    "div[class*='rating'] span",
    "span[class*='rating']",
    "div[aria-label*='rated']",
    "//div[contains(@aria-label, 'rated')]",
]

REVIEW_TEXT_SELECTORS = [
    # Zomato v2 review cards — broad sc- class matching
    "div.sc-1s0s0s0-0 p",
    "div.sc-1s0s0s0-0 span",
    "div[class*='review'] p",
    "div[class*='review'] span",
    "p[class*='review']",
    "div[class*='review-text']",
    "span[class*='review']",
    "//p[contains(@class, 'review')]",
    "//div[contains(@class, 'review')]//p",
    # Catch-all: any paragraph inside a card-like container
    "article p",
    "section[class*='review'] p",
    "div[class*='card'] p",
    "div[class*='feedback'] p",
    "div[class*='comment'] p",
]

REVIEW_RATING_SELECTORS = [
    "div[class*='review'] span[class*='rating']",
    "span[class*='review-rating']",
    "div[class*='review'] div[class*='rating']",
    "//div[contains(@class, 'review')]//span[contains(@class, 'rating')]",
    # Broader Zomato v2 selectors
    "div.sc-1s0s0s0-0 div[class*='rating']",
    "div.sc-1s0s0s0-0 span[class*='rating']",
    "div[class*='rating'] span",
    "span[class*='rating']",
    "div[aria-label*='rated']",
    "//div[contains(@aria-label, 'rated')]",
]

MENU_ITEM_SELECTORS = [
    # Structural selectors targeting Order Online dish containers
    "div[class*='MenuItem__MenuItemContainer']",
    "div:has(h4):has-text('₹')",
    "div[class*='sc-']:has(h4)",
    "div[class*='sc-'] > div:has(h4)",
    "div:has(h4)",
]

MENU_PRICE_SELECTORS = [
    # Look for explicit price text containing the rupee symbol in various tags
    "span:has-text('₹')",
    "p:has-text('₹')",
    "div:has-text('₹')",
    "span[class*='price']",
    "p[class*='price']",
    "div[class*='price']",
    ":has-text('₹')",
]

MENU_CATEGORY_SELECTORS = [
    "h3[class*='category']",
    "div[class*='category-header']",
    "//h3[contains(@class, 'category')]",
]


async def find_selector(page, selectors_list) -> str | None:
    """Try each selector until one matches at least one element. Returns the first matching selector or None."""
    for selector in selectors_list:
        try:
            # page may be a Playwright Page or a Locator; obtain a locator and await its count
            if hasattr(page, "locator"):
                locator = page.locator(selector)
            else:
                # fallback: assume `page` behaves like a locator already
                locator = page

            count = await locator.count()
            if count and count > 0:
                # logger.info(f"Active selector found: {selector} ({count} matches)")
                return selector
        except Exception as e:
            logger.debug(f"Selector failed: {selector} - {e}")
            continue
    return None


# --- Delivery-specific selectors ---

# Distance shown on restaurant cards in delivery listing
DELIVERY_DISTANCE_SELECTORS = [
    "div.sc-1hez2tp-0 span.sc-1hez2tp-0",  # common Zomato delivery distance
    "div.gnLbKM span",
    "div.sc-1hez2tp-0",
    "[class*='distance']",
    "[class*='delivery'] span",
]

# Delivery time shown on restaurant cards
DELIVERY_TIME_SELECTORS = [
    "div.sc-1s0s0s0-0 span.sc-1s0s0s0-0",  # common Zomato delivery time
    "div.dLbLZP span",
    "div.sc-1s0s0s0-0",
    "[class*='time']",
    "[class*='eta']",
    "[class*='delivery-time']",
]

# Delivery fee / charges
DELIVERY_FEE_SELECTORS = [
    "div.sc-1s0s0s0-0 span.sc-1s0s0s0-0",  # common Zomato delivery fee
    "[class*='fee']",
    "[class*='charges']",
    "[class*='delivery-fee']",
]


# --- Listing Card: Offers / Discounts ---
OFFER_SELECTORS = [
    "div.sc-17y0p1-0 span",           # common Zomato offer badge
    "div.sc-1s0s0s0-0 div.sc-17y0p1-0",
    "[class*='offer']",
    "[class*='discount']",
    "[class*='promo']",
    "div.sc-1s0s0s0-0 span:has-text('%')",
]

# --- Listing Card: Total Orders Placed ---
TOTAL_ORDERS_SELECTORS = [
    "div.sc-1hez2tp-0 span.sc-1hez2tp-0",  # common Zomato order count
    "div.gnLbKM span",
    "[class*='order']",
    "[class*='orders']",
    "span:has-text('orders')",
    "span:has-text('Order')",
]

# --- Listing Card: Safety Badges ---
SAFETY_BADGE_SELECTORS = [
    "div.sc-1s0s0s0-0 img[alt*='safety']",
    "div.sc-1s0s0s0-0 img[alt*='Safe']",
    "div.sc-1s0s0s0-0 img[alt*='Vaccinated']",
    "[class*='safety']",
    "[class*='badge']",
    "img[alt*='safety']",
    "img[alt*='Safe']",
]

# --- Restaurant Detail: Cuisines ---
CUISINE_SELECTORS = [
    "div.sc-1s0s0s0-0 a[class*='cuisine']",
    "div.sc-1s0s0s0-0 span[class*='cuisine']",
    "a[class*='cuisine']",
    "span[class*='cuisine']",
    "div:has(span:has-text('Cuisines')) + div a",
    "div:has(span:has-text('Cuisine')) + div span",
    "[class*='cuisine']",
]

# --- Restaurant Detail: Exact Address ---
ADDRESS_SELECTORS = [
    "p.sc-bFADNz.gNdKCg",
    "div.sc-1s0s0s0-0 p[class*='address']",
    "div.sc-1s0s0s0-0 span[class*='address']",
    "p[class*='address']",
    "span[class*='address']",
    "div:has(span:has-text('Address')) + div p",
    "div:has(span:has-text('Address')) + div span",
    "[class*='address']",
]

# --- Restaurant Detail: Open/Closed Status & Timings ---
TIMING_SELECTORS = [
    "span.sc-iGPElx",
    "div.sc-13lc47p-0",
    "div.sc-1s0s0s0-0 p[class*='timing']",
    "div.sc-1s0s0s0-0 span[class*='timing']",
    "p[class*='timing']",
    "span[class*='timing']",
    "div:has(span:has-text('Open'))",
    "div:has(span:has-text('Closed'))",
    "div:has(span:has-text('Hours')) + div p",
    "[class*='timing']",
    "[class*='open']",
    "[class*='closed']",
    "span:has-text('Open')",
    "span:has-text('Closed')",
]

# --- Menu Item: Veg/Non-Veg Tag ---
VEG_NONVEG_SELECTORS = [
    "span[class*='veg']",
    "span[class*='non-veg']",
    "div[class*='veg']",
    "div[class*='non-veg']",
    "img[alt*='veg']",
    "img[alt*='non-veg']",
    "[class*='veg']",
    "[class*='nonveg']",
]

# --- Menu Item: Bestseller / Must Try Status ---
BESTSELLER_SELECTORS = [
    "span:has-text('Bestseller')",
    "span:has-text('Must Try')",
    "span:has-text('Must try')",
    "span:has-text('Popular')",
    "div:has-text('Bestseller')",
    "div:has-text('Must Try')",
    "[class*='bestseller']",
    "[class*='must-try']",
    "[class*='popular']",
]

# --- Menu Item: Description ---
ITEM_DESCRIPTION_SELECTORS = [
    "p[class*='description']",
    "span[class*='description']",
    "div[class*='description']",
    "p.sc-1s0s0s0-0",
    "div.sc-1s0s0s0-0 p",
    "[class*='desc']",
]


if __name__ == "__main__":
    print("Selectors module loaded successfully")
    print("RESTAURANT_CARD_SELECTORS:", len(RESTAURANT_CARD_SELECTORS))
    print("RESTAURANT_NAME_SELECTORS:", len(RESTAURANT_NAME_SELECTORS))
    print("RESTAURANT_PHONE_SELECTORS:", len(RESTAURANT_PHONE_SELECTORS))
    print("PRICE_FOR_TWO_SELECTORS:", len(PRICE_FOR_TWO_SELECTORS))
    print("RATING_SELECTORS:", len(RATING_SELECTORS))
    print("REVIEW_TEXT_SELECTORS:", len(REVIEW_TEXT_SELECTORS))
    print("REVIEW_RATING_SELECTORS:", len(REVIEW_RATING_SELECTORS))
    print("MENU_ITEM_SELECTORS:", len(MENU_ITEM_SELECTORS))
    print("MENU_PRICE_SELECTORS:", len(MENU_PRICE_SELECTORS))
    print("MENU_CATEGORY_SELECTORS:", len(MENU_CATEGORY_SELECTORS))
