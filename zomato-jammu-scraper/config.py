import json
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
LOGS_DIR = PROJECT_ROOT / "logs"

# Load from dashboard config if available
DASHBOARD_CONFIG = Path("d:/zomato-intel/config.json")
CONFIG_DATA = {}
if DASHBOARD_CONFIG.exists():
    try:
        CONFIG_DATA = json.loads(DASHBOARD_CONFIG.read_text())
    except: pass

# ── URLs ───────────────────────────────────────────────────────────────────
BASE_URL = CONFIG_DATA.get("target_url", "https://www.zomato.com/jammu/restaurants?category=1")

# ── Database ───────────────────────────────────────────────────────────────
DB_PATH = CONFIG_DATA.get("db_path", str(PROJECT_ROOT / "data" / "zomato_jammu_intel.db"))

# ── Timing ─────────────────────────────────────────────────────────────────
MIN_DELAY = CONFIG_DATA.get("min_delay", 10)
MAX_DELAY = CONFIG_DATA.get("max_delay", 20)

# ── Scraping limits ────────────────────────────────────────────────────────
MAX_REVIEWS = CONFIG_DATA.get("max_reviews", 50)
CHROME_USER_DATA = CONFIG_DATA.get("chrome_profile", r"D:\zomato_scraper_profile")
DEFAULT_CITY = CONFIG_DATA.get("default_city", "jammu")
DEFAULT_STATE = CONFIG_DATA.get("default_state", "J&K")
