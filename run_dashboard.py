"""Launch the Azure-Inspect Flask dashboard, bound for LAN access."""
import os

from dotenv import load_dotenv

load_dotenv(".env")  # real Azure credentials

from azure_inspect.ui.app import create_app

app = create_app()
# Bind to all interfaces so it's reachable from the LAN, not just localhost.
app.run(host="0.0.0.0", port=5010, debug=False)
