"""Flask web application for Azure-Inspect (the dashboard)."""
from __future__ import annotations

from flask import Flask, jsonify, render_template_string

from ..config import load_config
from ..costs import cost_by_resource_group
from ..logs import get_activity_log
from ..resources import list_resource_groups

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Azure-Inspect</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --fg:#c9d1d9;
          --accent:#58a6ff; --green:#3fb950; --red:#f85149; --muted:#8b949e; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; margin:0; background:var(--bg);
         color:var(--fg); }
  header { display:flex; align-items:center; justify-content:space-between;
           padding:1rem 2rem; border-bottom:1px solid var(--border); }
  header h1 { margin:0; font-size:1.3rem; color:var(--accent); }
  #meta { font-size:.8rem; color:var(--muted); }
  #refresh { background:var(--panel); color:var(--fg); border:1px solid var(--border);
             border-radius:6px; padding:.4rem .8rem; cursor:pointer; }
  #refresh:hover { border-color:var(--accent); }
  main { padding:2rem; max-width:1100px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; margin-bottom:2rem; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:1rem; }
  .card .k { font-size:.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  .card .v { font-size:1.6rem; font-weight:600; margin-top:.3rem; color:var(--accent); }
  section { margin-bottom:2rem; }
  h2 { font-size:1rem; border-bottom:1px solid var(--border); padding-bottom:.4rem; }
  table { border-collapse:collapse; width:100%; font-size:.85rem; }
  th, td { border-bottom:1px solid var(--border); padding:6px 10px; text-align:left; }
  th { color:var(--muted); font-weight:500; }
  .bar { height:8px; background:var(--accent); border-radius:4px; }
  .pill { padding:1px 8px; border-radius:10px; font-size:.75rem; }
  .ok { background:rgba(63,185,80,.15); color:var(--green); }
  .fail { background:rgba(248,81,73,.15); color:var(--red); }
  .state { background:rgba(88,166,255,.15); color:var(--accent); }
  .err { color:var(--red); padding:1rem; background:rgba(248,81,73,.1); border-radius:6px; }
  .muted { color:var(--muted); }
  .loading { color:var(--muted); font-style:italic; }
</style>
</head>
<body>
<header>
  <h1>Azure-Inspect</h1>
  <div style="display:flex; gap:1rem; align-items:center;">
    <span id="meta">subscription: <span id="sub">…</span></span>
    <button id="refresh">Refresh</button>
  </div>
</header>
<main>
  <div class="cards" id="cards">
    <div class="card"><div class="k">Resource groups</div><div class="v" id="c-rg">–</div></div>
    <div class="card"><div class="k">Total cost (30d)</div><div class="v" id="c-cost">–</div></div>
    <div class="card"><div class="k">Activity (24h)</div><div class="v" id="c-act">–</div></div>
  </div>

  <section><h2>Resource groups</h2><div id="rg"><p class="loading">Loading…</p></div></section>
  <section><h2>Cost by resource group (30d)</h2><div id="cost"><p class="loading">Loading…</p></div></section>
  <section><h2>Activity log (24h)</h2><div id="logs"><p class="loading">Loading…</p></div></section>
</main>
<script>
const COLS = {
  rg: ['name','location','provisioning_state'],
  cost: ['resource_group','bar','cost','currency'],
  logs: ['event_timestamp','operation','resource_group','caller','status'],
};

function esc(s){ return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function fmtTs(iso){ try { return new Date(iso).toLocaleString(); } catch { return iso; } }

async function fill(id, url, render){
  const el = document.getElementById(id);
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) { el.innerHTML = '<p class="err">'+esc(data.error)+'</p>'; return; }
    render(el, data);
  } catch(e){ el.innerHTML = '<p class="err">'+esc(e)+'</p>'; }
}

function renderRg(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No resource groups.</p>'; return; }
  let rows = data.map(d => '<tr><td>'+esc(d.name)+'</td><td>'+esc(d.location)+
    '</td><td><span class="pill state">'+esc(d.provisioning_state)+'</span></td></tr>').join('');
  el.innerHTML = '<table><tr><th>Name</th><th>Location</th><th>State</th></tr>'+rows+'</table>';
}

function renderCost(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No cost data.</p>'; return; }
  const max = Math.max(...data.map(d => d.cost), 0.0001);
  let rows = data.sort((a,b)=>b.cost-a.cost).map(d => {
    const pct = (d.cost / max * 100).toFixed(0);
    return '<tr><td>'+esc(d.resource_group||'(none)')+'</td>'+
      '<td style="width:120px"><div class="bar" style="width:'+pct+'%"></div></td>'+
      '<td>'+Number(d.cost).toFixed(2)+'</td><td>'+esc(d.currency)+'</td></tr>';
  }).join('');
  el.innerHTML = '<table><tr><th>Resource group</th><th></th><th>Cost</th><th>Cur</th></tr>'+rows+'</table>';
}

function renderLogs(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No recent activity.</p>'; return; }
  let rows = data.slice(0,50).map(d => {
    const st = (d.status||'').toLowerCase().includes('fail') ? 'fail' : 'ok';
    return '<tr><td>'+esc(fmtTs(d.event_timestamp))+'</td><td>'+esc(d.operation)+
      '</td><td>'+esc(d.resource_group)+'</td><td>'+esc(d.caller)+
      '</td><td><span class="pill '+st+'">'+esc(d.status)+'</span></td></tr>';
  }).join('');
  el.innerHTML = '<table><tr><th>Time</th><th>Operation</th><th>RG</th><th>Caller</th><th>Status</th></tr>'+rows+'</table>';
}

async function loadAll(){
  // subscription id + summary
  try {
    const s = await (await fetch('/api/summary')).json();
    document.getElementById('sub').textContent = s.subscription_id || '?';
    document.getElementById('c-rg').textContent = s.resource_group_count ?? '–';
    document.getElementById('c-cost').textContent = s.total_cost != null ? s.total_cost.toFixed(2)+' '+(s.currency||'') : '–';
    document.getElementById('c-act').textContent = s.activity_count ?? '–';
  } catch(e){ /* leave placeholders */ }

  fill('rg', '/api/resources', renderRg);
  fill('cost', '/api/costs', renderCost);
  fill('logs', '/api/logs', renderLogs);
}

document.getElementById('refresh').addEventListener('click', loadAll);
loadAll();
setInterval(loadAll, 60000); // auto-refresh every minute
</script>
</body>
</html>
"""


def _safe(fn):
    """Wrap a data-fetching callable; return (payload, status).

    On success: returns (payload_dict, 200).
    On exception: returns ({"error": message}, 500).

    Flask serializes the dict to JSON and honors the status code when the
    caller returns the tuple directly (i.e. ``return _safe(_compute)``).
    """
    try:
        return fn(), 200
    except Exception as exc:  # surface API errors to the dashboard
        return {"error": str(exc)}, 500


def create_app(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> Flask:
    """Build and return the Flask application.

    Args:
        host: bind host (default 127.0.0.1).
        port: bind port (default 5000) — informational; the app object is
            returned and run by the caller.
        debug: Flask debug mode.
    """
    app = Flask(__name__)
    app.config["HOST"] = host
    app.config["PORT"] = port

    @app.route("/")
    def index():
        return render_template_string(_INDEX_HTML)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/summary")
    def api_summary():
        def _compute():
            cfg = load_config()
            rgs = list_resource_groups(cfg)
            costs = cost_by_resource_group(cfg)
            total = sum(c.cost for c in costs)
            currency = costs[0].currency if costs else ""
            # activity count uses a lightweight fetch window
            logs = get_activity_log(cfg, hours=24)
            return {
                "subscription_id": cfg.subscription_id,
                "resource_group_count": len(rgs),
                "total_cost": round(total, 2),
                "currency": currency,
                "activity_count": len(logs),
            }
        return _safe(_compute)

    @app.route("/api/resources")
    def api_resources():
        def _compute():
            cfg = load_config()
            return [
                {
                    "name": rg.name,
                    "location": rg.location,
                    "provisioning_state": rg.provisioning_state,
                }
                for rg in list_resource_groups(cfg)
            ]
        return _safe(_compute)

    @app.route("/api/costs")
    def api_costs():
        def _compute():
            cfg = load_config()
            return [
                {
                    "resource_group": c.resource_group,
                    "cost": c.cost,
                    "currency": c.currency,
                }
                for c in cost_by_resource_group(cfg)
            ]
        return _safe(_compute)

    @app.route("/api/logs")
    def api_logs():
        def _compute():
            cfg = load_config()
            return [
                {
                    "event_timestamp": e.event_timestamp.isoformat(),
                    "operation": e.operation,
                    "resource_group": e.resource_group,
                    "caller": e.caller,
                    "status": e.status,
                }
                for e in get_activity_log(cfg)
            ]
        return _safe(_compute)

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
