import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def insert_restaurant(name, phone, price_for_two, rating, zomato_url, distance=None, delivery_time=None, offer=None, total_orders=None, safety_badge=None, cuisines=None, address=None, open_status=None, timings=None, latitude=None, longitude=None, exact_votes=None, dining_rating=None, dining_votes=None, delivery_rating=None, delivery_votes=None, highlights=None, menu_images=None, city='Jammu', state='J&K'):
    """Insert or Update a restaurant. Refreshes rating/votes if already exists."""
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            # We use UPSERT to update existing records with new ratings/votes
            cursor.execute("""
                INSERT INTO restaurants (name, phone, price_for_two, rating, zomato_url, distance, delivery_time, offer, total_orders, safety_badge, cuisines, address, open_status, timings, latitude, longitude, exact_votes, dining_rating, dining_votes, delivery_rating, delivery_votes, highlights, menu_images, city, state, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(zomato_url) DO UPDATE SET
                    rating=excluded.rating,
                    exact_votes=excluded.exact_votes,
                    dining_rating=excluded.dining_rating,
                    dining_votes=excluded.dining_votes,
                    delivery_rating=excluded.delivery_rating,
                    delivery_votes=excluded.delivery_votes,
                    phone=COALESCE(excluded.phone, restaurants.phone),
                    price_for_two=COALESCE(excluded.price_for_two, restaurants.price_for_two),
                    scraped_at=excluded.scraped_at
            """, (name, phone, price_for_two, rating, zomato_url, distance, delivery_time, offer, total_orders, safety_badge, cuisines, address, open_status, timings, latitude, longitude, exact_votes, dining_rating, dining_votes, delivery_rating, delivery_votes, highlights, menu_images, city, state, datetime.now().isoformat()))
            conn.commit()

            cursor.execute("SELECT id FROM restaurants WHERE zomato_url = ?", (zomato_url,))
            row = cursor.fetchone()
            return row["id"] if row else None
        except Exception as e:
            print(f"Error inserting/updating restaurant: {e}")
            raise

def delete_restaurant_reviews(restaurant_id):
    """Delete all reviews for a specific restaurant (to refresh them)."""
    with get_db() as conn:
        conn.execute("DELETE FROM reviews WHERE restaurant_id = ?", (restaurant_id,))
        conn.commit()

def insert_review(restaurant_id, review_text, rating, review_order, reviewer_name=None, review_timestamp=None):
    """Insert one review."""
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reviews (restaurant_id, reviewer_name, review_text, rating, review_order, review_timestamp, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, reviewer_name, review_text, rating, review_order, review_timestamp, datetime.now().isoformat()))
            conn.commit()
        except Exception as e:
            print(f"Error inserting review: {e}")
            raise


def insert_menu_item(restaurant_id, item_name, price, category, is_veg=None, bestseller=None, description=None):
    """Insert one menu item."""
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO menu_items (restaurant_id, item_name, price, category, is_veg, bestseller, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, item_name, price, category, is_veg, bestseller, description, datetime.now().isoformat()))
            conn.commit()
        except Exception as e:
            print(f"Error inserting menu item: {e}")
            raise


def get_restaurant_by_url(url):
    """Query restaurants table by zomato_url. Returns a dict or None."""
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM restaurants WHERE zomato_url = ?", (url,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error getting restaurant by url: {e}")
            raise


def get_all_restaurants():
    """Return all restaurants as list of dicts."""
    with get_db() as conn:
        try:
            rows = conn.execute("SELECT * FROM restaurants").fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting all restaurants: {e}")
            raise


def get_reviews_by_restaurant(restaurant_id):
    """Return all reviews for a restaurant ordered by review_order."""
    with get_db() as conn:
        try:
            rows = conn.execute("""
                SELECT * FROM reviews
                WHERE restaurant_id = ? ORDER BY review_order
            """, (restaurant_id,)).fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting reviews by restaurant: {e}")
            raise


def get_menu_items_by_restaurant(restaurant_id):
    """Return all menu items for a restaurant."""
    with get_db() as conn:
        try:
            rows = conn.execute("""
                SELECT * FROM menu_items
                WHERE restaurant_id = ?
            """, (restaurant_id,)).fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting menu items by restaurant: {e}")
            raise


if __name__ == "__main__":
    from database.schema import create_tables, reset_database

    create_tables()

    # Insert a test restaurant
    rid = insert_restaurant("Test Restaurant", "1234567890", 500.0, 4.5, "https://zomato.com/test")
    print(f"Inserted restaurant ID: {rid}")

    # Insert a test review and menu item
    insert_review(rid, "Great food!", 5.0, 1)
    insert_menu_item(rid, "Biryani", 299.0, "Main Course")

    # Query them back and print the results
    r = get_restaurant_by_url("https://zomato.com/test")
    print(f"Queried restaurant: {r}")

    all_r = get_all_restaurants()
    print(f"All restaurants ({len(all_r)}): {all_r}")

    reviews = get_reviews_by_restaurant(rid)
    print(f"Reviews ({len(reviews)}): {reviews}")

    items = get_menu_items_by_restaurant(rid)
    print(f"Menu items ({len(items)}): {items}")

    # Clean up
    reset_database()
    print("Database reset — test complete.")
