"""
Centralized configuration constants for Humble Library Sync.
All global settings and URLs are defined here so that service modules
can import them from a single source of truth.
"""

from pathlib import Path

# Browser User-Agent to avoid bot detection
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Humble Bundle URLs
BUNDLES_URL = "https://www.humblebundle.com/bundles"

# Default paths and TTL
BUNDLES_DUMP_PATH = Path("raw_bundles_dump.json")
CACHE_TTL_SECONDS = 21600  # 6 hours