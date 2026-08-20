"""Launch the Azure-Inspect Flask dashboard, bound for LAN access."""
import os

from dotenv import load_dotenv

load_dotenv(".env")  # real Azure credentials

from azure_inspect.ui.app import create_app
from azure_inspect.cache import DataCache
from azure_inspect.refresher import start_refresher

cache = DataCache()
# Warm the cache in the background so the dashboard is instant and resilient.
start_refresher(cache, interval_min=int(os.getenv("REFRESH_INTERVAL_MIN", "15")))

app = create_app()
# Bind to all interfaces so it's reachable from the LAN, not just localhost.
app.run(host="0.0.0.0", port=5010, debug=False)
