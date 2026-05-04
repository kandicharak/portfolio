"""
Extract menu items and menu-image URLs from a Zomato restaurant page.

Zomato menus are image-based (JPEG images rendered in a carousel).
Individual menu items are NOT available as DOM elements.  This module
attempts to extract:

* Structured menu data from JSON-LD or ``__PRELOADED_STATE__``.
* Menu‑image URLs from ``SECTION_IMAGE_MENU`` when no structured items
  are found.
"""

import asyncio
import json
import re

from loguru import logger

from utils.delays import human_delay
from utils.selectors import (
    MENU_ITEM_SELECTORS,
    MENU_PRICE_SELECTORS,
    MENU_CATEGORY_SELECTORS,
    VEG_NONVEG_SELECTORS,
    BESTSELLER_SELECTORS,
    ITEM_DESCRIPTION_SELECTORS,
    find_selector,
)

# Regex to extract JSON-LD script blocks from raw HTML
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _normalize_is_veg(value) -> str | None:
    """Normalize is_veg to a consistent string: 'Veg', 'Non-Veg', or None.

    Handles booleans, strings, and tags from the preloaded state.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "Veg" if value else "Non-Veg"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "1", "veg"):
            return "Veg"
        if v in ("false", "no", "0", "non-veg", "non veg", "nonveg"):
            return "Non-Veg"
        return value.strip()  # pass through as-is (e.g. "Veg", "Non-Veg")
    if isinstance(value, (int, float)):
        return "Veg" if value else "Non-Veg"
    return str(value) if value else None


def _extract_menu_from_json_ld(html: str) -> list[dict]:
    """
    Attempt to extract menu items from JSON-LD structured data.

    Zomato sometimes embeds a ``hasMenu`` property in the Restaurant
    JSON-LD that points to a separate ``Menu`` JSON-LD block with
    individual ``hasMenuItem`` entries.

    Returns a list of dicts with keys:
    ``item_name``, ``price``, ``category``, ``is_veg``, ``bestseller``, ``description``.
    """
    items: list[dict] = []

    for block_text in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block_text.strip())
        except json.JSONDecodeError:
            continue

        items_data = data if isinstance(data, list) else [data]
        for entry in items_data:
            entry_type = entry.get("@type", "")
            if isinstance(entry_type, list):
                type_str = " ".join(entry_type)
            else:
                type_str = str(entry_type)

            # Look for Menu JSON-LD with menu items
            if "Menu" in type_str and "hasMenuItem" in entry:
                for menu_item in entry["hasMenuItem"]:
                    if isinstance(menu_item, dict):
                        name = menu_item.get("name")
                        if name:
                            price = menu_item.get("offers", {}).get("price") if isinstance(menu_item.get("offers"), dict) else None
                            items.append({
                                "item_name": str(name).strip(),
                                "price": float(price) if price else None,
                                "category": None,
                                "is_veg": None,
                                "bestseller": None,
                                "description": menu_item.get("description"),
                            })

    return items


def _parse_preloaded_state(html: str) -> dict | None:
    """Parse and return the ``__PRELOADED_STATE__`` JSON object, or ``None``."""
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\(', html)
    if not m:
        return None

    start = m.end()
    if html[start] != '"':
        return None

    end = html.find('")', start)
    if end == -1:
        return None

    try:
        raw = html[start + 1:end]
        raw = raw.replace('\\"', '"').replace('\\\\', '\\')
        return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return None


def _extract_menu_from_preloaded_state(html: str) -> list[dict]:
    """
    Attempt to extract structured menu items from the ``__PRELOADED_STATE__`` JSON.

    Checks multiple key paths:
      1. ``entities.ORDER``
      2. ``entities.RETAIL_ENTITY`` / ``entities.RESTAURANTS``
      3. ``restaurant.{resId}.sections.SECTION_ORDER`` (primary for /order page)
      4. ``restaurant.{resId}.sections.SECTION_RES_DETAILS.IMAGE_MENUS.menus``

    Does **not** create synthetic ``[Menu]`` placeholder items for image
    menus — those are handled separately by
    :func:`_extract_menu_images_from_preloaded_state`.

    Returns a list of dicts (same schema as ``_extract_menu_from_json_ld``).
    """
    items: list[dict] = []

    state = _parse_preloaded_state(html)
    if state is None:
        return items

    # Log available top-level keys for debugging
    logger.debug("Menu PRELOADED_STATE top-level keys: {}", list(state.keys()))

    entities = state.get("entities", {})
    if isinstance(entities, dict):
        # ── Path 1: entities.ORDER ──────────────────────────────────
        order = entities.get("ORDER", {})
        if order and isinstance(order, dict):
            for order_id, order_data in order.items():
                if isinstance(order_data, dict):
                    menu_items = order_data.get("menu_items", []) or order_data.get("items", [])
                    for mitem in menu_items:
                        if isinstance(mitem, dict) and mitem.get("name"):
                            items.append({
                                "item_name": str(mitem["name"]).strip(),
                                "price": mitem.get("price"),
                                "category": mitem.get("category"),
                                "is_veg": _normalize_is_veg(mitem.get("is_veg")),
                                "bestseller": mitem.get("bestseller"),
                                "description": mitem.get("description"),
                            })
        if items:
            logger.debug("Extracted {} items from entities.ORDER", len(items))
            return items

        # ── Path 2: entities.RETAIL_ENTITY / RESTAURANTS ─────────
        for entity_key in ("RETAIL_ENTITY", "RETAIL", "RESTAURANT", "RESTAURANTS"):
            entity_data = entities.get(entity_key, {})
            if isinstance(entity_data, dict):
                for ent_id, ent_obj in entity_data.items():
                    if not isinstance(ent_obj, dict):
                        continue
                    # Some Zomato pages nest menu under "menu" or "menuItems"
                    for menu_key in ("menu", "menuItems", "menu_items", "dish"):
                        menu_list = ent_obj.get(menu_key, [])
                        if isinstance(menu_list, list):
                            for mitem in menu_list:
                                if isinstance(mitem, dict):
                                    name = mitem.get("name") or mitem.get("dish_name") or mitem.get("item_name")
                                    if name:
                                        price = mitem.get("price")
                                        # price might be a string like "₹299"
                                        if isinstance(price, str):
                                            price = price.replace("₹", "").replace(",", "").strip()
                                        items.append({
                                            "item_name": str(name).strip(),
                                            "price": float(price) if price else None,
                                            "category": mitem.get("category") or mitem.get("cat"),
                                            "is_veg": _normalize_is_veg(mitem.get("is_veg") or mitem.get("isVeg")),
                                            "bestseller": mitem.get("bestseller") or mitem.get("mustTry"),
                                            "description": mitem.get("description") or mitem.get("desc"),
                                        })
            if items:
                logger.debug("Extracted {} items from entities.{}", len(items), entity_key)
                return items

    # ── Path 3: restaurant.{resId}.sections.SECTION_ORDER (primary for /order) ─
    restaurant_data = state.get("restaurant", {})
    if isinstance(restaurant_data, dict):
        for res_id, res_obj in restaurant_data.items():
            if not isinstance(res_obj, dict):
                continue
            sections = res_obj.get("sections", {})
            if not isinstance(sections, dict):
                continue

            section_order = sections.get("SECTION_ORDER", {})
            if isinstance(section_order, dict):
                # SECTION_ORDER typically has category keys (e.g. "South Indian", "Beverages")
                # each containing a list of dish dicts
                for cat_name, cat_data in section_order.items():
                    if isinstance(cat_data, list):
                        for mitem in cat_data:
                            if isinstance(mitem, dict):
                                name = mitem.get("name") or mitem.get("dish_name") or mitem.get("item_name")
                                if name:
                                    price = mitem.get("price")
                                    if isinstance(price, str):
                                        price = price.replace("₹", "").replace(",", "").strip()
                                    items.append({
                                        "item_name": str(name).strip(),
                                        "price": float(price) if price else None,
                                        "category": cat_name,
                                        "is_veg": _normalize_is_veg(mitem.get("is_veg") or mitem.get("isVeg")),
                                        "bestseller": mitem.get("bestseller") or mitem.get("mustTry"),
                                        "description": mitem.get("description") or mitem.get("desc"),
                                    })
                    elif isinstance(cat_data, dict):
                        # Some pages nest under cat_data["items"] or cat_data["dishes"]
                        dish_list = cat_data.get("items") or cat_data.get("dishes") or cat_data.get("menu_items") or []
                        if isinstance(dish_list, list):
                            for mitem in dish_list:
                                if isinstance(mitem, dict):
                                    name = mitem.get("name") or mitem.get("dish_name") or mitem.get("item_name")
                                    if name:
                                        price = mitem.get("price")
                                        if isinstance(price, str):
                                            price = price.replace("₹", "").replace(",", "").strip()
                                        items.append({
                                            "item_name": str(name).strip(),
                                            "price": float(price) if price else None,
                                            "category": cat_name,
                                            "is_veg": _normalize_is_veg(mitem.get("is_veg") or mitem.get("isVeg")),
                                            "bestseller": mitem.get("bestseller") or mitem.get("mustTry"),
                                            "description": mitem.get("description") or mitem.get("desc"),
                                        })
            if items:
                logger.debug("Extracted {} items from SECTION_ORDER", len(items))
                return items

            res_details = sections.get("SECTION_RES_DETAILS", {})
            if isinstance(res_details, dict):
                image_menus = res_details.get("IMAGE_MENUS", {})
                if isinstance(image_menus, dict):
                    menus_list = image_menus.get("menus", [])
                    if isinstance(menus_list, list):
                        for menu_group in menus_list:
                            if not isinstance(menu_group, dict):
                                continue
                            cat_label = menu_group.get("name") or menu_group.get("label", "Other")
                            items_data = menu_group.get("items", [])
                            for mitem in items_data:
                                if isinstance(mitem, dict):
                                    name = mitem.get("name") or mitem.get("dish_name")
                                    if name:
                                        price = mitem.get("price")
                                        if isinstance(price, str):
                                            price = price.replace("₹", "").replace(",", "").strip()
                                        items.append({
                                            "item_name": str(name).strip(),
                                            "price": float(price) if price else None,
                                            "category": cat_label,
                                            "is_veg": _normalize_is_veg(mitem.get("is_veg") or mitem.get("isVeg")),
                                            "bestseller": mitem.get("bestseller") or mitem.get("mustTry"),
                                            "description": mitem.get("description"),
                                        })

    if items:
        logger.debug("Extracted {} structured items from sections", len(items))
        return items

    return items


def _extract_menu_images_from_preloaded_state(html: str) -> list[str]:
    """
    Extract menu‑image URLs from ``SECTION_IMAGE_MENU`` in the preloaded state.

    Zomato stores image‑based menus under
    ``restaurant.{resId}.sections.SECTION_IMAGE_MENU``, where each entry
    has a ``pages`` list containing dicts with a ``url`` key pointing to a
    JPEG image of a menu page.

    Returns a list of image URLs, or an empty list.
    """
    image_urls: list[str] = []

    state = _parse_preloaded_state(html)
    if state is None:
        return image_urls

    restaurant_data = state.get("restaurant", {})
    if not isinstance(restaurant_data, dict):
        return image_urls

    for res_id, res_obj in restaurant_data.items():
        if not isinstance(res_obj, dict):
            continue
        sections = res_obj.get("sections", {})
        if not isinstance(sections, dict):
            continue

        # ── SECTION_IMAGE_MENU ──────────────────────────────────────
        image_menu = sections.get("SECTION_IMAGE_MENU", {})
        if isinstance(image_menu, dict):
            menu_items_list = image_menu.get("menuItems", [])
            if isinstance(menu_items_list, list):
                for menu_group in menu_items_list:
                    if not isinstance(menu_group, dict):
                        continue
                    pages = menu_group.get("pages", [])
                    if isinstance(pages, list):
                        for page_entry in pages:
                            if isinstance(page_entry, dict):
                                url = page_entry.get("url")
                                if url and isinstance(url, str) and url.strip():
                                    image_urls.append(url.strip())

        # Also check SECTION_RES_DETAILS > IMAGE_MENUS > menus
        res_details = sections.get("SECTION_RES_DETAILS", {})
        if isinstance(res_details, dict):
            image_menus = res_details.get("IMAGE_MENUS", {})
            if isinstance(image_menus, dict):
                menus_list = image_menus.get("menus", [])
                if isinstance(menus_list, list):
                    for menu_group in menus_list:
                        if not isinstance(menu_group, dict):
                            continue
                        pages = menu_group.get("pages", [])
                        if isinstance(pages, list):
                            for page_entry in pages:
                                if isinstance(page_entry, dict):
                                    url = page_entry.get("url")
                                    if url and isinstance(url, str) and url.strip():
                                        image_urls.append(url.strip())

    if image_urls:
        logger.debug("Extracted {} menu image URLs from preloaded state", len(image_urls))

    return image_urls


async def extract_menu(page, restaurant_url: str = "") -> tuple[list[dict], list[str]]:
    """
    Navigate to the Order Online page and extract live dish data.

    Strategy:
    1. Navigate to ``/order`` (primary — live dish data with prices).
    2. Try JSON-LD extraction.
    3. Try ``__PRELOADED_STATE__`` extraction (checks ``SECTION_ORDER`` first).
    4. **If no structured items found**, fall back to ``/menu`` (image-based menus).
    5. On ``/menu`` fallback: try preloaded state, then image URLs, then DOM.

    Returns
    -------
    tuple[list[dict], list[str]]
        ``(items, menu_images)`` where *items* is a list of structured menu
        items (``{item_name, price, category, is_veg, bestseller, description}``)
        and *menu_images* is a list of image URLs (``str``).
    """

    # ── Helper: try extracting from a given URL ──────────────────────────
    async def _try_extract(url: str, allow_image_return: bool = True) -> tuple[list[dict], list[str]] | None:
        """Return (items, []) or ([], images) or None if nothing found.

        When ``allow_image_return`` is False, image URLs are ignored so the
        caller can fall through to DOM extraction first.
        """
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 5)
        except Exception as e:
            logger.warning("Failed to navigate to {}: {}", url, e)
            return None

        html = await page.content()

        # JSON-LD
        items = _extract_menu_from_json_ld(html)
        if items:
            logger.info(f"Extracted {len(items)} menu items from JSON-LD at {url}")
            return items, []

        # Preloaded state
        items = _extract_menu_from_preloaded_state(html)
        if items:
            logger.info(f"Extracted {len(items)} menu items from preloaded state at {url}")
            return items, []

        # Image URLs
        menu_images = _extract_menu_images_from_preloaded_state(html)
        if menu_images and allow_image_return:
            logger.info(f"Extracted {len(menu_images)} menu image URLs at {url}")
            return [], menu_images

        return None

    # ── Build URLs ───────────────────────────────────────────────────────
    base = restaurant_url.rstrip("/") if restaurant_url else page.url.rstrip("/")
    order_url = base + "/order"
    menu_url = base + "/menu"

    # 1. Primary: /order
    logger.info("Primary target — navigating to order page: {}", order_url)
    result = await _try_extract(order_url, allow_image_return=False)
    if result is not None:
        return result

    # 2. DOM extraction on the /order page before falling back to /menu.
    logger.info("No structured data on /order — trying DOM-based extraction on the order page")
    # Some Zomato menus lazy-load items inside React components.
    # Perform a scrolling loop to trigger lazy-loading before DOM extraction.
    logger.info("Performing scroll loop to load lazy menu items...")
    prev_count = -1
    max_scrolls = 12
    for _ in range(max_scrolls):
        try:
            current_count = await page.locator("div:has(h4)").count()
        except Exception:
            current_count = 0
        if current_count == prev_count:
            break
        prev_count = current_count
        await page.evaluate("window.scrollBy(0, window.innerHeight);")
        await human_delay(0.8, 1.5)
    logger.info("Scroll loop finished, potential containers found: {}", prev_count)

    async def _extract_items_from_dom() -> list[dict]:
        return await page.evaluate("""() => {
            const items = [];
            // Track the current category as we scan down the page
            let currentCategory = "General";
            
            // Get all elements that could be headers or item containers
            const elements = document.querySelectorAll('h3, h4, [class*="MenuItemContainer"], [class*="sc-"]');
            
            for (const el of elements) {
                const tagName = el.tagName.toLowerCase();
                const text = el.innerText || "";
                
                // 1. Category Detection (h3 or h4 that doesn't look like a dish name)
                if (tagName === 'h3' || (tagName === 'h4' && text.length < 30 && !el.closest('[class*="MenuItem"]'))) {
                    const catText = text.trim();
                    if (catText && catText.length > 2 && !catText.includes('₹')) {
                        currentCategory = catText;
                    }
                    continue;
                }

                // 2. Dish Item Detection (h4 inside a container)
                const h4 = el.tagName === 'H4' ? el : el.querySelector('h4');
                if (h4 && el.innerText.includes('₹')) {
                    const item_name = h4.innerText.trim();
                    if (!item_name || items.some(it => it.item_name === item_name)) continue;

                    const containerText = el.innerText;
                    
                    // Price
                    let price = null;
                    const m = containerText.match(/₹\s?([\d,]+)/);
                    if (m) price = parseFloat(m[1].replace(/,/g, ''));

                    // Veg/Non-Veg (Check icons or specific text)
                    let is_veg = null;
                    const icon = el.querySelector('[class*="veg"], [class*="non-veg"], [alt*="veg"]');
                    if (icon) {
                        const iconClass = (icon.className || "").toLowerCase();
                        const iconAlt = (icon.getAttribute('alt') || "").toLowerCase();
                        if ((iconClass + iconAlt).includes('non-veg') || (iconClass + iconAlt).includes('nonveg')) is_veg = '0';
                        else if ((iconClass + iconAlt).includes('veg')) is_veg = '1';
                    }
                    if (!is_veg) {
                        if (containerText.toLowerCase().includes('non-veg')) is_veg = '0';
                        else if (containerText.toLowerCase().includes('pure veg')) is_veg = '1';
                    }

                    // Bestseller
                    const isBestseller = /BESTSELLER|MUST TRY|POPULAR/i.test(containerText) ? '1' : '0';

                    // Description
                    const p = el.querySelector('p');
                    const description = p ? p.innerText.trim() : null;

                    items.push({
                        item_name,
                        price,
                        category: currentCategory,
                        is_veg,
                        bestseller: isBestseller,
                        description
                    });
                }
            }
            return items;
        }""")

    # First attempt
    items = await _extract_items_from_dom()
    if not items:
        # perform one final absolute-bottom scroll and retry once (helps when React defers final render)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await human_delay(1, 2)
        except Exception:
            pass
        items = await _extract_items_from_dom()

    if items:
        logger.info(f"Extracted {len(items)} menu items from order page DOM")
        return items, []

    # 3. Fallback: /menu images only after /order DOM extraction fails completely
    logger.info("No menu items found on /order DOM — falling back to /menu: {}", menu_url)
    result = await _try_extract(menu_url, allow_image_return=True)
    if result is not None:
        return result

    logger.info("No structured data found on /order or /menu")
    return [], []
