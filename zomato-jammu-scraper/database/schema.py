import sqlite3
import datetime
from config import DB_PATH


def create_tables():
    """Create the database schema with restaurants, reviews, and menu_items tables."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create restaurants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                price_for_two REAL,
                rating REAL,
                distance TEXT,
                delivery_time TEXT,
                offer TEXT,
                total_orders TEXT,
                safety_badge TEXT,
                cuisines TEXT,
                address TEXT,
                open_status TEXT,
                timings TEXT,
                zomato_url TEXT UNIQUE,
                latitude TEXT,
                longitude TEXT,
                exact_votes TEXT,
                dining_rating REAL,
                dining_votes TEXT,
                delivery_rating REAL,
                delivery_votes TEXT,
                highlights TEXT,
                menu_images TEXT,
                city TEXT DEFAULT 'Jammu',
                state TEXT DEFAULT 'J&K',
                scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create reviews table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER,
                reviewer_name TEXT,
                review_text TEXT,
                rating REAL,
                review_order INTEGER,
                review_timestamp TEXT,
                scraped_at TEXT,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
            )
        """)

        # Create menu_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER,
                item_name TEXT NOT NULL,
                price REAL,
                category TEXT,
                is_veg TEXT,
                bestseller TEXT,
                description TEXT,
                scraped_at TEXT,
                FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
                UNIQUE(restaurant_id, item_name)
            )
        """)

        # ── Indexes for Performance ──────────────────────────────────────────
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rest_city ON restaurants(city)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rest_name ON restaurants(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rev_rest_id ON reviews(restaurant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_rest_id ON menu_items(restaurant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_item_name ON menu_items(item_name)")

        conn.commit()

        # Run migration for existing databases to add any missing columns
        migrate_schema(conn)

    except sqlite3.Error as e:
        print(f"Database error during schema creation: {e}")
        raise
    finally:
        if conn:
            conn.close()


def migrate_schema(conn):
    """Add new columns to existing databases without breaking them."""
    cursor = conn.cursor()
    # New columns for restaurants table
    for col in ["distance", "delivery_time", "offer", "total_orders", "safety_badge", "cuisines", "address", "open_status", "timings", "latitude", "longitude", "exact_votes", "dining_rating", "dining_votes", "delivery_rating", "delivery_votes", "highlights", "menu_images"]:
        try:
            cursor.execute(f"ALTER TABLE restaurants ADD COLUMN {col} TEXT")
        except Exception:
            pass  # Column already exists
    # New columns for reviews table
    for col in ["reviewer_name", "review_timestamp"]:
        try:
            cursor.execute(f"ALTER TABLE reviews ADD COLUMN {col} TEXT")
        except Exception:
            pass  # Column already exists
    # New columns for menu_items table
    for col in ["is_veg", "bestseller", "description"]:
        try:
            cursor.execute(f"ALTER TABLE menu_items ADD COLUMN {col} TEXT")
        except Exception:
            pass  # Column already exists
    conn.commit()


def reset_database():
    """Drop all tables and recreate the schema."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON")

        # Drop tables in correct order (child tables first, then parent)
        cursor.execute("DROP TABLE IF EXISTS menu_items")
        cursor.execute("DROP TABLE IF EXISTS reviews")
        cursor.execute("DROP TABLE IF EXISTS restaurants")
        conn.commit()
        conn.close()
        conn = None

        # Recreate tables
        create_tables()

    except sqlite3.Error as e:
        print(f"Database error during reset: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    try:
        create_tables()
        print("Database schema created successfully")
    except Exception as e:
        print(f"Failed to create database schema: {e}")