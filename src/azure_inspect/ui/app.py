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
  .logout { color:var(--muted); text-decoration:none; font-size:.8rem; padding:.4rem .7rem; border:1px solid var(--border); border-radius:10px; transition:all .15s; }
  .logout:hover { color:var(--fg); border-color:var(--accent); }
  main { padding:1.9rem; max-width:1180px; margin:0 auto; }

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

  .card .ico { position:absolute; top:1.15rem; right:1.2rem; width:22px; height:22px; opacity:.5; color:var(--accent); }
  .card .spark { margin-top:.7rem; width:100%; height:34px; display:block; }
  .card .delta { font-size:.72rem; margin-top:.35rem; font-weight:600; }
  .card .delta.up { color:var(--red); } .card .delta.down { color:var(--green); }
  .card .delta.flat { color:var(--muted); }

  /* cost trend chart */
  .chart-wrap { position:relative; margin-top:.4rem; }
  #costchart { width:100%; height:240px; display:block; }
  .chart-meta { display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; margin-bottom:.4rem; flex-wrap:wrap; }
  .chart-total { font-size:1.5rem; font-weight:800; letter-spacing:-.03em; background:linear-gradient(100deg,var(--accent),var(--cyan)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  .chart-sub { font-size:.74rem; color:var(--muted); }
  .legend { display:flex; gap:1rem; font-size:.72rem; color:var(--muted); align-items:center; }
  .legend .sw { width:12px; height:12px; border-radius:3px; background:linear-gradient(90deg,var(--accent),var(--cyan)); display:inline-block; margin-right:.35rem; vertical-align:middle; }
  .chart-tip { position:absolute; pointer-events:none; background:rgba(14,19,29,.95); border:1px solid var(--border); border-radius:9px; padding:.4rem .6rem; font-size:.74rem; opacity:0; transform:translate(-50%,-115%); transition:opacity .12s; white-space:nowrap; box-shadow:var(--shadow); }
  .chart-tip.show { opacity:1; }

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
  .spark-cell { width:104px; }
  .minispark { display:block; }
  .pill { padding:2px 10px; border-radius:999px; font-size:.73rem; font-weight:600; }
  .ok { background:rgba(62,240,163,.15); color:var(--green); }
  .fail { background:rgba(255,107,129,.15); color:var(--red); }
  .state { background:rgba(88,166,255,.15); color:var(--accent); }
  .loc { font-size:.72rem; color:var(--muted); }
  .muted { color:var(--muted); }

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
    <span id="meta"><span class="live"></span> <b id="sub">…</b> · <span id="updated">–</span> · <span id="synced" class="muted">sync: –</span></span>
    <label>Cost
      <select id="days"><option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option></select>
    </label>
    <label title="Auto-refresh dashboard every 60s (reads local cache)"><input type="checkbox" id="auto" checked> auto</label>
    <button id="sync">⇅ Sync now</button>
    <button id="refresh">↻ Refresh</button>
    <a class="logout" href="/logout">Logout</a>
  </div>
</header>
<div id="toast"></div>
<main>
  <div class="cards" id="cards">
    <div class="card">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 10h18M8 4v3M16 4v3"/></svg>
      <div class="k">Resource groups</div><div class="v dash" id="c-rg">–</div>
    </div>
    <div class="card">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 3v18M7 7h7a3 3 0 0 1 0 6H7m0 0h8a3 3 0 0 1 0 6H7"/></svg>
      <div class="k">Total cost (30d)</div><div class="v dash" id="c-cost">–</div>
      <svg class="spark" id="c-cost-spark" viewBox="0 0 100 34" preserveAspectRatio="none"></svg>
      <div class="delta flat" id="c-cost-delta"></div>
    </div>
    <div class="card">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M13 3 4 14h6l-1 7 9-11h-6l1-7Z"/></svg>
      <div class="k">Activity (24h)</div><div class="v dash" id="c-act">–</div>
    </div>
    <div class="card">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 2 4 5v6c0 5 3.5 8 8 11 4.5-3 8-6 8-11V5l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>
      <div class="k">Governance gaps</div><div class="v dash" id="c-gap">–</div>
    </div>
  </div>

  <section>
    <div class="section-head"><h2><span class="dot"></span> Resource groups</h2>
      <input type="search" id="rg-search" placeholder="filter…"></div>
    <div id="rg"><div class="loading"><div class="sk" style="width:40%"></div><div class="sk" style="width:90%"></div><div class="sk" style="width:75%"></div></div></div>
  </section>

  <section><div class="section-head"><h2><span class="dot"></span> Cost by resource group</h2></div>
    <div id="cost"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div><div class="sk" style="width:70%"></div></div></div></section>

  <section><div class="section-head"><h2><span class="dot"></span> Cost trend (14d)</h2>
      <div class="legend"><span><span class="sw"></span> daily spend</span></div></div>
    <div class="chart-meta">
      <div><span class="chart-total" id="trend-total">–</span> <span class="chart-sub" id="trend-sub"></span></div>
    </div>
    <div class="chart-wrap">
      <svg id="costchart" viewBox="0 0 600 240" preserveAspectRatio="none"></svg>
      <div class="chart-tip" id="chart-tip"></div>
    </div>
  </section>

  <section><div class="section-head"><h2><span class="dot"></span> Activity log</h2></div>
    <div id="logs"><div class="loading"><div class="sk" style="width:55%"></div><div class="sk" style="width:80%"></div><div class="sk" style="width:65%"></div></div></div></section>

  <section><div class="section-head"><h2><span class="dot"></span> Compliance &amp; access posture</h2>
    <span class="pill state" id="posture-badge">–</span></div>
    <div id="compliance"><div class="loading"><div class="sk" style="width:50%"></div><div class="sk" style="width:85%"></div><div class="sk" style="width:70%"></div></div></div></section>
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
function renderCost(el,data,trendMap){
  if(!data.length){ el.innerHTML=emptyState('No cost data','Cost Management has not indexed this subscription yet — this can take a few hours after a tenant move.'); return; }
  const max=Math.max(...data.map(d=>d.cost),0.0001);
  let rows=data.sort((a,b)=>b.cost-a.cost).map((d,i)=>{ const pct=Math.max(2,(d.cost/max*100)).toFixed(0);
    const rg=d.resource_group||'(none)';
    const series=(trendMap&&trendMap[rg]||[]).map(x=>x.cost);
    const spark=series.length>=2?miniSpark(series):'';
    return '<tr style="animation-delay:'+(i*40)+'ms"><td><b>'+esc(rg)+'</b></td>'+
      '<td class="bar-wrap"><div class="bar" style="width:'+pct+'%"></div></td>'+
      '<td class="spark-cell">'+(spark||'<span class="muted">–</span>')+'</td>'+
      '<td>'+Number(d.cost).toFixed(2)+' '+esc(d.currency)+'</td></tr>'; }).join('');
  el.innerHTML='<table><thead><tr><th>Resource group</th><th></th><th>Trend (14d)</th><th>Cost</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
function miniSpark(values){ // returns a tiny inline SVG string
  const W=90,H=22,min=Math.min(...values),max=Math.max(...values),rng=(max-min)||1;
  const pts=values.map((v,i)=>{ const x=(i/(values.length-1))*W; const y=H-2-((v-min)/rng)*(H-4); return x.toFixed(1)+','+y.toFixed(1); }).join(' ');
  return '<svg class="minispark" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" width="'+W+'" height="'+H+'">'+
    '<polyline points="'+pts+'" fill="none" stroke="url(#miniG)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'+
    '<defs><linearGradient id="miniG" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#58a6ff"/><stop offset="1" stop-color="#39d3ff"/></linearGradient></defs></svg>';
}

function renderLogs(el,data){
  if(!data.length){ el.innerHTML=emptyState('Activity log unavailable','The legacy Azure activity-log API (Microsoft.Insights/eventLogs) is retired in this tenant API surface. To enable it, configure diagnostic settings → Log Analytics and query via Azure Resource Graph. Other tabs (cost, resources, compliance) are live.'); return; }
  let rows=data.slice(0,60).map((d,i)=>{ const st=(d.status||'').toLowerCase().includes('fail')?'fail':'ok';
    return '<tr style="animation-delay:'+(i*30)+'ms"><td title="'+esc(fmtTs(d.event_timestamp))+'">'+esc(rel(d.event_timestamp))+'</td>'+
      '<td>'+esc(d.operation)+'</td><td class="loc">'+esc(d.resource_group||'–')+'</td><td class="loc">'+esc(d.caller||'–')+'</td>'+
      '<td><span class="pill '+st+'">'+esc(d.status)+'</span></td></tr>'; }).join('');
  el.innerHTML='<table><thead><tr><th>When</th><th>Operation</th><th>RG</th><th>Caller</th><th>Status</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
function renderCompliance(el,data){
  const gaps=data.governance_gaps||[];
  const badge=document.getElementById('posture-badge');
  const gapCard=document.getElementById('c-gap');
  gapCard.textContent=String(data.governance_gap_count ?? gaps.length); gapCard.className='v';
  if(gaps.length){ badge.textContent=gaps.length+' gap'+(gaps.length>1?'s':''); badge.className='pill fail'; }
  else { badge.textContent='clean'; badge.className='pill ok'; }
  // access table
  const roles=data.role_assignments||[];
  let html='';
  if(roles.length){
    const rr=roles.map((r,i)=>'<tr style="animation-delay:'+(i*30)+'ms"><td><b>'+esc(r.role)+'</b></td>'+
      '<td class="loc">'+esc(r.principal_id)+'</td><td class="loc">'+esc(r.scope)+'</td></tr>').join('');
    html+='<h3 style="font-size:.8rem;color:var(--muted);margin:.2rem 0 .6rem">Access (RBAC)</h3>'+
      '<table><thead><tr><th>Role</th><th>Principal</th><th>Scope</th></tr></thead><tbody>'+rr+'</tbody></table>';
  }
  if(gaps.length){
    const gg=gaps.map((g,i)=>'<tr style="animation-delay:'+(i*30)+'ms"><td><b>'+esc(g.resource)+'</b></td>'+
      '<td class="loc">'+esc(g.resource_type)+'</td><td><span class="pill fail">'+esc(g.issue)+'</span></td></tr>').join('');
    html+='<h3 style="font-size:.8rem;color:var(--muted);margin:1rem 0 .6rem">Governance gaps</h3>'+
      '<table><thead><tr><th>Resource</th><th>Type</th><th>Issue</th></tr></thead><tbody>'+gg+'</tbody></table>';
  }
  if(!html) html=emptyState('No posture data','No role assignments or governance gaps returned.');
  el.innerHTML=html;
}
function sparkline(svg, values){ // tiny inline sparkline into an <svg viewBox="0 0 100 34">
  if(!svg) return;
  if(!values || values.length<2){ svg.innerHTML=''; return; }
  const W=100,H=34,min=Math.min(...values),max=Math.max(...values),rng=(max-min)||1;
  const pts=values.map((v,i)=>{ const x=(i/(values.length-1))*W; const y=H-2-((v-min)/rng)*(H-4); return x.toFixed(1)+','+y.toFixed(1); }).join(' ');
  const area='M0,'+H+' L'+pts.replace(/ /g,' L')+' L'+W+','+H+' Z';
  svg.innerHTML='<polygon points="'+pts+'" fill="none" stroke="url(#sparkG)" stroke-width="1.6" stroke-linejoin="round"/>'+
    '<polygon points="'+area+'" fill="url(#sparkGA)"/>'+
    '<defs><linearGradient id="sparkG" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#58a6ff"/><stop offset="1" stop-color="#39d3ff"/></linearGradient>'+
    '<linearGradient id="sparkGA" x1="0" y1="0" x2="0" y2="1"><stop stop-color="rgba(57,211,255,.28)"/><stop offset="1" stop-color="rgba(57,211,255,0)"/></linearGradient></defs>';
}
function drawCostChart(svg, tip, series){
  if(!svg) return;
  if(!series || series.length<2){ svg.innerHTML=''; if(tip)tip.classList.remove('show'); return; }
  const W=600,H=240,pad=34,min=Math.min(...series.map(d=>d.cost)),max=Math.max(...series.map(d=>d.cost)),rng=(max-min)||1;
  const X=i=>pad+(i/(series.length-1))*(W-pad*1.4);
  const Y=v=>H-pad-((v-min)/rng)*(H-pad*2);
  let path='', area='M'+pad+','+(H-pad);
  series.forEach((d,i)=>{ const x=X(i).toFixed(1),y=Y(d.cost).toFixed(1); path+=(i?' L':'M')+x+','+y; area+=' L'+x+','+y; });
  area+=' L'+X(series.length-1).toFixed(1)+','+(H-pad)+' Z';
  // gridlines + y labels (min/mid/max)
  const fmt=v=>Number(v).toFixed(2);
  let grid='';
  [min,(min+max)/2,max].forEach((g,i)=>{ const y=Y(g).toFixed(1);
    grid+='<line x1="'+pad+'" y1="'+y+'" x2="'+(W-pad*0.4)+'" y2="'+y+'" stroke="rgba(255,255,255,.07)"/>'+
      '<text x="4" y="'+(+y+3)+'" fill="#8593a6" font-size="10">'+fmt(g)+'</text>'; });
  // x labels (first + last)
  const xlabels='<text x="'+pad+'" y="'+(H-10)+'" fill="#8593a6" font-size="10">'+series[0].day.slice(5)+'</text>'+
    '<text x="'+(W-pad*0.4-30)+'" y="'+(H-10)+'" fill="#8593a6" font-size="10" text-anchor="end">'+series[series.length-1].day.slice(5)+'</text>';
  svg.innerHTML=grid+xlabels+
    '<path d="'+area+'" fill="url(#areaG)"/>'+
    '<path d="'+path+'" fill="none" stroke="url(#lineG)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'+
    series.map((d,i)=>'<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(d.cost).toFixed(1)+'" r="2.6" fill="#39d3ff"/>').join('')+
    '<defs><linearGradient id="lineG" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#58a6ff"/><stop offset="1" stop-color="#39d3ff"/></linearGradient>'+
    '<linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1"><stop stop-color="rgba(88,166,255,.35)"/><stop offset="1" stop-color="rgba(57,211,255,0)"/></linearGradient></defs>';
  // hover
  svg.onmousemove=function(e){ const r=svg.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*W;
    let i=Math.round((px-pad)/((W-pad*1.4)/(series.length-1))); i=Math.max(0,Math.min(series.length-1,i));
    const d=series[i]; tip.textContent=d.day+' · '+fmt(d.cost)+' '+d.currency; tip.style.left=(X(i)/W*r.width)+'px'; tip.style.top=(Y(d.cost)/H*r.height)+'px'; tip.classList.add('show'); };
  svg.onmouseleave=function(){ tip.classList.remove('show'); };
}
async function fillTrend(){
  const svg=document.getElementById('costchart'), tip=document.getElementById('chart-tip');
  const totEl=document.getElementById('trend-total'), subEl=document.getElementById('trend-sub');
  try{
    const r=await fetch('/api/costs_daily'); const series=await r.json();
    if(!Array.isArray(series)||!series.length){ svg.innerHTML=''; totEl.textContent='–'; subEl.textContent='no daily data yet'; return; }
    drawCostChart(svg,tip,series);
    // total of available days + delta vs first half vs second half
    const vals=series.map(d=>d.cost), total=vals.reduce((a,b)=>a+b,0), cur=series[0].currency||'';
    const half=Math.floor(vals.length/2), first=vals.slice(0,half).reduce((a,b)=>a+b,0), second=vals.slice(half).reduce((a,b)=>a+b,0);
    totEl.textContent=total.toFixed(2)+' '+cur;
    const pct=first? ((second-first)/first*100):0;
    subEl.textContent=(pct>=0?'▲ ':'▼ ')+Math.abs(pct).toFixed(0)+'% vs first half · '+series.length+'d';
    subEl.style.color=pct>0?'var(--red)':'var(--green)';
    // sparkline in the cost card
    sparkline(document.getElementById('c-cost-spark'), vals);
    const dEl=document.getElementById('c-cost-delta');
    dEl.textContent=(pct>=0?'▲ ':'▼ ')+Math.abs(pct).toFixed(0)+'% trend';
    dEl.className='delta '+(pct>1?'up':pct<-1?'down':'flat');
  }catch(e){ svg.innerHTML=''; totEl.textContent='–'; subEl.textContent='error'; }
}
function relTime(s){ try{ const secs=(Date.now()-new Date(s).getTime())/1000;
  if(secs<60)return Math.round(secs)+'s ago'; if(secs<3600)return Math.round(secs/60)+'m ago';
  if(secs<86400)return Math.round(secs/3600)+'h ago'; return Math.round(secs/86400)+'d ago'; }catch{return '?'; } }
async function updateSynced(){
  try{ const r=await fetch('/api/freshness'); const j=await r.json();
    const newest=Object.values(j).filter(Boolean).sort().pop();
    document.getElementById('synced').textContent='sync: '+relTime(newest); }
  catch{ document.getElementById('synced').textContent='sync: ?'; }
}
async function doSync(){
  const b=document.getElementById('sync'); b.disabled=true; b.textContent='⇅ Syncing…';
  try{ await fetch('/api/refresh',{method:'POST'}); await loadAll(); }
  catch(e){ toast('Sync failed: '+e); }
  finally{ b.disabled=false; b.textContent='⇅ Sync now'; updateSynced(); }
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
      // governance gap count comes from the compliance endpoint; set a placeholder
      document.getElementById('c-gap').textContent='…'; document.getElementById('c-gap').className='v dash';
    }
    const days=document.getElementById('days').value;
    fill('rg','/api/resources',renderRg,'rg-search');
    // fetch RG-trend map once, pass into renderCost for per-RG sparklines
    let trendMap=null;
    try { const tr=await fetch('/api/costs_rg_daily'); trendMap=await tr.json(); } catch(e){}
    fill('cost','/api/costs?days='+days,(el,data)=>renderCost(el,data,trendMap));
    fill('logs','/api/logs',renderLogs);
    fill('compliance','/api/compliance',renderCompliance);
    fillTrend();
  } finally { btn.disabled=false; btn.textContent='↻ Refresh'; }
}
let timer=null;
function setupAuto(){ if(timer)clearInterval(timer); if(document.getElementById('auto').checked) timer=setInterval(loadAll,60000); }
document.getElementById('auto').addEventListener('change',setupAuto);
document.getElementById('refresh').addEventListener('click',loadAll);
document.getElementById('sync').addEventListener('click',doSync);
document.getElementById('days').addEventListener('change',loadAll);
document.getElementById('rg-search').addEventListener('input',()=>fill('rg','/api/resources',renderRg,'rg-search'));
loadAll(); setupAuto(); updateSynced();
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
            rgs = list_resource_groups(cfg)
            costs = cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=30))
            total = sum(c.cost for c in costs)
            currency = costs[0].currency if costs else ""
            # Activity log is optional for the summary: if it's unavailable
            # (e.g. SPN lacks tenant Reader), don't fail the whole card row.
            try:
                logs = get_activity_log(cfg, hours=24)
            except Exception:
                logs = []
            return {
                "subscription_id": cfg.subscription_id,
                "resource_group_count": len(rgs),
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
    create_app().run(debug=True, host="127.0.0.1", port=5000)
