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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e17; --panel: rgba(22,27,34,.72); --panel-solid: #11161f;
    --border: rgba(255,255,255,.08); --fg: #e6edf3; --muted: #8b98a9;
    --accent: #58a6ff; --accent2: #39d3ff; --green: #3fb950; --red: #ff6b6b;
    --radius: 16px; --shadow: 0 8px 30px rgba(0,0,0,.35);
  }
  * { box-sizing: border-box; }
  html, body { margin:0; }
  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background:
      radial-gradient(1200px 600px at 85% -10%, rgba(88,166,255,.12), transparent 60%),
      radial-gradient(900px 500px at 10% 110%, rgba(57,211,255,.08), transparent 55%),
      var(--bg);
    color: var(--fg); min-height: 100vh; -webkit-font-smoothing: antialiased;
  }
  header {
    position: sticky; top:0; z-index: 10; display:flex; align-items:center; justify-content:space-between;
    padding: 1rem 1.8rem; border-bottom: 1px solid var(--border);
    background: rgba(10,14,23,.6); backdrop-filter: blur(14px); flex-wrap:wrap; gap:.6rem;
  }
  .brand { display:flex; align-items:center; gap:.7rem; }
  .brand svg { width:30px; height:30px; filter: drop-shadow(0 0 8px rgba(88,166,255,.5)); }
  .brand h1 { margin:0; font-size:1.25rem; font-weight:800; letter-spacing:-.02em;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; background-clip:text; -webkit-text-fill-color: transparent; }
  #controls { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; }
  #meta { font-size:.8rem; color:var(--muted); }
  #meta b { color: var(--fg); font-weight:600; }
  select, button {
    background: var(--panel-solid); color: var(--fg); border: 1px solid var(--border);
    border-radius: 10px; padding:.45rem .8rem; cursor:pointer; font:inherit; font-size:.82rem;
    transition: border-color .15s, transform .05s, box-shadow .15s;
  }
  button:hover, select:hover { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,166,255,.12); }
  button:active { transform: translateY(1px); }
  button:disabled { opacity:.5; cursor:default; box-shadow:none; }
  input[type=checkbox]{ accent-color: var(--accent); }
  main { padding: 1.8rem; max-width: 1180px; margin: 0 auto; }
  .banner {
    padding:.8rem 1rem; border-radius: 12px; margin-bottom:1.4rem; font-size:.85rem;
    display:none; align-items:center; gap:.5rem; border:1px solid rgba(255,107,107,.4);
    background: rgba(255,107,107,.1); color: var(--red);
  }
  .banner.warn { display:flex; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; margin-bottom:1.8rem; }
  .card {
    background: var(--panel); border:1px solid var(--border); border-radius: var(--radius);
    padding: 1.1rem 1.2rem; box-shadow: var(--shadow); backdrop-filter: blur(8px);
    position:relative; overflow:hidden;
  }
  .card::after { content:""; position:absolute; inset:0; background: linear-gradient(135deg, rgba(88,166,255,.06), transparent 50%); pointer-events:none; }
  .card .k { font-size:.72rem; color: var(--muted); text-transform:uppercase; letter-spacing:.08em; font-weight:600; }
  .card .v { font-size:1.9rem; font-weight:800; margin-top:.35rem; letter-spacing:-.02em; }
  .card.accent .v { background: linear-gradient(90deg,var(--accent),var(--accent2)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  section { margin-bottom: 1.8rem; background: var(--panel); border:1px solid var(--border); border-radius: var(--radius);
    padding: 1.1rem 1.2rem; box-shadow: var(--shadow); backdrop-filter: blur(8px); }
  .section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.8rem; }
  h2 { font-size:.95rem; margin:0; font-weight:700; display:flex; align-items:center; gap:.5rem; }
  h2 .dot { width:8px; height:8px; border-radius:50%; background: var(--accent); box-shadow:0 0 8px var(--accent); }
  input[type=search] { background: var(--panel-solid); color: var(--fg); border:1px solid var(--border); border-radius:10px; padding:.35rem .7rem; font:inherit; min-width:180px; font-size:.82rem; }
  table { border-collapse: collapse; width:100%; font-size:.85rem; }
  th, td { border-bottom: 1px solid var(--border); padding: .55rem .7rem; text-align:left; }
  th { color: var(--muted); font-weight:600; font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; }
  tbody tr { transition: background .12s; }
  tbody tr:hover { background: rgba(255,255,255,.03); }
  .bar-wrap { width:140px; }
  .bar { height:9px; border-radius:6px; background: linear-gradient(90deg, var(--accent), var(--accent2)); box-shadow: 0 0 10px rgba(57,211,255,.4); }
  .pill { padding:2px 9px; border-radius:999px; font-size:.74rem; font-weight:600; }
  .ok { background: rgba(63,185,80,.15); color: var(--green); }
  .fail { background: rgba(255,107,107,.15); color: var(--red); }
  .state { background: rgba(88,166,255,.15); color: var(--accent); }
  .loc { font-size:.72rem; color: var(--muted); }
  .err { color: var(--red); padding: 1rem; background: rgba(255,107,107,.08); border-radius:10px; border:1px solid rgba(255,107,107,.25); }
  .muted { color: var(--muted); }
  .loading { color: var(--muted); font-style: italic; display:flex; align-items:center; gap:.6rem; padding:.4rem 0; }
  .spin { width:14px; height:14px; border:2px solid var(--border); border-top-color: var(--accent); border-radius:50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  footer { text-align:center; color: var(--muted); font-size:.75rem; padding: 1.5rem; }
  a { color: var(--accent); text-decoration:none; }
  @media (max-width: 640px) { main { padding: 1rem; } header { padding:.8rem 1rem; } }
</style>
</head>
<body>
<header>
  <div class="brand">
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 16a4 4 0 0 1 .8-7.9 5 5 0 0 1 9.7-1.3A3.5 3.5 0 0 1 18 16H6Z" stroke="url(#g)" stroke-width="1.6" stroke-linejoin="round"/>
      <defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop stop-color="#58a6ff"/><stop offset="1" stop-color="#39d3ff"/></linearGradient></defs>
    </svg>
    <h1>Azure-Inspect</h1>
  </div>
  <div id="controls">
    <span id="meta">sub <b id="sub">…</b> · <span id="updated">–</span></span>
    <label>Cost
      <select id="days">
        <option value="7">7d</option>
        <option value="30" selected>30d</option>
        <option value="90">90d</option>
      </select>
    </label>
    <label title="Auto-refresh every 60s"><input type="checkbox" id="auto" checked> auto</label>
    <button id="refresh">↻ Refresh</button>
  </div>
</header>
<div class="banner warn" id="banner"></div>
<main>
  <div class="cards" id="cards">
    <div class="card accent"><div class="k">Resource groups</div><div class="v" id="c-rg">–</div></div>
    <div class="card accent"><div class="k">Total cost</div><div class="v" id="c-cost">–</div></div>
    <div class="card accent"><div class="k">Activity (24h)</div><div class="v" id="c-act">–</div></div>
  </div>

  <section>
    <div class="section-head">
      <h2><span class="dot"></span> Resource groups</h2>
      <input type="search" id="rg-search" placeholder="filter…">
    </div>
    <div id="rg"><p class="loading"><span class="spin"></span> Loading…</p></div>
  </section>

  <section><div class="section-head"><h2><span class="dot"></span> Cost by resource group</h2></div>
    <div id="cost"><p class="loading"><span class="spin"></span> Loading…</p></div></section>

  <section><div class="section-head"><h2><span class="dot"></span> Activity log</h2></div>
    <div id="logs"><p class="loading"><span class="spin"></span> Loading…</p></div></section>
</main>
<footer>Azure-Inspect · service-principal dashboard</footer>
<script>
function esc(s){ return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function fmtTs(iso){ try { return new Date(iso).toLocaleString(); } catch { return iso; } }
function rel(ts){
  try { const d = (Date.now() - new Date(ts).getTime())/1000;
    if (d<60) return d.toFixed(0)+'s ago';
    if (d<3600) return (d/60).toFixed(0)+'m ago';
    if (d<86400) return (d/3600).toFixed(0)+'h ago';
    return (d/86400).toFixed(0)+'d ago';
  } catch { return ''; }
}
function stamp(){ document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString(); }

async function fill(id, url, render, searchId){
  const el = document.getElementById(id);
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) {
      if (data.code === 'not_configured' || data.code === 'auth_error' || data.code === 'cost_data_unavailable') {
        showBanner(data.error);
        el.innerHTML = '<p class="muted">Check the banner above.</p>'; return;
      }
      el.innerHTML = '<p class="err">'+esc(data.error)+'</p>'; return;
    }
    if (searchId) {
      const q = (document.getElementById(searchId).value || '').toLowerCase();
      if (q) data = data.filter(d => JSON.stringify(d).toLowerCase().includes(q));
    }
    render(el, data); stamp();
  } catch(e){ el.innerHTML = '<p class="err">'+esc(e)+'</p>'; }
}

function showBanner(msg){
  const b = document.getElementById('banner');
  b.textContent = '⚠ ' + msg;
}

function renderRg(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No resource groups.</p>'; return; }
  let rows = data.map(d => '<tr><td><b>'+esc(d.name)+'</b></td><td><span class="loc">'+esc(d.location)+
    '</span></td><td><span class="pill state">'+esc(d.provisioning_state)+'</span></td></tr>').join('');
  el.innerHTML = '<table><thead><tr><th>Name</th><th>Location</th><th>State</th></tr></thead><tbody>'+rows+'</tbody></table>';
}

function renderCost(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No cost data.</p>'; return; }
  const max = Math.max(...data.map(d => d.cost), 0.0001);
  let rows = data.sort((a,b)=>b.cost-a.cost).map(d => {
    const pct = Math.max(2, (d.cost / max * 100)).toFixed(0);
    return '<tr><td><b>'+esc(d.resource_group||'(none)')+'</b></td>'+
      '<td class="bar-wrap"><div class="bar" style="width:'+pct+'%"></div></td>'+
      '<td>'+Number(d.cost).toFixed(2)+' '+esc(d.currency)+'</td></tr>';
  }).join('');
  el.innerHTML = '<table><thead><tr><th>Resource group</th><th></th><th>Cost</th></tr></thead><tbody>'+rows+'</tbody></table>';
}

function renderLogs(el, data){
  if(!data.length){ el.innerHTML = '<p class="muted">No recent activity.</p>'; return; }
  let rows = data.slice(0,60).map(d => {
    const st = (d.status||'').toLowerCase().includes('fail') ? 'fail' : 'ok';
    return '<tr><td title="'+esc(fmtTs(d.event_timestamp))+'">'+esc(rel(d.event_timestamp))+'</td>'+
      '<td>'+esc(d.operation)+'</td><td class="loc">'+esc(d.resource_group||'–')+'</td>'+
      '<td class="loc">'+esc(d.caller||'–')+'</td>'+
      '<td><span class="pill '+st+'">'+esc(d.status)+'</span></td></tr>';
  }).join('');
  el.innerHTML = '<table><thead><tr><th>When</th><th>Operation</th><th>RG</th><th>Caller</th><th>Status</th></tr></thead><tbody>'+rows+'</tbody></table>';
}

async function loadAll(){
  const btn = document.getElementById('refresh');
  btn.disabled = true; btn.textContent = '↻ Refreshing…';
  try {
    const s = await (await fetch('/api/summary')).json();
    if (s.error) {
      if (s.code === 'not_configured') showBanner(s.error);
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
    btn.disabled = false; btn.textContent = '↻ Refresh';
  }
}

let timer = null;
function setupAuto(){
  if (timer) clearInterval(timer);
  if (document.getElementById('auto').checked) timer = setInterval(loadAll, 60000);
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
    if "getazuresubscriptionbyid" in lowered or "costmanagement" in lowered:
        return {
            "error": "Azure Cost Management has no billing data for this "
                     "subscription yet. This commonly happens just after a "
                     "subscription is moved to a new tenant (data can take "
                     "hours to propagate) or when the service principal lacks "
                     "the Cost Management Reader role. "
                     f"({msg[:160]})",
            "code": "cost_data_unavailable",
        }, 503
    if "invalidresourcetype" in lowered and "insights" in lowered:
        return {
            "error": "The activity-log query used an unsupported API version. "
                     "This is a bug in Azure-Inspect — please report it. "
                     f"({msg[:160]})",
            "code": "log_query_error",
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
            from datetime import date, timedelta
            rgs = list_resource_groups(cfg)
            costs = cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=30))
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
                for c in cost_by_resource_group(cfg, from_date=_date_window(days))
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


def _date_window(days: int):
    """Return the ``from_date`` (date) for a trailing ``days`` window."""
    from datetime import date, timedelta
    return date.today() - timedelta(days=days)


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
