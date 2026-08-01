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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#070a12; --panel:rgba(20,26,38,.6); --panel-solid:#0e131d;
    --border:rgba(255,255,255,.09); --fg:#eaf1f8; --muted:#8593a6;
    --accent:#58a6ff; --accent2:#7c5cff; --cyan:#39d3ff; --green:#3ef0a3;
    --red:#ff6b81; --radius:18px; --shadow:0 10px 40px rgba(0,0,0,.45);
  }
  * { box-sizing:border-box; } html,body { margin:0; }
  body { font-family:'Inter',system-ui,sans-serif; color:var(--fg); min-height:100vh;
    background:var(--bg); overflow-x:hidden; -webkit-font-smoothing:antialiased; }
  .aurora { position:fixed; inset:-20%; z-index:-2; filter:blur(70px); opacity:.85;
    background:
      radial-gradient(40% 50% at 20% 30%, rgba(88,166,255,.30), transparent 60%),
      radial-gradient(45% 55% at 80% 25%, rgba(124,92,255,.28), transparent 60%),
      radial-gradient(50% 60% at 55% 85%, rgba(57,211,255,.22), transparent 60%);
    animation:drift 18s ease-in-out infinite alternate; }
  @keyframes drift { 0%{transform:translate3d(-3%,-2%,0) scale(1.05) rotate(0)} 50%{transform:translate3d(4%,3%,0) scale(1.15) rotate(8deg)} 100%{transform:translate3d(-2%,4%,0) scale(1.08) rotate(-6deg)} }
  .grain { position:fixed; inset:0; z-index:-1; pointer-events:none; opacity:.035;
    background-image:radial-gradient(rgba(255,255,255,.9) 1px, transparent 1px); background-size:3px 3px; }

  header { position:sticky; top:0; z-index:20; display:flex; align-items:center; justify-content:space-between;
    padding:1rem 1.9rem; border-bottom:1px solid var(--border);
    background:rgba(7,10,18,.55); backdrop-filter:blur(18px) saturate(140%); flex-wrap:wrap; gap:.7rem; }
  .brand { display:flex; align-items:center; gap:.75rem; }
  .brand svg { width:32px; height:32px; animation:float 5s ease-in-out infinite; }
  @keyframes float { 50%{transform:translateY(-3px)} }
  .brand h1 { margin:0; font-size:1.3rem; font-weight:800; letter-spacing:-.03em;
    background:linear-gradient(100deg,var(--accent),var(--cyan) 45%,var(--accent2)); background-size:200% auto;
    -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; animation:shimmer 6s linear infinite; }
  @keyframes shimmer { to{background-position:200% center} }
  #controls { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; }
  #meta { font-size:.8rem; color:var(--muted); display:flex; align-items:center; gap:.5rem; }
  #meta b { color:var(--fg); font-weight:600; font-family:'JetBrains Mono',monospace; font-size:.74rem; }
  .live { width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 0 0 rgba(62,240,163,.6); animation:pulse 1.8s infinite; }
  @keyframes pulse { 70%{box-shadow:0 0 0 7px rgba(62,240,163,0)} 100%{box-shadow:0 0 0 0 rgba(62,240,163,0)} }
  select, button { background:var(--panel-solid); color:var(--fg); border:1px solid var(--border); border-radius:11px;
    padding:.45rem .85rem; cursor:pointer; font:inherit; font-size:.82rem; transition:all .16s ease; }
  button:hover,select:hover { border-color:var(--accent); box-shadow:0 0 0 3px rgba(88,166,255,.14); transform:translateY(-1px); }
  button:active { transform:translateY(0); } button:disabled { opacity:.5; cursor:default; transform:none; box-shadow:none; }
  input[type=checkbox]{ accent-color:var(--accent); }
  main { padding:1.9rem; max-width:1180px; margin:0 auto; }

  /* toast */
  #toast { position:fixed; bottom:1.4rem; left:50%; transform:translateX(-50%) translateY(20px);
    z-index:50; max-width:560px; padding:.8rem 1.1rem; border-radius:13px; font-size:.84rem; opacity:0;
    background:rgba(20,26,38,.92); border:1px solid rgba(255,107,129,.4); color:var(--red);
    box-shadow:var(--shadow); backdrop-filter:blur(12px); transition:all .35s cubic-bezier(.2,.8,.2,1); pointer-events:none; }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(0); }

  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:1.05rem; margin-bottom:1.9rem; }
  .card { position:relative; overflow:hidden; border-radius:var(--radius); padding:1.2rem 1.3rem;
    background:var(--panel); border:1px solid var(--border); box-shadow:var(--shadow); backdrop-filter:blur(12px);
    transition:transform .25s ease, box-shadow .25s ease, border-color .25s; }
  .card::before { content:""; position:absolute; inset:0; border-radius:inherit; padding:1px;
    background:linear-gradient(135deg, rgba(88,166,255,.5), transparent 45%);
    -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite:xor; mask-composite:exclude; opacity:.6; pointer-events:none; }
  .card:hover { transform:translateY(-5px); box-shadow:0 18px 50px rgba(88,166,255,.18); border-color:rgba(88,166,255,.35); }
  .card .k { font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-weight:600; }
  .card .v { font-size:2.1rem; font-weight:800; margin-top:.4rem; letter-spacing:-.03em;
    background:linear-gradient(100deg,var(--accent),var(--cyan)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  .card .v.dash { background:none; -webkit-text-fill-color:var(--muted); color:var(--muted); }

  section { margin-bottom:1.9rem; border-radius:var(--radius); padding:1.2rem 1.35rem; box-shadow:var(--shadow);
    background:var(--panel); border:1px solid var(--border); backdrop-filter:blur(12px); border-top:1px solid rgba(88,166,255,.18); }
  .section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.9rem; }
  h2 { font-size:.95rem; margin:0; font-weight:700; display:flex; align-items:center; gap:.55rem; }
  h2 .dot { width:9px; height:9px; border-radius:50%; background:linear-gradient(135deg,var(--accent),var(--cyan)); box-shadow:0 0 10px var(--accent); }
  input[type=search] { background:var(--panel-solid); color:var(--fg); border:1px solid var(--border); border-radius:11px; padding:.4rem .75rem; font:inherit; min-width:185px; font-size:.82rem; }
  input[type=search]:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px rgba(88,166,255,.14); }

  table { border-collapse:collapse; width:100%; font-size:.85rem; }
  th,td { border-bottom:1px solid rgba(255,255,255,.06); padding:.6rem .75rem; text-align:left; }
  th { color:var(--muted); font-weight:600; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }
  tbody tr { opacity:0; animation:fadein .4s ease forwards; transition:background .12s; }
  tbody tr:hover { background:rgba(255,255,255,.035); }
  @keyframes fadein { to{opacity:1} }

  .bar-wrap { width:150px; }
  .bar { height:10px; border-radius:7px; background:linear-gradient(90deg,var(--accent),var(--cyan)); box-shadow:0 0 12px rgba(57,211,255,.45); transition:width .6s cubic-bezier(.2,.8,.2,1); }
  .pill { padding:2px 10px; border-radius:999px; font-size:.73rem; font-weight:600; }
  .ok { background:rgba(62,240,163,.15); color:var(--green); }
  .fail { background:rgba(255,107,129,.15); color:var(--red); }
  .state { background:rgba(88,166,255,.15); color:var(--accent); }
  .loc { font-size:.72rem; color:var(--muted); }
  .muted { color:var(--muted); }

  /* elegant empty / error states */
  .state-box { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:.6rem;
    padding:2.2rem 1rem; text-align:center; color:var(--muted); animation:fadein .4s ease; }
  .state-box .ico { width:42px; height:42px; opacity:.55; }
  .state-box .t { font-weight:600; color:var(--fg); font-size:.92rem; }
  .state-box .h { font-size:.8rem; max-width:420px; line-height:1.45; }
  .state-box.warn .ico { color:var(--red); opacity:.7; }
  .state-box.warn .h { color:#d98a98; }

  .loading { display:flex; flex-direction:column; gap:.6rem; padding:.3rem 0; }
  .sk { height:14px; border-radius:6px; background:linear-gradient(90deg, rgba(255,255,255,.06), rgba(255,255,255,.14), rgba(255,255,255,.06)); background-size:200% 100%; animation:sk 1.2s infinite; }
  @keyframes sk { to{background-position:-200% 0} }

  footer { text-align:center; color:var(--muted); font-size:.74rem; padding:1.6rem; }
  @media (max-width:640px){ main{padding:1rem} header{padding:.8rem 1rem} }
</style>
</head>
<body>
<div class="aurora"></div>
<div class="grain"></div>
<header>
  <div class="brand">
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 16a4 4 0 0 1 .8-7.9 5 5 0 0 1 9.7-1.3A3.5 3.5 0 0 1 18 16H6Z" stroke="url(#g)" stroke-width="1.7" stroke-linejoin="round"/>
      <defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop stop-color="#58a6ff"/><stop offset="1" stop-color="#7c5cff"/></linearGradient></defs>
    </svg>
    <h1>Azure-Inspect</h1>
  </div>
  <div id="controls">
    <span id="meta"><span class="live"></span> <b id="sub">…</b> · <span id="updated">–</span></span>
    <label>Cost
      <select id="days"><option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option></select>
    </label>
    <label title="Auto-refresh every 60s"><input type="checkbox" id="auto" checked> auto</label>
    <button id="refresh">↻ Refresh</button>
  </div>
</header>
<div id="toast"></div>
<main>
  <div class="cards" id="cards">
    <div class="card"><div class="k">Resource groups</div><div class="v dash" id="c-rg">–</div></div>
    <div class="card"><div class="k">Total cost</div><div class="v dash" id="c-cost">–</div></div>
    <div class="card"><div class="k">Activity (24h)</div><div class="v dash" id="c-act">–</div></div>
  </div>

  <section>
    <div class="section-head"><h2><span class="dot"></span> Resource groups</h2>
      <input type="search" id="rg-search" placeholder="filter…"></div>
    <div id="rg"><div class="loading"><div class="sk" style="width:40%"></div><div class="sk" style="width:90%"></div><div class="sk" style="width:75%"></div></div></div>
  </section>

  <section><div class="section-head"><h2><span class="dot"></span> Cost by resource group</h2></div>
    <div id="cost"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div><div class="sk" style="width:70%"></div></div></div></section>

  <section><div class="section-head"><h2><span class="dot"></span> Activity log</h2></div>
    <div id="logs"><div class="loading"><div class="sk" style="width:55%"></div><div class="sk" style="width:80%"></div><div class="sk" style="width:65%"></div></div></div></section>
</main>
<footer>Azure-Inspect · live service-principal dashboard</footer>
<script>
const ICON = {
  empty: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M3 9h18M8 14h8"/></svg>',
  warn:  '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>'
};
function esc(s){ return String(s ?? '').replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function fmtTs(iso){ try{return new Date(iso).toLocaleString()}catch{return iso} }
function rel(ts){ try{const d=(Date.now()-new Date(ts).getTime())/1000;
  if(d<60)return d.toFixed(0)+'s ago'; if(d<3600)return (d/60).toFixed(0)+'m ago';
  if(d<86400)return (d/3600).toFixed(0)+'h ago'; return (d/86400).toFixed(0)+'d ago';}catch{return ''} }
function stamp(){ document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString(); }
let toastT=null;
function toast(msg){ const t=document.getElementById('toast'); t.textContent='⚠ '+msg; t.classList.add('show');
  if(toastT)clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('show'),6000); }
function emptyState(title, hint){ return '<div class="state-box"><div class="ico">'+ICON.empty+'</div><div class="t">'+esc(title)+'</div>'+(hint?'<div class="h">'+esc(hint)+'</div>':'')+'</div>'; }
function warnState(title, hint){ return '<div class="state-box warn"><div class="ico">'+ICON.warn+'</div><div class="t">'+esc(title)+'</div>'+(hint?'<div class="h">'+esc(hint)+'</div>':'')+'</div>'; }

async function fill(id, url, render, searchId){
  const el=document.getElementById(id);
  try {
    const r=await fetch(url); const data=await r.json();
    if(data.error){
      if(data.code==='not_configured'){ toast(data.error); el.innerHTML=warnState('Not configured', data.error); return; }
      if(data.code==='auth_error'){ toast(data.error); el.innerHTML=warnState('Access denied', data.error); return; }
      if(data.code==='cost_data_unavailable'){ toast(data.error); el.innerHTML=warnState('No cost data yet', data.error); return; }
      if(data.code==='log_query_error'){ toast(data.error); el.innerHTML=warnState('Activity log needs tenant read', data.error); return; }
      el.innerHTML=warnState('Something went wrong', data.error); return;
    }
    if(searchId){ const q=(document.getElementById(searchId).value||'').toLowerCase(); if(q) data=data.filter(d=>JSON.stringify(d).toLowerCase().includes(q)); }
    render(el,data); stamp();
  } catch(e){ el.innerHTML=warnState('Network error', String(e)); }
}
function renderRg(el,data){
  if(!data.length){ el.innerHTML=emptyState('No resource groups','This subscription has no resource groups yet.'); return; }
  let rows=data.map((d,i)=>'<tr style="animation-delay:'+(i*40)+'ms"><td><b>'+esc(d.name)+'</b></td><td><span class="loc">'+esc(d.location)+
    '</span></td><td><span class="pill state">'+esc(d.provisioning_state)+'</span></td></tr>').join('');
  el.innerHTML='<table><thead><tr><th>Name</th><th>Location</th><th>State</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
function renderCost(el,data){
  if(!data.length){ el.innerHTML=emptyState('No cost data','Cost Management hasn\\'t indexed this subscription yet — this can take a few hours after a tenant move.'); return; }
  const max=Math.max(...data.map(d=>d.cost),0.0001);
  let rows=data.sort((a,b)=>b.cost-a.cost).map((d,i)=>{ const pct=Math.max(2,(d.cost/max*100)).toFixed(0);
    return '<tr style="animation-delay:'+(i*40)+'ms"><td><b>'+esc(d.resource_group||'(none)')+'</b></td>'+
      '<td class="bar-wrap"><div class="bar" style="width:'+pct+'%"></div></td>'+
      '<td>'+Number(d.cost).toFixed(2)+' '+esc(d.currency)+'</td></tr>'; }).join('');
  el.innerHTML='<table><thead><tr><th>Resource group</th><th></th><th>Cost</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
function renderLogs(el,data){
  if(!data.length){ el.innerHTML=emptyState('No recent activity','No activity-log events in the last 24 hours.'); return; }
  let rows=data.slice(0,60).map((d,i)=>{ const st=(d.status||'').toLowerCase().includes('fail')?'fail':'ok';
    return '<tr style="animation-delay:'+(i*30)+'ms"><td title="'+esc(fmtTs(d.event_timestamp))+'">'+esc(rel(d.event_timestamp))+'</td>'+
      '<td>'+esc(d.operation)+'</td><td class="loc">'+esc(d.resource_group||'–')+'</td><td class="loc">'+esc(d.caller||'–')+'</td>'+
      '<td><span class="pill '+st+'">'+esc(d.status)+'</span></td></tr>'; }).join('');
  el.innerHTML='<table><thead><tr><th>When</th><th>Operation</th><th>RG</th><th>Caller</th><th>Status</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
async function loadAll(){
  const btn=document.getElementById('refresh'); btn.disabled=true; btn.textContent='↻ Refreshing…';
  try {
    const s=await (await fetch('/api/summary')).json();
    if(s.error){
      if(s.code==='not_configured') toast(s.error);
      document.getElementById('sub').textContent='?';
      document.getElementById('c-rg').textContent='–'; document.getElementById('c-rg').className='v dash';
      document.getElementById('c-cost').textContent='–'; document.getElementById('c-cost').className='v dash';
      document.getElementById('c-act').textContent='–'; document.getElementById('c-act').className='v dash';
    } else {
      document.getElementById('sub').textContent=s.subscription_id||'?';
      const set=(id,val)=>{ const e=document.getElementById(id); e.textContent=val; e.className='v'; };
      set('c-rg', s.resource_group_count ?? '–');
      set('c-cost', s.total_cost!=null ? s.total_cost.toFixed(2)+' '+(s.currency||'') : '–');
      set('c-act', s.activity_count ?? '–');
    }
    const days=document.getElementById('days').value;
    fill('rg','/api/resources',renderRg,'rg-search');
    fill('cost','/api/costs?days='+days,renderCost);
    fill('logs','/api/logs',renderLogs);
  } finally { btn.disabled=false; btn.textContent='↻ Refresh'; }
}
let timer=null;
function setupAuto(){ if(timer)clearInterval(timer); if(document.getElementById('auto').checked) timer=setInterval(loadAll,60000); }
document.getElementById('auto').addEventListener('change',setupAuto);
document.getElementById('refresh').addEventListener('click',loadAll);
document.getElementById('days').addEventListener('change',loadAll);
document.getElementById('rg-search').addEventListener('input',()=>fill('rg','/api/resources',renderRg,'rg-search'));
loadAll(); setupAuto();
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
            "error": "The activity-log API returned an unsupported resource type. "
                     "This usually means the service principal lacks read "
                     "permission at the tenant (directory) scope — grant it the "
                     "Reader role at tenant scope in Entra ID, then refresh. "
                     f"({msg[:120]})",
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
