"""Flask web application for Azure-Inspect (the dashboard)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template_string

from ..config import load_config
from ..costs import cost_by_resource_group
from ..logs import get_activity_log
from ..resources import list_resource_groups

_INDEX_HTML = """<!doctype html>
<title>Azure-Inspect</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #0d1117; color: #c9d1d9; }
  h1 { color: #58a6ff; }
  section { margin-bottom: 2rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #30363d; padding: 6px 10px; text-align: left; }
  th { background: #161b22; }
  .err { color: #f85149; }
</style>
<h1>Azure-Inspect</h1>
<section><h2>Resource groups</h2><div id="rg"></div></section>
<section><h2>Cost (30d)</h2><div id="cost"></div></section>
<section><h2>Activity (24h)</h2><div id="logs"></div></section>
<script>
async function fill(id, url, cols) {
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) { document.getElementById(id).innerHTML = '<p class="err">' + data.error + '</p>'; return; }
    let rows = data.map(d => '<tr>' + cols.map(c => '<td>' + (d[c] ?? '') + '</td>').join('') + '</tr>').join('');
    document.getElementById(id).innerHTML = '<table><tr>' + cols.map(c => '<th>' + c + '</th>').join('') + '</tr>' + rows + '</table>';
  } catch (e) { document.getElementById(id).innerHTML = '<p class="err">' + e + '</p>'; }
}
fill('rg', '/api/resources', ['name', 'location', 'provisioning_state']);
fill('cost', '/api/costs', ['resource_group', 'cost', 'currency']);
fill('logs', '/api/logs', ['event_timestamp', 'operation', 'resource_group', 'caller', 'status']);
</script>
"""


def create_app() -> Flask:
    """Build and return the Flask application."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(_INDEX_HTML)

    @app.route("/api/resources")
    def api_resources():
        try:
            cfg = load_config()
            data = [
                {
                    "name": rg.name,
                    "location": rg.location,
                    "provisioning_state": rg.provisioning_state,
                }
                for rg in list_resource_groups(cfg)
            ]
            return jsonify(data)
        except Exception as exc:  # surface API errors to the dashboard
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/costs")
    def api_costs():
        try:
            cfg = load_config()
            data = [
                {
                    "resource_group": c.resource_group,
                    "cost": c.cost,
                    "currency": c.currency,
                }
                for c in cost_by_resource_group(cfg)
            ]
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/logs")
    def api_logs():
        try:
            cfg = load_config()
            data = [
                {
                    "event_timestamp": e.event_timestamp.isoformat(),
                    "operation": e.operation,
                    "resource_group": e.resource_group,
                    "caller": e.caller,
                    "status": e.status,
                }
                for e in get_activity_log(cfg)
            ]
            return jsonify(data)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
