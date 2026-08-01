"""Flask web application for Azure-Inspect (the dashboard)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from flask import Flask, jsonify, render_template_string, request

from ..config import AzureConfig, load_config
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
           padding:1rem 2rem; border-bottom:1px solid var(--border); flex-wrap:wrap; gap:.5rem; }
  header h1 { margin:0; font-size:1.3rem; color:var(--accent); }
  #controls { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; }
  #meta { font-size:.8rem; color:var(--muted); }
  select, button { background:var(--panel); color:var(--fg); border:1px solid var(--border);
             border-radius:6px; padding:.4rem .8rem; cursor:pointer; font:inherit; }
  button:hover, select:hover { border-color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  main { padding:2rem; max-width:1100px; margin:0 auto; }
  .banner { padding:.7rem 1rem; border-radius:6px; margin-bottom:1.5rem; font-size:.85rem; display:none; }
  .banner.warn { display:block; background:rgba(248,81,73,.12); border:1px solid var(--red); color:var(--red); }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; margin-bottom:2rem; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:1rem; }
  .card .k { font-size:.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  .card .v { font-size:1.6rem; font-weight:600; margin-top:.3rem; color:var(--accent); }
  section { margin-bottom:2rem; }
  .section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; border-bottom:1px solid var(--border); padding-bottom:.4rem; margin-bottom:.6rem; }
  h2 { font-size:1rem; margin:0; }
  input[type=search] { background:var(--panel); color:var(--fg); border:1px solid var(--border);
             border-radius:6px; padding:.3rem .6rem; font:inherit; min-width:200px; }
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
  <div id="controls">
    <span id="meta">subscription: <span id="sub">…</span> · <span id="updated">–</span></span>
    <label>Cost window
      <select id="days">
        <option value="7">7d</option>
        <option value="30" selected>30d</option>
        <option value="90">90d</option>
      </select>
    </label>
    <label><input type="checkbox" id="auto" checked> auto</label>
    <button id="refresh">Refresh</button>
  </div>
</header>
<div class="banner warn" id="banner"></div>
<main>
  <div class="cards" id="cards">
    <div class="card"><div class="k">Resource groups</div><div class="v" id="c-rg">–</div></div>
    <div class="card"><div class="k">Total cost</div><div class="v" id="c-cost">–</div></div>
    <div class="card"><div class="k">Activity</div><div class="v" id="c-act">–</div></div>
  </div>

  <section>
    <div class="section-head">
      <h2>Resource groups</h2>
      <input type="search" id="rg-search" placeholder="filter…">
    </div>
    <div id="rg"><p class="loading">Loading…</p></div>
  </section>
  <section><h2>Cost by resource group</h2><div id="cost"><p class="loading">Loading…</p></div></section>
  <section><h2>Activity log</h2><div id="logs"><p class="loading">Loading…</p></div></section>
</main>
<script>
const COLS = {
  rg: ['name','location','provisioning_state'],
  cost: ['resource_group','bar','cost','currency'],
  logs: ['event_timestamp','operation','resource_group','caller','status'],
};

function esc(s){ return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function fmtTs(iso){ try { return new Date(iso).toLocaleString(); } catch { return iso; } }

function stamp(){
  document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
}

async function fill(id, url, render, searchId){
  const el = document.getElementById(id);
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) {
      if (data.code === 'not_configured' || data.code === 'auth_error') {
        showBanner(data.error);
        el.innerHTML = '<p class="muted">Check the banner above for details.</p>';
        return;
      }
      el.innerHTML = '<p class="err">'+esc(data.error)+'</p>'; return;
    }
    if (searchId) {
      const q = (document.getElementById(searchId).value || '').toLowerCase();
      if (q) data = data.filter(d => JSON.stringify(d).toLowerCase().includes(q));
    }
    render(el, data);
    stamp();
  } catch(e){ el.innerHTML = '<p class="err">'+esc(e)+'</p>'; }
}

function showBanner(msg){
  const b = document.getElementById('banner');
  b.textContent = '⚠ ' + msg;
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
  const btn = document.getElementById('refresh');
  btn.disabled = true; btn.textContent = 'Refreshing…';
  try {
    const s = await (await fetch('/api/summary')).json();
    if (s.error) {
      if (s.code === 'not_configured') {
        showBanner(s.error);
      } else {
        document.getElementById('banner').textContent = '';
      }
      document.getElementById('sub').textContent = '?';
      document.getElementById('c-rg').textContent = '–';
      document.getElementById('c-cost').textContent = '–';
      document.getElementById('c-act').textContent = '–';
    } else {
      showBanner('');
      document.getElementById('sub').textContent = s.subscription_id || '?';
      document.getElementById('c-rg').textContent = s.resource_group_count ?? '–';
      document.getElementById('c-cost').textContent = s.total_cost != null ? s.total_cost.toFixed(2)+' '+(s.currency||'') : '–';
      document.getElementById('c-act').textContent = s.activity_count ?? '–';
    }

    const days = document.getElementById('days').value;
    fill('rg', '/api/resources', renderRg, 'rg-search');
    fill('cost', '/api/costs?days='+days, renderCost);
    fill('logs', '/api/logs', renderLogs);
  } finally {
    btn.disabled = false; btn.textContent = 'Refresh';
  }
}

let timer = null;
function setupAuto(){
  if (timer) clearInterval(timer);
  const on = document.getElementById('auto').checked;
  if (on) timer = setInterval(loadAll, 60000);
}
document.getElementById('auto').addEventListener('change', setupAuto);
document.getElementById('refresh').addEventListener('click', loadAll);
document.getElementById('days').addEventListener('change', loadAll);
document.getElementById('rg-search').addEventListener('input', () => fill('rg', '/api/resources', renderRg, 'rg-search'));
loadAll();
setupAuto();
</script>
</body>
</html>
"""


_NOT_CONFIGURED = {
    "error": "Azure credentials are not configured. Set AZURE_TENANT_ID, "
             "AZURE_CLIENT_ID, AZURE_CLIENT_SECRET and AZURE_SUBSCRIPTION_ID.",
    "code": "not_configured",
}


def _load_cfg(config_provider: Callable[[], AzureConfig] | None):
    """Resolve the AzureConfig, or return None when not configured."""
    if config_provider is not None:
        try:
            return config_provider()
        except Exception:
            return None
    try:
        return load_config()
    except Exception:
        return None


def _classify_error(exc: Exception) -> tuple[dict, int]:
    """Turn a data-fetch exception into a friendly, UI-classifiable payload.

    Azure auth/permission failures (401/403, expired or wrong-tenant tokens,
    missing roles) are reported with a dedicated ``auth_error`` code and a 503
    so the dashboard can show an actionable banner instead of a raw API blob.
    Any other failure falls through to a generic 500.
    """
    msg = str(exc)
    lowered = msg.lower()
    auth_signals = (
        "401" in msg,
        "403" in msg,
        "invalidauthenticationtoken" in lowered,
        "authorizationfailed" in lowered,
        "authentication failed" in lowered,
        "forbidden" in lowered,
        "unauthorized" in lowered,
    )
    if any(auth_signals):
        return {
            "error": "Azure rejected the request — check that the service "
                     "principal's tenant matches the subscription and that it "
                     "has Reader / Cost Management Reader roles. "
                     f"({msg[:160]})",
            "code": "auth_error",
        }, 503
    return {"error": msg}, 500


def _safe(fn, config_provider=None):
    """Wrap a data-fetching callable; return (payload, status).

    On success: returns (payload_dict, 200).
    When Azure credentials are missing: returns the not-configured payload
    with a 503 so the dashboard can show a friendly banner instead of a raw
    error box.
    On an Azure auth/permission failure: returns a classified ``auth_error``
    payload with a 503 so the UI can show an actionable banner.
    On any other exception: returns ({"error": message}, 500).
    """
    cfg = _load_cfg(config_provider)
    if cfg is None:
        return dict(_NOT_CONFIGURED), 503
    try:
        return fn(cfg), 200
    except Exception as exc:  # surface API errors to the dashboard
        return _classify_error(exc)


def _coerce_days(raw: str | None, default: int = 30) -> int:
    """Parse the ?days= query param into a safe int (7/30/90 clamped)."""
    try:
        d = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    if d not in (7, 30, 90):
        return default
    return d


def create_app(
    config_provider: Optional[Callable[[], AzureConfig]] = None,
    debug: bool = False,
) -> Flask:
    """Build and return the Flask application.

    Args:
        config_provider: callable returning an ``AzureConfig``. When omitted,
            the app falls back to ``load_config()`` (env/.env). Injecting a
            provider keeps the app testable and lets callers supply config
            without touching the environment.
        debug: Flask debug mode.
    """
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(_INDEX_HTML)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/summary")
    def api_summary():
        def _compute(cfg):
            rgs = list_resource_groups(cfg)
            costs = cost_by_resource_group(cfg, from_date=date_window(30))
            total = sum(c.cost for c in costs)
            currency = costs[0].currency if costs else ""
            logs = get_activity_log(cfg, hours=24)
            return {
                "subscription_id": cfg.subscription_id,
                "resource_group_count": len(rgs),
                "total_cost": round(total, 2),
                "currency": currency,
                "activity_count": len(logs),
            }
        return _safe(_compute, config_provider)

    @app.route("/api/resources")
    def api_resources():
        def _compute(cfg):
            return [
                {
                    "name": rg.name,
                    "location": rg.location,
                    "provisioning_state": rg.provisioning_state,
                }
                for rg in list_resource_groups(cfg)
            ]
        return _safe(_compute, config_provider)

    @app.route("/api/costs")
    def api_costs():
        days = _coerce_days(request.args.get("days"))
        def _compute(cfg):
            return [
                {
                    "resource_group": c.resource_group,
                    "cost": c.cost,
                    "currency": c.currency,
                }
                for c in cost_by_resource_group(cfg, from_date=date_window(days))
            ]
        return _safe(_compute, config_provider)

    @app.route("/api/logs")
    def api_logs():
        def _compute(cfg):
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
        return _safe(_compute, config_provider)

    return app


def date_window(days: int):
    """Return the ``from_date`` (date) for a trailing ``days`` window."""
    from datetime import date, timedelta
    return date.today() - timedelta(days=days)


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
