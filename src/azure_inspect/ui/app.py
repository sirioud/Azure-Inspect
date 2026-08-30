"""Flask web application for Azure-Inspect (the dashboard)."""
from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

from dotenv import load_dotenv

from ..config import AzureConfig, load_config
from ..costs import cost_by_resource_group
from ..logs import get_activity_log
from ..resources import list_resource_groups
from ..cache import DataCache

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Azure-Inspect · Security Posture</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root {
    --bg:#0b0f14; --panel:#10171f; --panel2:#0d141b; --panel-solid:#0e151c;
    --border:rgba(255,255,255,.08); --border2:rgba(255,255,255,.04);
    --fg:#e7eef5; --muted:#8190a3; --faint:#5b6678;
    --accent:#1fd1a5; --accent2:#00e0a4; --cyan:#27e0c8;
    --crit:#ff3b5c; --high:#ff6a3d; --med:#ffc24b; --low:#1fd1a5; --green:#1fd1a5; --red:#ff3b5c; --amber:#ffc24b;
    --mono:'JetBrains Mono',ui-monospace,monospace;
    --sidebar-w:220px; --shadow:0 1px 0 rgba(255,255,255,.03) inset, 0 8px 30px rgba(0,0,0,.55);
  }
  * { box-sizing:border-box; } html,body { margin:0; }
  body { font-family:'Inter',system-ui,sans-serif; color:var(--fg); min-height:100vh;
    background:
      radial-gradient(55% 45% at 12% 0%, rgba(31,209,165,.10), transparent 55%),
      radial-gradient(50% 40% at 95% 8%, rgba(39,224,200,.08), transparent 55%),
      var(--bg);
    background-attachment:fixed; overflow-x:hidden; -webkit-font-smoothing:antialiased; }
  body::before { content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; opacity:.45;
    background-image:linear-gradient(rgba(31,209,165,.018) 1px, transparent 1px),
      linear-gradient(90deg, rgba(31,209,165,.018) 1px, transparent 1px);
    background-size:40px 40px; mask-image:radial-gradient(circle at 40% 0%, #000 22%, transparent 78%); }

  .sidebar { position:fixed; top:0; left:0; bottom:0; width:var(--sidebar-w); z-index:30;
    background:linear-gradient(180deg, #0c141b, #0a0e13); border-right:1px solid var(--border);
    display:flex; flex-direction:column; padding:.95rem .7rem; gap:.35rem; transition:width .2s ease; }
  .sidebar.collapsed { width:62px; }
  .brand { display:flex; align-items:center; gap:.6rem; padding:.2rem .4rem .85rem; }
  .brand svg { width:27px; height:27px; flex:0 0 auto; }
  .brand h1 { font-size:1rem; font-weight:800; letter-spacing:-.02em; white-space:nowrap;
    background:linear-gradient(100deg,var(--accent),var(--cyan) 60%,var(--accent2)); background-size:200% auto;
    -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; margin:0; }
  .sidebar.collapsed .brand h1, .sidebar.collapsed .nav-label { display:none; }
  .nav-item { display:flex; align-items:center; gap:.7rem; padding:.6rem .7rem; border-radius:9px;
    color:var(--muted); cursor:pointer; font-size:.86rem; font-weight:500; transition:all .14s; white-space:nowrap; }
  .nav-item:hover { background:rgba(255,255,255,.05); color:var(--fg); }
  .nav-item.active { background:linear-gradient(90deg, rgba(31,209,165,.16), rgba(31,209,165,.03)); color:var(--fg);
    box-shadow:inset 2px 0 0 var(--accent); }
  .nav-item svg { width:19px; height:19px; flex:0 0 auto; }
  .nav-label { overflow:hidden; }
  .sb-toggle { margin-top:auto; }
  .sb-foot { font-size:.66rem; color:var(--faint); padding:.4rem .5rem; font-family:var(--mono); }

  .app { margin-left:var(--sidebar-w); transition:margin-left .2s ease; }
  .app.full { margin-left:62px; }
  header.top { position:sticky; top:0; z-index:20; display:flex; align-items:center; justify-content:space-between;
    padding:.8rem 1.5rem; border-bottom:1px solid var(--border); background:rgba(11,15,20,.82); backdrop-filter:blur(14px); flex-wrap:wrap; gap:.6rem; }
  .meta { font-size:.78rem; color:var(--muted); display:flex; align-items:center; gap:.5rem; font-family:var(--mono); }
  .meta b { color:var(--fg); }
  .live { width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 0 0 rgba(31,209,165,.55); animation:pulse 1.8s infinite; }
  @keyframes pulse { 70%{box-shadow:0 0 0 6px rgba(31,209,165,0)} 100%{box-shadow:0 0 0 0 rgba(31,209,165,0)} }
  #controls { display:flex; gap:.5rem; align-items:center; flex-wrap:wrap; }
  select, button { background:var(--panel2); color:var(--fg); border:1px solid var(--border); border-radius:9px;
    padding:.42rem .8rem; cursor:pointer; font:inherit; font-size:.8rem; transition:all .15s; }
  button:hover,select:hover { border-color:var(--accent); box-shadow:0 0 0 3px rgba(31,209,165,.13); }
  button:active { transform:translateY(0); } button:disabled { opacity:.5; cursor:default; box-shadow:none; }
  input[type=checkbox]{ accent-color:var(--accent); }
  .logout { color:var(--muted); text-decoration:none; font-size:.78rem; padding:.4rem .7rem; border:1px solid var(--border); border-radius:9px; }
  .logout:hover { color:var(--fg); border-color:var(--accent); }
  main { padding:1.4rem 1.5rem 2rem; max-width:1340px; }

  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr)); gap:.9rem; margin-bottom:1.4rem; }
  .kpi { position:relative; overflow:hidden; border-radius:13px; padding:1rem 1.1rem;
    background:linear-gradient(180deg,var(--panel),var(--panel2)); border:1px solid var(--border); box-shadow:var(--shadow); }
  .kpi::before { content:""; position:absolute; left:0; top:0; bottom:0; width:3px; border-radius:13px 0 0 13px; background:var(--accent); opacity:.85; }
  .kpi.k-res::before { background:var(--accent); } .kpi.k-rg::before { background:var(--cyan); }
  .kpi.k-score::before { background:var(--green); } .kpi.k-find::before { background:var(--high); }
  .kpi.k-cost::before { background:var(--amber); }
  .kpi .k { font-size:.66rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-weight:600; }
  .kpi .v { font-size:1.9rem; font-weight:800; margin-top:.3rem; font-family:var(--mono); color:var(--fg); line-height:1; }
  .kpi .sub { font-size:.66rem; color:var(--muted); margin-top:.25rem; }

  .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:1.1rem; }
  .panel { grid-column:span 6; border-radius:14px; padding:1.1rem 1.25rem; background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--border); box-shadow:var(--shadow); min-height:240px; display:flex; flex-direction:column; }
  .panel.w12 { grid-column:span 12; } .panel.w4 { grid-column:span 4; } .panel.w8 { grid-column:span 8; }
  .panel-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:.7rem; gap:.8rem; }
  .panel-head h2 { font-size:.9rem; margin:0; font-weight:700; display:flex; align-items:center; gap:.5rem; }
  .panel-head h2 .dot { width:7px; height:7px; border-radius:50%; background:var(--accent); box-shadow:0 0 8px var(--accent); }
  .chart { width:100%; height:255px; }
  .chart.sm { height:200px; }
  table { border-collapse:collapse; width:100%; font-size:.82rem; }
  th,td { border-bottom:1px solid var(--border2); padding:.5rem .6rem; text-align:left; }
  th { color:var(--faint); font-weight:600; font-size:.66rem; text-transform:uppercase; letter-spacing:.07em; }
  tbody tr:hover { background:rgba(255,255,255,.04); }
  td b, .mono { font-family:var(--mono); }
  .pill { padding:2px 9px; border-radius:999px; font-size:.7rem; font-weight:600; font-family:var(--mono); }
  .ok { background:rgba(31,209,165,.14); color:var(--green); } .fail { background:rgba(255,59,92,.14); color:var(--red); }
  .state { background:rgba(39,224,200,.14); color:var(--cyan); }
  .warn { background:rgba(255,194,75,.16); color:var(--amber); }
  .sev-Critical { background:rgba(255,59,92,.16); color:var(--crit); }
  .sev-High { background:rgba(255,106,61,.16); color:var(--high); }
  .sev-Medium { background:rgba(255,194,75,.16); color:var(--med); }
  .sev-Low { background:rgba(31,209,165,.14); color:var(--low); }
  .muted { color:var(--muted); } .loc { font-size:.72rem; color:var(--muted); font-family:var(--mono); }
  .state-box { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:.6rem; padding:1.8rem 1rem; text-align:center; color:var(--muted); }
  .state-box .ico { width:38px; height:38px; opacity:.5; }
  .state-box .t { font-weight:600; color:var(--fg); font-size:.9rem; }
  .state-box .h { font-size:.78rem; max-width:420px; line-height:1.5; }
  .loading { display:flex; flex-direction:column; gap:.5rem; padding:.3rem 0; }
  .sk { height:12px; border-radius:6px; background:linear-gradient(90deg, rgba(255,255,255,.05), rgba(255,255,255,.12), rgba(255,255,255,.05)); background-size:200% 100%; animation:sk 1.2s infinite; }
  @keyframes sk { to{background-position:-200% 0} }
  .feed { display:flex; flex-direction:column; gap:.55rem; max-height:340px; overflow:auto; }
  .feed-item { display:flex; gap:.7rem; align-items:flex-start; padding:.55rem .65rem; border-radius:9px; background:rgba(255,255,255,.03); border:1px solid var(--border2); }
  .feed-item .ic { width:8px; height:8px; border-radius:50%; margin-top:.4rem; flex:0 0 auto; }
  .feed-item .body { font-size:.8rem; line-height:1.45; }
  .feed-item .meta2 { font-size:.68rem; color:var(--faint); font-family:var(--mono); margin-top:.15rem; }
  #toast { position:fixed; bottom:1.4rem; left:50%; transform:translateX(-50%) translateY(20px); z-index:60; max-width:560px;
    padding:.75rem 1.05rem; border-radius:11px; font-size:.82rem; opacity:0; background:var(--panel); border:1px solid rgba(255,59,92,.4);
    color:var(--red); box-shadow:var(--shadow); transition:all .3s cubic-bezier(.2,.8,.2,1); pointer-events:none; }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
  .view { display:none; } .view.active { display:block; }
  /* ---- A+D: glow command-center + motion ---- */
  :root { --glow:0 0 24px rgba(31,209,165,.30), 0 0 2px rgba(31,209,165,.6); }
  body::after { content:""; position:fixed; inset:0; z-index:-2; pointer-events:none; opacity:.5;
    background:linear-gradient(120deg, rgba(31,209,165,.05), rgba(39,224,200,.04) 40%, rgba(255,194,75,.03) 70%, rgba(31,209,165,.05));
    background-size:300% 300%; animation:hue 18s ease infinite; }
  @keyframes hue { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
  .panel { box-shadow:var(--shadow), 0 0 0 1px rgba(31,209,165,.06), 0 0 22px rgba(31,209,165,.05); }
  .panel:hover { box-shadow:var(--shadow), 0 0 0 1px rgba(31,209,165,.16), 0 0 34px rgba(31,209,165,.12); }
  .kpi { box-shadow:var(--shadow), 0 0 20px rgba(31,209,165,.06); }
  .kpi:hover { box-shadow:var(--shadow), 0 0 28px rgba(31,209,165,.16); }
  .kpi .v { text-shadow:0 0 18px rgba(31,209,165,.25); transition:none; }
  .nav-item.active { box-shadow:inset 2px 0 0 var(--accent), 0 0 16px rgba(31,209,165,.10); }
  .brand h1 { animation:shimmer 6s linear infinite; background-size:200% auto; }
  @keyframes shimmer { to { background-position:200% center; } }
  /* hero gauge */
  .hero { grid-column:span 12; display:flex; gap:1.2rem; align-items:center; flex-wrap:wrap;
    border-radius:14px; padding:1.2rem 1.4rem; background:linear-gradient(120deg, rgba(31,209,165,.07), rgba(39,224,200,.03)); border:1px solid var(--border); box-shadow:var(--shadow), 0 0 30px rgba(31,209,165,.08); }
  .hero .gauge { width:230px; height:150px; flex:0 0 auto; }
  .hero .htext { flex:1; min-width:220px; }
  .hero .hbig { font-family:var(--mono); font-size:3.1rem; font-weight:800; line-height:1;
    background:linear-gradient(100deg,var(--accent),var(--cyan)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
    text-shadow:0 0 30px rgba(31,209,165,.25); }
  .hero .hsub { color:var(--muted); font-size:.85rem; margin-top:.4rem; }
  .hero .htags { display:flex; gap:.5rem; margin-top:.7rem; flex-wrap:wrap; }
  .hero .htag { font-size:.7rem; padding:.25rem .6rem; border-radius:999px; background:rgba(255,255,255,.05); border:1px solid var(--border); color:var(--muted); font-family:var(--mono); }
  @media (max-width:900px){ .panel{ grid-column:span 12 !important; } }
  @media (max-width:640px){ main{padding:.9rem} header.top{padding:.7rem 1rem} }
</style>
</head>
<body>
<div class="sidebar" id="sidebar">
  <div class="brand">
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2 4 5v6c0 5 3.5 8 8 11 4.5-3 8-6 8-11V5z" stroke="url(#g)" stroke-width="1.7" stroke-linejoin="round"/>
      <path d="m9 12 2 2 4-4" stroke="url(#g)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
      <defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24"><stop stop-color="#1fd1a5"/><stop offset="1" stop-color="#27e0c8"/></linearGradient></defs>
    </svg>
    <h1>Azure-Inspect</h1>
  </div>
  <div class="nav-item active" data-view="posture">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 2 4 5v6c0 5 3.5 8 8 11 4.5-3 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/></svg>
    <span class="nav-label">Posture</span>
  </div>
  <div class="nav-item" data-view="inventory">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    <span class="nav-label">Inventory</span>
  </div>
  <div class="nav-item" data-view="exposure">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="9"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></svg>
    <span class="nav-label">Exposure</span>
  </div>
  <div class="nav-item" data-view="compliance">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 11l3 3 8-8"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
    <span class="nav-label">Compliance</span>
  </div>
  <div class="nav-item" data-view="advisor">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1h6c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2Z"/></svg>
    <span class="nav-label">Advisor</span>
  </div>
  <div class="nav-item" data-view="alerts">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/></svg>
    <span class="nav-label">Alerts</span>
  </div>
  <button class="nav-item sb-toggle" id="sb-toggle">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M15 6l-6 6 6 6"/></svg>
    <span class="nav-label">Collapse</span>
  </button>
  <div class="sb-foot">enten · live</div>
</div>

<div class="app" id="app">
  <header class="top">
    <div class="meta"><span class="live"></span> <b id="sub">…</b> · <span id="updated">–</span> · <span class="muted" id="synced">sync: –</span></div>
    <div id="controls">
      <label>Window
        <select id="days"><option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option></select>
      </label>
      <label title="Auto-refresh every 60s (reads local cache)"><input type="checkbox" id="auto" checked> auto</label>
      <button id="sync">⇅ Sync now</button>
      <button id="refresh">↻ Refresh</button>
      <button id="export">⬇ Export</button>
      <a class="logout" href="/logout">Logout</a>
    </div>
  </header>
  <main>
    <div class="kpis" id="kpis">
      <div class="kpi k-res"><div class="k">Resources</div><div class="v" id="c-res">–</div></div>
      <div class="kpi k-rg"><div class="k">Resource groups</div><div class="v" id="c-rg">–</div></div>
      <div class="kpi k-score"><div class="k">Posture</div><div class="v" id="c-score">–</div><div class="sub" id="c-score-sub">compliant</div></div>
      <div class="kpi k-find"><div class="k">Open findings</div><div class="v" id="c-find">–</div><div class="sub" id="c-find-sub">critical + high</div></div>
      <div class="kpi k-cost"><div class="k">Spend (30d)</div><div class="v" id="c-cost">–</div></div>
    </div>

    <!-- POSTURE (security landing) -->
    <div class="view active" id="view-posture">
      <div class="hero">
        <div class="gauge" id="postureGauge"></div>
        <div class="htext">
          <div class="hbig" id="hero-pct">–</div>
          <div class="hsub" id="hero-sub">Security posture</div>
          <div class="htags" id="hero-tags"></div>
        </div>
      </div>
      <div class="grid">
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Posture</h2></div><div id="govChart" class="chart sm"></div></div>
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Findings by severity</h2></div><div id="sevChart" class="chart sm"></div></div>
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Resource exposure (by type)</h2></div><div id="typeChart" class="chart"></div></div>
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Risk feed</h2><span class="muted" style="font-size:.7rem">activity · findings</span></div><div id="feed" class="feed"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div><div class="sk" style="width:70%"></div></div></div></div>
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> Resource groups</h2><input type="search" id="rg-search" placeholder="filter…"></div><div id="rg"><div class="loading"><div class="sk" style="width:40%"></div><div class="sk" style="width:90%"></div><div class="sk" style="width:75%"></div></div></div></div>
        <div class="panel w4"><div class="panel-head"><h2><span class="dot"></span> Resources (trend)</h2></div><div id="resTrend" class="chart sm"></div></div>
        <div class="panel w4"><div class="panel-head"><h2><span class="dot"></span> Posture % (trend)</h2></div><div id="postureTrend" class="chart sm"></div></div>
        <div class="panel w4"><div class="panel-head"><h2><span class="dot"></span> Spend (trend)</h2></div><div id="costTrend" class="chart sm"></div></div>
      </div>
    </div>

    <!-- INVENTORY -->
    <div class="view" id="view-inventory">
      <div class="grid">
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Resources by type</h2></div><div id="typeChart2" class="chart"></div></div>
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Resources by location</h2></div><div id="locChart" class="chart"></div></div>
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> Tag coverage</h2></div><div id="tagChart" class="chart sm"></div></div>
      </div>
    </div>

    <!-- EXPOSURE -->
    <div class="view" id="view-exposure">
      <div class="grid">
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Resource exposure (by type)</h2></div><div id="expChart" class="chart"></div></div>
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Resources by location</h2></div><div id="locChart2" class="chart"></div></div>
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> All findings (risk-ranked)</h2></div><div id="findings"><div class="loading"><div class="sk" style="width:55%"></div><div class="sk" style="width:80%"></div><div class="sk" style="width:65%"></div></div></div></div>
      </div>
    </div>

    <!-- COMPLIANCE -->
    <div class="view" id="view-compliance">
      <div class="grid">
        <div class="panel"><div class="panel-head"><h2><span class="dot"></span> Posture</h2></div><span class="pill state" id="posture-badge">–</span></div>
        <div class="panel w8"><div class="panel-head"><h2><span class="dot"></span> Governance gaps</h2></div><div id="compliance"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div></div></div></div>
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> Access (RBAC)</h2></div><div id="rbac"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div></div></div></div>
      </div>
    </div>

    <!-- ADVISOR -->
    <div class="view" id="view-advisor">
      <div class="grid">
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> Azure Advisor recommendations</h2></div><div id="advisor"><div class="loading"><div class="sk" style="width:55%"></div><div class="sk" style="width:80%"></div><div class="sk" style="width:65%"></div></div></div></div>
      </div>
    </div>

    <!-- ALERTS -->
    <div class="view" id="view-alerts">
      <div class="grid">
        <div class="panel w12"><div class="panel-head"><h2><span class="dot"></span> Alert rules</h2><span class="muted" id="alert-chan" style="font-size:.7rem"></span></div><div id="alerts"><div class="loading"><div class="sk" style="width:55%"></div><div class="sk" style="width:80%"></div><div class="sk" style="width:65%"></div></div></div></div>
      </div>
    </div>
  </main>
</div>
<div id="toast"></div>
<script>
const ICON = {
  empty:'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M3 9h18M8 14h8"/></svg>',
  warn:'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>'
};
function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function fmtTs(iso){ try{return new Date(iso).toLocaleString()}catch{return iso} }
function rel(ts){ try{const d=(Date.now()-new Date(ts).getTime())/1000;
  if(d<60)return d.toFixed(0)+'s ago'; if(d<3600)return (d/60).toFixed(0)+'m ago';
  if(d<86400)return (d/3600).toFixed(0)+'h ago'; return (d/86400).toFixed(0)+'d ago';}catch{return ''} }
function stamp(){ document.getElementById('updated').textContent='updated '+new Date().toLocaleTimeString(); }
let toastT=null;
function toast(msg){ const t=document.getElementById('toast'); t.textContent='⚠ '+msg; t.classList.add('show');
  if(toastT)clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('show'),6000); }
const charts=[];
function makeChart(id){
  if(typeof echarts==='undefined') return null;
  const el=document.getElementById(id); if(!el) return null;
  const c=echarts.init(el, 'dark', {renderer:'canvas'});
  charts.push(c); return c;
}
window.addEventListener('resize', ()=>charts.forEach(c=>c.resize()));
const baseGrid={left:8,right:18,top:24,bottom:8,containLabel:true};
const axisStyle={axisLine:{lineStyle:{color:'rgba(255,255,255,.15)'}},axisLabel:{color:'#8190a3',fontSize:11},splitLine:{lineStyle:{color:'rgba(255,255,255,.05)'}}};

document.querySelectorAll('.nav-item[data-view]').forEach(n=>{
  n.addEventListener('click', ()=>{
    document.querySelectorAll('.nav-item[data-view]').forEach(x=>x.classList.remove('active'));
    n.classList.add('active');
    const v=n.dataset.view;
    document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
    document.getElementById('view-'+v).classList.add('active');
    setTimeout(()=>charts.forEach(c=>c.resize()),60);
  });
});
document.getElementById('sb-toggle').addEventListener('click', ()=>{
  const sb=document.getElementById('sidebar'), app=document.getElementById('app');
  sb.classList.toggle('collapsed'); app.classList.toggle('full');
  setTimeout(()=>charts.forEach(c=>c.resize()),220);
});

async function fill(elId, url, render, searchId){
  const el=document.getElementById(elId);
  let data=await (await fetch(url)).json();
  if(searchId){ const q=document.getElementById(searchId).value.toLowerCase();
    if(q) data=data.filter(d=>JSON.stringify(d).toLowerCase().includes(q)); }
  render(el, data);
}

function animateValue(id, to, opts){
  opts=opts||{};
  const el=document.getElementById(id); if(!el) return;
  const dec=opts.dec||0, suffix=opts.suffix||'', from=parseFloat(el.dataset.v||'0')||0;
  const t0=performance.now(), dur=opts.dur||900;
  function step(t){ const k=Math.min(1,(t-t0)/dur); const e=1-Math.pow(1-k,3);
    const v=from+(to-from)*e; el.textContent=(dec?v.toFixed(dec):Math.round(v))+suffix;
    if(k<1) requestAnimationFrame(step); else { el.dataset.v=to; } }
  el.dataset.v=el.dataset.v||'0'; requestAnimationFrame(step);
}
function renderGauge(elId, pct, gaps){
  const c=makeChart(elId); if(!c) return;
  c.setOption({
    series:[{ type:'gauge', startAngle:210, endAngle:-30, radius:'100%', center:['50%','62%'],
      progress:{show:true, width:14, roundCap:true, itemStyle:{color: pct>=80? new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'#27e0c8'},{offset:1,color:'#1fd1a5'}]) : (pct>=50? '#ffc24b':'#ff3b5c')}},
      axisLine:{lineStyle:{width:14, color:[[1,'rgba(255,255,255,.08)']]}},
      pointer:{show:false}, axisTick:{show:false}, splitLine:{show:false}, axisLabel:{show:false},
      anchor:{show:false},
      detail:{valueAnimation:true, fontSize:0, offsetCenter:[0,0]},
      data:[{value:pct}],
      title:{show:false}
    }]
  });
  // big colored arc glow via a second transparent series
  c.setOption({series:[{type:'gauge', startAngle:210, endAngle:-30, radius:'100%', center:['50%','62%'],
    progress:{show:true, width:14, roundCap:true, itemStyle:{color:'transparent', shadowBlur:18, shadowColor: pct>=80?'#1fd1a5':(pct>=50?'#ffc24b':'#ff3b5c')}},
    axisLine:{lineStyle:{width:14, color:[[1,'rgba(255,255,255,0)']]}}, pointer:{show:false}, axisTick:{show:false}, splitLine:{show:false}, axisLabel:{show:false}, anchor:{show:false}, detail:{show:false}, data:[{value:pct}], title:{show:false}}]});
}
function renderKpis(s, findings){
  document.getElementById('sub').textContent=s.subscription_id||'?';
  animateValue('c-res', s.total_resources!=null?s.total_resources:0);
  animateValue('c-rg', s.resource_group_count!=null?s.resource_group_count:0);
  animateValue('c-cost', s.total_cost!=null?s.total_cost:0, {dec:2, suffix:' '+(s.currency||'')});
  const gaps=(s.governance_gap_count||0);
  const total=(s.resource_group_count||0)||1;
  const pct=Math.max(0,Math.round((1-gaps/total)*100));
  animateValue('c-score', pct, {suffix:'%'});
  document.getElementById('c-score-sub').textContent=gaps+' gap'+(gaps!==1?'s':'');
  const crit=(findings&&findings.counts)?(findings.counts.Critical||0)+(findings.counts.High||0):gaps;
  animateValue('c-find', crit);
  document.getElementById('c-find-sub').textContent='critical + high';
  // hero
  renderGauge('postureGauge', pct, gaps);
  const hb=document.getElementById('hero-pct'); if(hb){ hb.textContent=pct+'%'; hb.dataset.v=pct; }
  document.getElementById('hero-sub').textContent = gaps? (gaps+' governance gap'+(gaps!==1?'s':'')+' open') : 'All resource groups compliant';
  const tags=document.getElementById('hero-tags');
  if(tags){ tags.innerHTML = (findings&&findings.counts)?
    ['Critical','High','Medium','Low'].map(k=>`<span class="htag">${k}: ${findings.counts[k]||0}</span>`).join('') : ''; }
}
function renderGov(el, comp){
  const gaps=(comp.governance_gap_count!=null?comp.governance_gap_count:(comp.governance_gaps||[]).length);
  const total=(comp.resource_group_count||11); const clean=Math.max(0,total-gaps);
  const c=makeChart('govChart'); if(!c){ return; }
  c.setOption({tooltip:{trigger:'item'}, series:[{type:'pie',radius:['55%','80%'],center:['50%','45%'],
    label:{color:'#e7eef5',formatter:'{b}: {c}'},
    data:[{name:'Compliant',value:clean,itemStyle:{color:'#1fd1a5',shadowBlur:14,shadowColor:'rgba(31,209,165,.5)'}},{name:'Gaps',value:gaps,itemStyle:{color:'#ff3b5c',shadowBlur:14,shadowColor:'rgba(255,59,92,.5)'}}]}]});
}
function renderSev(el, f){
  const c=makeChart('sevChart'); if(!c){ return; }
  const co=(f&&f.counts)||{Critical:0,High:0,Medium:0,Low:0};
  const glow={'Critical':'rgba(255,59,92,.5)','High':'rgba(255,106,61,.5)','Medium':'rgba(255,194,75,.5)','Low':'rgba(31,209,165,.5)'};
  c.setOption({grid:{left:8,right:8,top:14,bottom:8,containLabel:false}, tooltip:{trigger:'item'},
    series:[{type:'pie',radius:['45%','75%'],center:['50%','45%'],
      label:{color:'#e7eef5',formatter:'{b}: {c}'},
      data:[
        {name:'Critical',value:co.Critical||0,itemStyle:{color:'#ff3b5c',shadowBlur:12,shadowColor:glow.Critical}},
        {name:'High',value:co.High||0,itemStyle:{color:'#ff6a3d',shadowBlur:12,shadowColor:glow.High}},
        {name:'Medium',value:co.Medium||0,itemStyle:{color:'#ffc24b',shadowBlur:12,shadowColor:glow.Medium}},
        {name:'Low',value:co.Low||0,itemStyle:{color:'#1fd1a5',shadowBlur:12,shadowColor:glow.Low}}
      ]}]});
}
function renderType(el, inv){
  const c=makeChart(el.id); if(!c||!inv.by_type||!inv.by_type.length){ el.innerHTML='<div class="state-box"><div class="t">No resources</div></div>'; return; }
  const pal=['#1fd1a5','#27e0c8','#00e0a4','#ffc24b','#ff6a3d','#ff3b5c','#8190a3'];
  c.setOption({tooltip:{trigger:'item'}, legend:{type:'scroll',orient:'vertical',right:6,top:10,textStyle:{color:'#8190a3',fontSize:10}},
    series:[{type:'pie',radius:['40%','70%'],center:['38%','50%'],
      label:{show:false}, data:inv.by_type.map((t,i)=>({name:t.type.split('/').pop(),value:t.count,itemStyle:{color:pal[i%pal.length],shadowBlur:10,shadowColor:pal[i%pal.length]+'88'}}))}]});
}
function renderLoc(el, inv){
  const c=makeChart(el.id); if(!c||!inv.by_location||!inv.by_location.length){ return; }
  c.setOption({grid:baseGrid, tooltip:{trigger:'axis'}, xAxis:{type:'category',data:inv.by_location.map(l=>l.location||'unknown'),...axisStyle},
    yAxis:{type:'value',...axisStyle}, series:[{type:'bar',data:inv.by_location.map(l=>l.count),itemStyle:{color:'#27e0c8',borderRadius:[4,4,0,0],shadowBlur:10,shadowColor:'rgba(39,224,200,.5)'}}]});
}
function renderTag(el, inv){
  const c=makeChart('tagChart'); if(!c){ return; }
  const tagged=inv.tagged_rgs||0, untagged=inv.untagged_rgs||0;
  c.setOption({grid:{left:8,right:18,top:10,bottom:8,containLabel:true}, tooltip:{trigger:'item'},
    xAxis:{type:'value',...axisStyle}, yAxis:{type:'category',data:['untagged (no env)','tagged (env)'],...axisStyle},
    series:[{type:'bar',data:[{value:untagged,itemStyle:{color:'#ff3b5c'}},{value:tagged,itemStyle:{color:'#1fd1a5'}}],itemStyle:{borderRadius:[0,4,4,0]}}]});
}
function renderFindings(el, f){
  const list=(f&&f.findings)||[];
  if(!list.length){ el.innerHTML='<div class="state-box"><div class="t">No findings 🎉</div></div>'; return; }
  let rows=list.map(x=>`<tr><td><span class="pill sev-${esc(x.severity)}">${esc(x.severity)}</span></td><td><span class="pill state">${esc(x.source)}</span></td><td><b>${esc(x.title)}</b></td><td class="muted">${esc(x.detail)}</td></tr>`).join('');
  el.innerHTML=`<table><thead><tr><th>SEV</th><th>SOURCE</th><th>TITLE</th><th>DETAIL</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderRg(el, list){
  if(!list.length){ el.innerHTML='<div class="state-box"><div class="t">No resource groups</div></div>'; return; }
  let rows=list.map(r=>`<tr><td><b>${esc(r.name)}</b></td><td class="loc">${esc(r.location)}</td><td><span class="pill ${r.provisioning_state&&r.provisioning_state.toLowerCase()=='succeeded'?'ok':(r.provisioning_state&&r.provisioning_state.toLowerCase()=='failed'?'fail':'state')}">${esc(r.provisioning_state||'?')}</span></td></tr>`).join('');
  el.innerHTML=`<table><thead><tr><th>NAME</th><th>LOCATION</th><th>STATE</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderCompliance(el, comp){
  const gaps=comp.governance_gaps||[];
  const badge=document.getElementById('posture-badge');
  if(gaps.length){ badge.textContent=gaps.length+' gap'+(gaps.length>1?'s':''); badge.className='pill fail'; }
  else { badge.textContent='clean'; badge.className='pill ok'; }
  if(!gaps.length){ el.innerHTML='<div class="state-box"><div class="t">No governance gaps 🎉</div></div>'; return; }
  let rows=gaps.map(g=>`<tr><td><b>${esc(g.resource)}</b></td><td>${esc(g.type)}</td><td><span class="pill fail">${esc(g.issue)}</span></td></tr>`).join('');
  el.innerHTML=`<table><thead><tr><th>RESOURCE</th><th>TYPE</th><th>ISSUE</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderRbac(el, comp){
  const rows=comp.role_assignments||[];
  if(!rows.length){ el.innerHTML='<div class="state-box"><div class="t">No assignments</div></div>'; return; }
  let html=rows.map(r=>`<tr><td><span class="pill state">${esc(r.role)}</span></td><td class="mono">${esc((r.principal_id||'').slice(0,13))}…</td><td class="loc">${esc(r.scope)}</td></tr>`).join('');
  el.innerHTML=`<table><thead><tr><th>ROLE</th><th>PRINCIPAL</th><th>SCOPE</th></tr></thead><tbody>${html}</tbody></table>`;
}
function renderAdvisor(el, list){
  if(!list||!list.length){ el.innerHTML='<div class="state-box"><div class="t">No recommendations</div></div>'; return; }
  let rows=list.map(a=>`<tr><td><span class="pill sev-${esc(a.impact)}">${esc(a.impact)}</span></td><td><b>${esc(a.category)}</b></td><td>${esc(a.short_description||a.risk)}</td></tr>`).join('');
  el.innerHTML=`<table><thead><tr><th>IMPACT</th><th>CATEGORY</th><th>RECOMMENDATION</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderFeed(el, logs, findings){
  const items=[];
  (logs||[]).slice(0,8).forEach(l=>items.push({color:'#27e0c8',title:esc(l.operation||'activity'),sub:(l.resource_group||'')+' · '+(l.status||'')+' · '+rel(l.event_timestamp)}));
  (findings&&findings.findings||[]).forEach(f=>{
    const col={'Critical':'#ff3b5c','High':'#ff6a3d','Medium':'#ffc24b','Low':'#1fd1a5'}[f.severity]||'#27e0c8';
    items.push({color:col,title:esc(f.severity)+' · '+esc(f.title),sub:esc(f.source)+' · '+esc(f.detail)});
  });
  if(!items.length){ el.innerHTML='<div class="state-box"><div class="t">No recent activity or findings</div></div>'; return; }
  el.innerHTML=items.map(it=>`<div class="feed-item"><div class="ic" style="background:${it.color}"></div><div class="body">${it.title}<div class="meta2">${it.sub}</div></div></div>`).join('');
}
function renderAlerts(el, a){
  const rules=(a&&a.rules)||[];
  const chan=document.getElementById('alert-chan');
  if(chan) chan.textContent=(a&&a.telegram_configured)?'Telegram: configured':'Telegram: not configured';
  if(!rules.length){ el.innerHTML='<div class="state-box"><div class="t">No alert rules</div></div>'; return; }
  const st={'ok':'ok','firing':'fail'};
  let rows=rules.map(r=>{
    const lf=r.last_fired?(function(){ try{return rel(new Date(parseFloat(r.last_fired)*1000).toISOString());}catch{return 'unknown';} })():'never';
    return `<tr><td><span class="pill ${st[r.state]||'state'}">${esc(r.state)}</span></td><td><b>${esc(r.name)}</b></td><td class="muted">${esc(r.detail)}</td><td class="loc">${lf}</td></tr>`;
  }).join('');
  el.innerHTML=`<table><thead><tr><th>STATE</th><th>RULE</th><th>CONDITION</th><th>LAST FIRED</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderTrend(elId, hist, key, color){
  const c=makeChart(elId); if(!c) return;
  const data=(hist||[]).map(h=>({value:h[key], ts:h.ts}));
  const sm=elId!=='resTrend'&&elId!=='postureTrend'&&elId!=='costTrend'?false:true;
  const grad=new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'55'},{offset:1,color:color+'05'}]);
  c.setOption({grid:{left:8,right:12,top:14,bottom:sm?4:18,containLabel:true}, tooltip:{trigger:'axis'},
    xAxis:{type:'time',axisLabel:{show:!sm,color:'#8190a3',fontSize:10},axisLine:{lineStyle:{color:'rgba(255,255,255,.15)'}}},
    yAxis:{type:'value',...axisStyle},
    series:[{type:'line',data:data.map(d=>[d.ts,d.value]),smooth:true,showSymbol:false,
      lineStyle:{width:2.4,color:color,shadowBlur:12,shadowColor:color+'aa'},
      areaStyle:{color:grad},itemStyle:{color:color}}]});
}

let syncedTimer=null;
function updateSynced(){ const el=document.getElementById('synced'); el.textContent='sync: '+rel(new Date().toISOString()); }
async function loadAll(){
  const btn=document.getElementById('refresh'); btn.disabled=true; btn.textContent='↻ Refreshing…';
  try{
    const s=await (await fetch('/api/summary')).json();
    if(s.error){ if(s.code==='not_configured') toast(s.error); }
    const days=document.getElementById('days').value;
    const [inv, comp, findings, advisor, logs, alerts, history]=await Promise.all([
      fetch('/api/inventory').then(r=>r.json()).catch(()=>null),
      fetch('/api/compliance').then(r=>r.json()).catch(()=>null),
      fetch('/api/findings').then(r=>r.json()).catch(()=>null),
      fetch('/api/advisor').then(r=>r.json()).catch(()=>[]),
      fetch('/api/logs').then(r=>r.json()).catch(()=>[]),
      fetch('/api/alerts').then(r=>r.json()).catch(()=>null),
      fetch('/api/history').then(r=>r.json()).catch(()=>[]),
    ]);
    if(s&&!s.error){
      const comp4kpi=comp||{};
      const s2=Object.assign({}, s, {governance_gap_count:(comp4kpi.governance_gap_count!=null?comp4kpi.governance_gap_count:(comp4kpi.governance_gaps||[]).length)});
      renderKpis(s2, findings);
    }
    if(inv){ renderType(document.getElementById('typeChart'), inv); renderType(document.getElementById('typeChart2'), inv); renderLoc(document.getElementById('locChart'), inv); renderLoc(document.getElementById('locChart2'), inv); renderTag(document.getElementById('tagChart'), inv); renderType(document.getElementById('expChart'), inv); }
    if(comp){ renderGov(document.getElementById('govChart'), comp); renderCompliance(document.getElementById('compliance'), comp); renderRbac(document.getElementById('rbac'), comp); }
    if(findings){ renderSev(document.getElementById('sevChart'), findings); renderFindings(document.getElementById('findings'), findings); }
    renderAdvisor(document.getElementById('advisor'), advisor);
    renderFeed(document.getElementById('feed'), logs, findings);
    renderAlerts(document.getElementById('alerts'), alerts);
    if(history){ renderTrend('resTrend', history, 'resources', '#1fd1a5'); renderTrend('postureTrend', history, 'posture_pct', '#27e0c8'); renderTrend('costTrend', history, 'cost', '#ffc24b'); }
    fill('rg','/api/resources',renderRg,'rg-search');
    stamp(); updateSynced();
  }catch(e){ toast('Load failed: '+e); }
  finally{ btn.disabled=false; btn.textContent='↻ Refresh'; }
}
document.getElementById('rg-search').addEventListener('input', ()=>fill('rg','/api/resources',renderRg,'rg-search'));
document.getElementById('refresh').addEventListener('click', loadAll);
document.getElementById('days').addEventListener('change', loadAll);
document.getElementById('sync').addEventListener('click', async ()=>{
  const b=document.getElementById('sync'); b.disabled=true; b.textContent='⇅ Syncing…';
  try{ await fetch('/api/refresh',{method:'POST'}); await loadAll(); }catch(e){ toast('Sync failed: '+e); }
  finally{ b.disabled=false; b.textContent='⇅ Sync now'; updateSynced(); }
});
document.getElementById('export').addEventListener('click', async ()=>{
  try{
    const r=await fetch('/api/export'); const j=await r.json();
    const blob=new Blob([JSON.stringify(j,null,2)],{type:'application/json'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='azure-inspect-snapshot.json'; a.click(); URL.revokeObjectURL(a.href);
  }catch(e){ toast('Export failed: '+e); }
});
if(document.getElementById('auto').checked){ setInterval(loadAll, 60000); setInterval(updateSynced, 15000); }
loadAll();
</script>
</body>
</html>
"""


_LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Azure-Inspect · Sign in</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  * { box-sizing:border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
    font-family:'Inter',system-ui,sans-serif; color:#eaf1f8;
    background: radial-gradient(40% 50% at 30% 30%, rgba(88,166,255,.25), transparent 60%),
                radial-gradient(45% 55% at 75% 70%, rgba(124,92,255,.22), transparent 60%), #070a12; }
  .box { width:min(380px,92vw); padding:2.2rem; border-radius:20px; text-align:center;
    background:rgba(20,26,38,.7); border:1px solid rgba(255,255,255,.1); box-shadow:0 20px 60px rgba(0,0,0,.5);
    backdrop-filter:blur(14px); }
  .box h1 { margin:.2rem 0 1.4rem; font-size:1.4rem; font-weight:800; letter-spacing:-.02em;
    background:linear-gradient(100deg,#58a6ff,#39d3ff 50%,#7c5cff); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  input[type=password] { width:100%; padding:.8rem 1rem; border-radius:12px; border:1px solid rgba(255,255,255,.12);
    background:#0e131d; color:#eaf1f8; font:inherit; font-size:.95rem; margin-bottom:.9rem; }
  input[type=password]:focus { outline:none; border-color:#58a6ff; box-shadow:0 0 0 3px rgba(88,166,255,.15); }
  button { width:100%; padding:.8rem; border:none; border-radius:12px; cursor:pointer; font:inherit; font-weight:600; font-size:.95rem;
    color:#06101f; background:linear-gradient(100deg,#58a6ff,#39d3ff); transition:transform .1s, box-shadow .15s; }
  button:hover { box-shadow:0 0 20px rgba(57,211,255,.4); transform:translateY(-1px); }
  .err { color:#ff6b81; font-size:.82rem; margin-bottom:.8rem; min-height:1em; }
  .hint { color:#8593a6; font-size:.74rem; margin-top:1rem; }
</style>
</head>
<body>
<div class="box">
  <h1>Azure-Inspect</h1>
  <form method="post" action="/login">
    <div class="err">{{ error or '' }}</div>
    <input type="password" name="password" placeholder="Dashboard password" autofocus required>
    <button type="submit">Sign in</button>
  </form>
  <div class="hint">Protected dashboard · service-principal view</div>
</div>
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

    # Activity-log failures take priority over the generic auth branch: a 403
    # here is specifically "SPN lacks tenant/directory Reader", not a generic
    # auth problem, and deserves its own actionable banner.
    if "insights" in lowered and ("eventlogs" in lowered or "activitylog" in lowered
                                   or "invalidresourcetype" in lowered):
        if "403" in msg or "authorizationfailed" in lowered or "forbidden" in lowered:
            return {
                "error": "Azure rejected the activity-log request — the service "
                         "principal most likely lacks Reader (or Monitoring "
                         "Reader) at the tenant/directory scope. Grant that role "
                         "in Entra ID, then refresh. "
                         f"({msg[:140]})",
                "code": "log_query_error",
            }, 503
        return {
            "error": "The activity-log endpoint returned an error. If this "
                     "persists it is a configuration issue with the api-version "
                     "or resource type. "
                     f"({msg[:140]})",
            "code": "log_query_error",
        }, 503

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
    if "getazuresubscriptionbyid" in lowered:
        return {
            "error": "Azure rejected a subscription lookup — the service "
                     "principal likely lacks Reader at the subscription scope. "
                     f"({msg[:160]})",
            "code": "auth_error",
        }, 503
    if "costmanagement" in lowered and ("query" in lowered or "cost" in lowered):
        return {
            "error": "Azure Cost Management has no billing data for this "
                     "subscription yet. This commonly happens just after a "
                     "subscription is moved to a new tenant (data can take "
                     "hours to propagate) or when the service principal lacks "
                     "the Cost Management Reader role. "
                     f"({msg[:160]})",
            "code": "cost_data_unavailable",
        }, 503
    if "insights" in lowered and ("eventlogs" in lowered or "activitylog" in lowered
                                   or "invalidresourcetype" in lowered):
        # Activity-log endpoint failure. A 403 means the SPN lacks read at
        # tenant/directory scope (grant Reader at tenant scope in Entra ID);
        # a 404 means the api-version/resource-type is wrong (code defect).
        if "403" in msg or "authorizationfailed" in lowered or "forbidden" in lowered:
            return {
                "error": "Azure rejected the activity-log request — the service "
                         "principal most likely lacks Reader (or Monitoring "
                         "Reader) at the tenant/directory scope. Grant that role "
                         "in Entra ID, then refresh. "
                         f"({msg[:140]})",
                "code": "log_query_error",
            }, 503
        return {
            "error": "The activity-log endpoint returned an error. If this "
                     "persists it is a configuration issue with the api-version "
                     "or resource type. "
                     f"({msg[:140]})",
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
    auth: Optional[bool] = None,
) -> Flask:
    """Build and return the Flask application.

    Args:
        config_provider: callable returning an ``AzureConfig``. When omitted,
            the app falls back to ``load_config()`` (env/.env). Injecting a
            provider keeps the app testable and lets callers supply config
            without touching the environment.
        debug: Flask debug mode.
        auth: dashboard password-gate behaviour. ``None`` (default) enables the
            gate when ``DASHBOARD_PASSWORD`` is set in the environment, and
            leaves it open otherwise. Pass ``False`` to force the gate off
            (used by tests); pass ``True`` to force it on.
    """
    app = Flask(__name__)
    cache = DataCache()

    # --- password gate (optional) ---
    # Load .env so DASHBOARD_PASSWORD / DASHBOARD_SECRET are available in the
    # process environment (they live in the same .env as the Azure creds).
    load_dotenv()
    # DASHBOARD_PASSWORD enables the gate. If unset, the dashboard is open.
    # DASHBOARD_SECRET signs the session cookie; a random one is generated when
    # unset (sessions reset on restart — set it for stable logins).
    required_pw = os.environ.get("DASHBOARD_PASSWORD")
    if auth is False:
        required_pw = None  # force gate off (e.g. tests)
    elif auth is True and not required_pw:
        required_pw = secrets.token_hex(16)  # force gate on with a throwaway pw
    secret = os.environ.get("DASHBOARD_SECRET")
    if not secret:
        secret = secrets.token_hex(32)
        if auth is not False:
            app.logger.warning(
                "DASHBOARD_SECRET not set; generated an ephemeral signing key "
                "(sessions expire on restart). Set DASHBOARD_SECRET in .env."
            )
    if auth is not False and not required_pw:
        app.logger.warning(
            "DASHBOARD_PASSWORD not set; dashboard is OPEN (no auth gate)."
        )
    app.secret_key = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Only set Secure when not on plain HTTP (LAN). Behind TLS, set
    # DASHBOARD_SECURE_COOKIE=1 to force Secure cookies.
    if os.environ.get("DASHBOARD_SECURE_COOKIE") == "1":
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.before_request
    def _require_auth():
        if not required_pw:
            return  # gate disabled
        if request.path in ("/login", "/health"):
            return
        if request.path.startswith("/static"):
            return
        if session.get("authed"):
            return
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not required_pw:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            pw = request.form.get("password", "")
            # constant-time comparison to avoid timing leaks
            if hmac.compare_digest(pw, required_pw):
                session["authed"] = True
                session.permanent = True
                return redirect(url_for("index"))
            error = "Incorrect password"
        return render_template_string(_LOGIN_HTML, error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        return render_template_string(_INDEX_HTML)

    @app.route("/api/summary")
    def api_summary():
        def _compute(cfg):
            from datetime import date, timedelta
            from ..graph import resource_inventory
            rgs = list_resource_groups(cfg)
            costs = cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=30))
            total = sum(c.cost for c in costs)
            currency = costs[0].currency if costs else ""
            try:
                logs = get_activity_log(cfg, hours=24)
            except Exception:
                logs = []
            # Reuse the cached inventory payload (already fetched for the
            # dashboard) instead of re-querying Resource Graph here; that avoids
            # a duplicate call that can get throttled and return None.
            total_resources = 0
            inv_cached = cache.value("inventory")
            if isinstance(inv_cached, dict) and inv_cached.get("total_resources"):
                total_resources = inv_cached["total_resources"]
            else:
                try:
                    inv = resource_inventory(cfg)
                    total_resources = inv.get("total_resources") or 0
                except Exception:
                    total_resources = 0
            return {
                "subscription_id": cfg.subscription_id,
                "resource_group_count": len(rgs),
                "total_resources": total_resources,
                "total_cost": round(total, 2),
                "currency": currency,
                "activity_count": len(logs),
            }
        return _safe(lambda cfg: cache.cached("summary", lambda: _compute(cfg)), config_provider)

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
        return _safe(lambda cfg: cache.cached("resources", lambda: _compute(cfg)), config_provider)

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
        return _safe(lambda cfg: cache.cached(f"costs_{days}", lambda: _compute(cfg)), config_provider)

    @app.route("/api/costs_daily")
    def api_costs_daily():
        """Per-day total cost series (cached from the refresher).

        Used by the cost-trend chart. Returns the raw cached series
        (``[{"day", "cost", "currency"}]``) or an empty list when unavailable.
        """
        data = cache.value("costs_daily") or []
        return jsonify(data)

    @app.route("/api/costs_rg_daily")
    def api_costs_rg_daily():
        """Per-day cost for each resource group (cached from the refresher).

        Returns ``{resource_group: [{"day", "cost"}]}`` for drawing mini
        sparklines in the cost table. Empty dict when unavailable.
        """
        data = cache.value("costs_rg_daily") or {}
        return jsonify(data)

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
        return _safe(lambda cfg: cache.cached("logs", lambda: _compute(cfg)), config_provider)

    @app.route("/api/compliance")
    def api_compliance():
        from ..compliance import posture_summary

        def _compute(cfg):
            return posture_summary(cfg)
        return _safe(lambda cfg: cache.cached("compliance", lambda: _compute(cfg)), config_provider)

    @app.route("/api/inventory")
    def api_inventory():
        from ..graph import resource_inventory

        def _compute(cfg):
            return resource_inventory(cfg)
        return _safe(lambda cfg: cache.cached("inventory", lambda: _compute(cfg)), config_provider)

    @app.route("/api/advisor")
    def api_advisor():
        from ..advisor import get_recommendations

        def _compute(cfg):
            return get_recommendations(cfg)
        return _safe(lambda cfg: cache.cached("advisor", lambda: _compute(cfg)), config_provider)

    @app.route("/api/findings")
    def api_findings():
        """Merged, severity-sorted security findings: governance gaps + Advisor.

        Each finding: {severity, source, title, detail, resource}. Severity order
        Critical > High > Medium > Low so the dashboard can render a risk-ranked
        feed. Governance gaps are always 'High'; Advisor recs map High->High,
        Medium->Medium, otherwise Low.
        """
        def _compute(cfg):
            from ..compliance import posture_summary
            from ..advisor import get_recommendations

            findings = []
            try:
                comp = posture_summary(cfg)
                for g in comp.get("governance_gaps", []):
                    findings.append({
                        "severity": "High",
                        "source": "Governance",
                        "title": f"RG '{g.get('resource')}' missing tag",
                        "detail": g.get("issue", ""),
                        "resource": g.get("resource", ""),
                    })
            except Exception:
                pass
            try:
                for a in get_recommendations(cfg):
                    impact = a.get("impact", "Low")
                    sev = {"High": "High", "Medium": "Medium", "Critical": "Critical"}.get(impact, "Low")
                    findings.append({
                        "severity": sev,
                        "source": "Advisor",
                        "title": a.get("category", "Recommendation"),
                        "detail": a.get("short_description") or a.get("risk") or "",
                        "resource": a.get("resource", ""),
                    })
            except Exception:
                pass
            order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            findings.sort(key=lambda f: order.get(f["severity"], 9))
            counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
            for f in findings:
                counts[f["severity"]] = counts.get(f["severity"], 0) + 1
            return {"findings": findings, "counts": counts}
        return _safe(lambda cfg: cache.cached("findings", lambda: _compute(cfg)), config_provider)

    @app.route("/api/alerts")
    def api_alerts():
        """Grafana-style alerting view: the rules Azure-Inspect evaluates, their
        current status, and when each last fired (from the alert_cooldown table).

        Status is computed live against the current cache (not just 'did it fire
        recently'): stale data / missing baseline are reported as firing so the
        panel reflects real conditions, not just cooldown state.
        """
        def _last_fired(key):
            try:
                import sqlite3
                from pathlib import Path
                db = Path.home() / "code" / "Azure-Inspect" / "azure_inspect.db"
                con = sqlite3.connect(db)
                row = con.execute(
                    "SELECT ts FROM alert_cooldown WHERE key=?", (key,)
                ).fetchone()
                con.close()
                return row[0] if row else None
            except Exception:
                return None

        def _compute(cfg):
            from .. import alerts as al
            rules = []
            # 1) Spend spike
            daily = cache.value("costs_daily") or []
            series = [(row["day"], float(row["cost"])) for row in daily if "cost" in row]
            spike_state = "ok"
            if len(series) >= 8:
                latest = series[-1][1]
                baseline = sorted(c[1] for c in series[-8:-1])
                median = baseline[len(baseline) // 2]
                threshold = max(2 * median, 10.0)
                if median > 0 and latest > threshold:
                    spike_state = "firing"
            rules.append({
                "key": "spend_spike", "name": "Spend spike",
                "state": spike_state, "last_fired": _last_fired("spend_spike"),
                "detail": "latest daily cost > 2x 7d median and above 10 CHF floor",
            })
            # 2) New resource group
            baseline = cache.value("rg_baseline")
            current = [rg.name for rg in list_resource_groups(cfg)]
            new_state = "ok"
            if baseline is not None:
                new_rgs = set(current) - set(baseline)
                if new_rgs:
                    new_state = "firing"
            rules.append({
                "key": "new_rg", "name": "New resource group",
                "state": new_state, "last_fired": _last_fired("new_rg:any") or _last_fired("new_rg"),
                "detail": "a resource group appeared that was not in the stored baseline",
            })
            # 3) Stale data
            cost_ts = cache.written_at("costs_30")
            stale_state = "ok"
            if cost_ts is None:
                stale_state = "firing"
            rules.append({
                "key": "stale_data", "name": "Stale cost data",
                "state": stale_state, "last_fired": _last_fired("stale_cost"),
                "detail": "cost cache has not refreshed successfully",
            })
            return {"rules": rules, "telegram_configured": bool(al._read_env(al._ENV_PATH).get("TELEGRAM_BOT_TOKEN"))}
        return _safe(lambda cfg: cache.cached("alerts", lambda: _compute(cfg), force=False), config_provider)

    @app.route("/api/export")
    def api_export():
        """Grafana-style 'export dashboard' — return a full current snapshot as JSON."""
        def _compute(cfg):
            snap = {}
            for k in ("summary", "resources", "inventory", "compliance", "advisor",
                      "findings", "costs_30", "costs_daily", "logs", "history"):
                snap[k] = cache.value(k)
            snap["generated_at"] = datetime.now(timezone.utc).isoformat()
            return snap
        return _safe(lambda cfg: cache.cached("export", lambda: _compute(cfg)), config_provider)

    @app.route("/api/history")
    def api_history():
        """Rolling time-series samples (resources / posture % / spend) for trend charts."""
        return jsonify(cache.value("history") or [])

    @app.route("/health")
    def health():
        # Report data freshness, not just process liveness: a 200 here means
        # the process is up AND we know when each dataset was last written.
        freshness = {k: cache.written_at(k) for k in
                     ("summary", "resources", "costs_30", "logs", "compliance")}
        configured = _load_cfg(config_provider) is not None
        return jsonify({
            "status": "ok" if configured else "not_configured",
            "data_freshness": freshness,
        })

    @app.route("/api/freshness")
    def api_freshness():
        """Per-dataset last-successful-write timestamps (ISO or null)."""
        keys = ("summary", "resources", "costs_7", "costs_30", "costs_90",
                "logs", "compliance")
        return jsonify({k: cache.written_at(k) for k in keys})

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        """Force an immediate background refresh of every cached dataset.

        Returns the per-key result. Failures keep the previous good value.
        """
        from ..refresher import _refresh_once
        from ..config import load_config as _lc
        try:
            cfg = _lc()
        except Exception as exc:
            return jsonify({"error": f"config unavailable: {exc}", "code": "not_configured"}), 503
        results = _refresh_once(cache, cfg)
        return jsonify({"refreshed": results, "ok": all(v == "ok" for v in results.values())})

    return app


def _date_window(days: int):
    """Return the ``from_date`` (date) for a trailing ``days`` window."""
    from datetime import date, timedelta
    return date.today() - timedelta(days=days)


if __name__ == "__main__":
    create_app().run(debug=False, host="127.0.0.1", port=5000)
