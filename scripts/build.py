#!/usr/bin/env python3
"""Build The Signal's static site from the JSON in /data into /docs.

Standard library only, so the daily run needs no installs.
Usage: python3 scripts/build.py          (validate + build)
       python3 scripts/build.py --check  (validate only)
"""
import datetime as dt
import html
import json
import math
import random
import re
import shutil
import sys
from pathlib import Path

import maps

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT / "site"
OUT = ROOT / "docs"

SITE_NAME = "The Signal"
SITE_URL = "https://prototypeversions.github.io/TheSignal"
TAGLINE = "What changed in the world today"
DESCRIPTION = ("A finite daily briefing: the handful of developments that changed the picture today, "
               "with sources, momentum and running forecasts.")

CHANGE = {
    "major": ("Major shift", 1.0),
    "new": ("New", 0.78),
    "developing": ("Developing", 0.5),
    "quiet": ("Quiet", 0.18),
}
MOMENTUM = {"up": "Intensifying", "steady": "Holding", "down": "Easing"}
FIELDS = ["AI", "Science", "Medicine", "Space", "Energy", "Climate"]
REGIONS = ["North America", "Latin America", "Europe", "Africa", "Middle East", "Asia", "Oceania"]

e = html.escape


# --------------------------------------------------------------------------- data

class BuildError(Exception):
    pass


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{path.relative_to(ROOT)}: invalid JSON ({exc})")


def load():
    threads = {}
    for p in sorted((DATA / "threads").glob("*.json")):
        t = load_json(p)
        if t.get("id") != p.stem:
            raise BuildError(f"{p.name}: id '{t.get('id')}' must match the file name")
        threads[t["id"]] = t
    editions = [load_json(p) for p in sorted((DATA / "editions").glob("*.json"))]
    editions.sort(key=lambda x: x["date"])
    forecasts = load_json(DATA / "forecasts.json")
    return threads, editions, forecasts


def validate(threads, editions, forecasts):
    errs = []
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for t in threads.values():
        for k in ("id", "title", "section", "region", "started_label", "status", "summary"):
            if not t.get(k):
                errs.append(f"thread {t.get('id')}: missing '{k}'")
        if t.get("section") not in ("world", "frontier"):
            errs.append(f"thread {t['id']}: section must be 'world' or 'frontier'")
    seen = set()
    for ed in editions:
        d = ed.get("date", "?")
        if not date_re.match(d):
            errs.append(f"edition {d}: bad date")
        if d in seen:
            errs.append(f"edition {d}: duplicate date")
        seen.add(d)
        if not ed.get("lede"):
            errs.append(f"edition {d}: missing lede")
        if "ai" in ed:
            errs.append(f"edition {d}: the 'ai' list is now called 'frontiers'")
        for group in ("stories", "frontiers"):
            ids = set()
            for i, s in enumerate(ed.get(group, [])):
                where = f"edition {d} {group}[{i}]"
                if s.get("thread") not in threads:
                    errs.append(f"{where}: unknown thread '{s.get('thread')}' (create data/threads/<id>.json)")
                if s.get("thread") in ids:
                    errs.append(f"{where}: thread '{s.get('thread')}' appears twice")
                ids.add(s.get("thread"))
                if s.get("change") not in CHANGE:
                    errs.append(f"{where}: change must be one of {list(CHANGE)}")
                if s.get("momentum") not in MOMENTUM:
                    errs.append(f"{where}: momentum must be one of {list(MOMENTUM)}")
                need = ["headline", "dek", "body", "sources"] + (["why", "watch"] if group == "stories" else ["picture"])
                if group == "frontiers" and s.get("field") not in FIELDS:
                    errs.append(f"{where}: field must be one of {FIELDS}")
                for k in need:
                    if not s.get(k):
                        errs.append(f"{where}: missing '{k}'")
                if not isinstance(s.get("body", []), list):
                    errs.append(f"{where}: body must be a list of paragraphs")
                errs += check_sources(s.get("sources", []), where)
                errs += maps.validate_places(s.get("places"), where)
        errs += check_markets(ed.get("markets"), f"edition {d} markets")
        errs += check_sources(ed.get("frontier_note_sources", []), f"edition {d} frontier_note", allow_empty=True)
        if len(ed.get("stories", [])) < 3:
            errs.append(f"edition {d}: needs at least 3 stories")
        regions = [p.get("region") for p in ed.get("pulse", [])]
        if sorted(regions) != sorted(REGIONS):
            errs.append(f"edition {d}: pulse must cover exactly {REGIONS}")
        for p in ed.get("pulse", []):
            for tid in p.get("threads", []):
                if tid not in threads:
                    errs.append(f"edition {d} pulse {p.get('region')}: unknown thread '{tid}'")
            errs += check_sources(p.get("sources", []), f"edition {d} pulse {p.get('region')}", allow_empty=True)
    fids = set()
    for f in forecasts:
        fid = f.get("id")
        if fid in fids:
            errs.append(f"forecast {fid}: duplicate id")
        fids.add(fid)
        for k in ("question", "criteria", "category", "opened", "closes", "status", "history"):
            if not f.get(k):
                errs.append(f"forecast {fid}: missing '{k}'")
        last = ""
        for h in f.get("history", []):
            if not (1 <= h.get("p", -1) <= 99):
                errs.append(f"forecast {fid}: probability {h.get('p')} must be 1–99")
            if h.get("date", "") < last:
                errs.append(f"forecast {fid}: history must be in date order (never rewrite past entries)")
            last = h.get("date", "")
            if not h.get("note"):
                errs.append(f"forecast {fid}: every history entry needs a note saying why")
        if f.get("status") == "resolved" and f.get("resolution") not in ("yes", "no", "void"):
            errs.append(f"forecast {fid}: resolved forecasts need resolution yes/no/void")
        for tid in f.get("threads", []):
            if tid not in threads:
                errs.append(f"forecast {fid}: unknown thread '{tid}'")
    if errs:
        raise BuildError("Validation failed:\n  - " + "\n  - ".join(errs))


def check_markets(m, where):
    if not m:
        return []
    errs = []
    if not m.get("label") or not m.get("items"):
        errs.append(f"{where}: needs label and items")
    for it in m.get("items", []):
        if not it.get("name") or not it.get("value"):
            errs.append(f"{where}: each item needs name and value")
        if it.get("change") is not None and not isinstance(it["change"], (int, float)):
            errs.append(f"{where}: change must be a number (percent) or null")
    errs += check_sources(m.get("sources", []), where)
    return errs


def check_sources(sources, where, allow_empty=False):
    errs = []
    if not sources and not allow_empty:
        errs.append(f"{where}: needs at least one source")
    for s in sources:
        if not str(s.get("url", "")).startswith("https://"):
            errs.append(f"{where}: source url must start with https:// ({s.get('url')})")
        if not s.get("outlet") or not s.get("title"):
            errs.append(f"{where}: each source needs outlet and title")
    return errs


# --------------------------------------------------------------------------- helpers

def pdate(s):
    return dt.date.fromisoformat(s)


def long_date(s):
    d = pdate(s)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"


def short_date(s):
    d = pdate(s)
    return f"{d.day} {d.strftime('%b %Y')}"


def day_month(s):
    d = pdate(s)
    return f"{d.day} {d.strftime('%b')}"


def flex_date(s):
    """Background dates may be YYYY-MM or YYYY-MM-DD."""
    if re.match(r"^\d{4}-\d{2}$", s):
        d = dt.date.fromisoformat(s + "-01")
        return d.strftime("%B %Y")
    return short_date(s)


def momentum_icon(m):
    paths = {
        "up": "M2 11 L8 4 L14 11",
        "steady": "M2 8 H14 M10 4 L14 8 L10 12",
        "down": "M2 5 L8 12 L14 5",
    }
    return (f'<svg class="mom-icon" viewBox="0 0 16 16" aria-hidden="true">'
            f'<path d="{paths[m]}" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def badges(s):
    label = CHANGE[s["change"]][0]
    return (f'<span class="chg chg-{s["change"]}">{e(label)}</span>'
            f'<span class="mom mom-{s["momentum"]}">{momentum_icon(s["momentum"])}{e(MOMENTUM[s["momentum"]])}</span>')


def sources_block(sources, label="Sources"):
    if not sources:
        return ""
    items = "".join(
        f'<li><a href="{e(s["url"])}" rel="noopener" target="_blank">{e(s["title"])}</a>'
        f'<span class="outlet">{e(s["outlet"])}</span></li>' for s in sources)
    return (f'<details class="sources"><summary>{e(label)} ({len(sources)})</summary>'
            f'<ul>{items}</ul></details>')


def paras(body):
    return "".join(f"<p>{e(p)}</p>" for p in body)


def short_title(t):
    return t["title"]


# --------------------------------------------------------------------------- the trace

def trace_svg(points, seed, labels=True, height=150, aria="", W=1000, cls="", deco=False):
    """points: list of dicts {x: 0..1, amp: 0..1, mom, label, href, group}.
    Draws a seismograph-like line with a spike at each point."""
    H = height
    k = max(W / 1000, 0.45)
    base = H - (52 if labels else 14)
    top = 14
    rng = random.Random(seed)
    xs = sorted(points, key=lambda p: p["x"])
    segs = []
    x = 0.0
    path = [f"M0 {base:.1f}"]
    step = 7
    spikes = {round(p["x"] * W): p for p in xs}
    spike_xs = sorted(spikes)
    done = set()
    i = 0
    while x <= W:
        near = None
        for sx in spike_xs:
            if sx not in done and abs(sx - x) < 26 * k:
                near = sx
                break
        if near is not None:
            p = spikes[near]
            amp = p["amp"] * (base - top)
            # sharp up-down-up wiggle centered on the spike
            for dx, f in ((-16, 0.08), (-8, -0.2), (0, 1.0), (6, -0.55), (12, 0.3), (18, -0.1), (24, 0.03)):
                px = near + dx * k
                dy = amp * f if f > 0 else max(amp * f * 0.22, -11)
                path.append(f"L{px:.1f} {base - dy:.1f}")
            done.add(near)
            x = near + 26 * k
            continue
        jitter = rng.uniform(-2.2, 2.2)
        path.append(f"L{x:.1f} {base + jitter:.1f}")
        x += step + rng.uniform(-2, 2)
        i += 1
    path.append(f"L{W} {base:.1f}")
    d = " ".join(path)

    grid = []
    for gx in range(0, W + 1, 50 if W >= 600 else 40):
        grid.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" class="g{" gm" if gx % 250 == 0 and W >= 600 else ""}"/>')
    for gy in range(int(base) % 20, H + 1, 20):
        grid.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" class="g"/>')

    marks = []
    for n, p in enumerate(xs):
        px = round(p["x"] * W)
        py = base - p["amp"] * (base - top)
        lab = ""
        if labels:
            anchor = "middle"
            if px < 60:
                anchor = "start"
            elif px > W - 60:
                anchor = "end"
            ly = base + (24 if n % 2 == 0 else 42)
            tick = f'<line x1="{px}" y1="{base + 6}" x2="{px}" y2="{ly - 13}" class="tick"/>'
            lab = f'{tick}<text x="{px}" y="{ly}" text-anchor="{anchor}" class="tl">{e(p["label"])}</text>'
        dot = f'<circle cx="{px}" cy="{py:.1f}" r="5.5" class="pk pk-{p["mom"]}"/>'
        inner = f"{dot}{lab}"
        if p.get("href") and not deco:
            hw = 40 * k
            data = ""
            if p.get("thread"):
                data = (f' data-thread="{e(p["thread"])}" data-h="{e(p.get("headline", ""))}"'
                        f' data-l="{e(p.get("title", ""))}" data-m="{e(p["mom"])}"')
            inner = (f'<a href="{e(p["href"])}" class="tk"{data}><title>{e(p.get("title", p["label"]))}</title>'
                     f'<rect x="{px - hw:.0f}" y="0" width="{2 * hw:.0f}" height="{H}" class="hit"/>{inner}</a>')
        marks.append(inner)
    dividers = []
    for p in xs:
        if p.get("divider"):
            px = round(p["x"] * W - p.get("gapw", 0.03) * W)
            dividers.append(f'<line x1="{px}" y1="{top}" x2="{px}" y2="{base + 6}" class="div"/>'
                            f'<text x="{px + 6}" y="{top + 10}" class="dl">Frontiers</text>')
    a11y = 'aria-hidden="true" focusable="false"' if deco else f'role="img" aria-label="{e(aria)}"'
    return (f'<svg class="trace {cls}" viewBox="0 0 {W} {H}" {a11y}>'
            f'<g class="grid">{"".join(grid)}</g>{"".join(dividers)}'
            f'<path class="line" d="{d}" pathLength="1"/>'
            f'<g class="marks">{"".join(marks)}</g></svg>')


def edition_trace(ed, threads, prefix, mini=False):
    world = ed["stories"]
    ai = ed.get("frontiers", [])
    n = len(world) + len(ai)
    gap = 0.6 if ai else 0
    slots = n + gap
    pts = []
    for i, s in enumerate(world + ai):
        pos = i + (gap if i >= len(world) else 0)
        x = 0.05 + 0.9 * (pos + 0.5) / slots
        t = threads[s["thread"]]
        pts.append({
            "x": x, "amp": CHANGE[s["change"]][1], "mom": s["momentum"],
            "label": t.get("short", t["title"]), "href": f"#{s['thread']}",
            "title": f'{t["title"]}: {CHANGE[s["change"]][0]}, {MOMENTUM[s["momentum"]].lower()}',
            "divider": bool(ai) and i == len(world), "gapw": 0.9 * (gap / 2 + 0.5) / slots,
            "thread": s["thread"], "headline": s["headline"],
        })
    aria = "Today's trace: one spike per story, taller for bigger changes."
    if mini:
        return trace_svg(pts, seed=ed["date"], aria="", W=2400, height=60, labels=False, cls="trace-mini")
    return (trace_svg(pts, seed=ed["date"], aria=aria, height=170, cls="trace-wide") +
            trace_svg(pts, seed=ed["date"], aria=aria, W=420, height=120, labels=False, cls="trace-narrow", deco=True))


# --------------------------------------------------------------------------- page shell

FONTS = ("https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800"
         "&family=Schibsted+Grotesk:wght@400..800&display=swap")

THEME_INIT = ("<script>try{var t=localStorage.getItem('signal-theme');"
              "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}</script>")
THEME_BUTTON = ('<button class="theme" type="button" aria-label="Switch between light and dark">'
                '<svg viewBox="0 0 24 24" aria-hidden="true" class="i-moon"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>'
                '<svg viewBox="0 0 24 24" aria-hidden="true" class="i-sun"><circle cx="12" cy="12" r="4"/>'
                '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
                '</button>')


def page(title, body, prefix, path, active="", description=DESCRIPTION, extra_head=""):
    full_title = f"{title} — {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME}: {TAGLINE.lower()}"
    canon = f"{SITE_URL}/{path}"
    nav = [("Today", "", "today"), ("Threads", "threads/", "threads"),
           ("Forecasts", "forecasts/", "forecasts"), ("Archive", "archive/", "archive"), ("How it works", "about/", "about")]
    nav_html = "".join(
        f'<a href="{prefix}{href}"{" aria-current=\"page\"" if key == active else ""}>{e(lbl)}</a>'
        for lbl, href, key in nav)
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canon)}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(canon)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#0D1626">
<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{prefix}feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{prefix}assets/style.css">
{THEME_INIT}
{extra_head}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="mast">
  <div class="wrap mast-in">
    <a class="brand" href="{prefix}" aria-label="{SITE_NAME}, today's edition">
      <svg viewBox="0 0 64 24" aria-hidden="true"><path d="M1 16 H18 L22 13 L26 20 L31 3 L36 22 L40 11 L44 16 H63" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>The Signal</span>
    </a>
    <div class="mast-r"><nav class="nav" aria-label="Sections">{nav_html}</nav>{THEME_BUTTON}</div>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <p class="foot-brand">The Signal</p>
    <p>Read <a href="{prefix}about/">how it works</a> or browse the <a href="{prefix}archive/">archive</a>.</p>
    <p class="small">Forecasts are our own estimates, not financial or betting advice.</p>
  </div>
</footer>
<script src="{prefix}assets/signal.js" defer></script>
</body>
</html>
"""


# --------------------------------------------------------------------------- edition page

def story_html(s, threads, prefix, ed_date, kind="world"):
    t = threads[s["thread"]]
    meta = (f'<div class="meta">{badges(s)}'
            f'<a class="thread" href="{prefix}threads/{t["id"]}/">{e(t["title"])}</a></div>')
    extra = ""
    if kind == "world":
        extra = (f'<div class="so"><div><h3>Why it matters</h3><p>{e(s["why"])}</p></div>'
                 f'<div><h3>What to watch</h3><p>{e(s["watch"])}</p></div></div>')
    else:
        extra = f'<div class="picture"><h3>This changes the picture because</h3><p>{e(s["picture"])}</p></div>'
    return (f'<article class="story story-{kind}" id="{e(s["thread"])}">{meta}'
            f'<h2>{e(s["headline"])}</h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="body">{paras(s["body"])}</div>{extra}{sources_block(s["sources"])}</article>')


def story_meta(s, threads, prefix):
    t = threads[s["thread"]]
    return (f'<div class="meta">{badges(s)}'
            f'<a class="thread" href="{prefix}threads/{t["id"]}/">{e(t["title"])}</a></div>')


def so_block(s):
    return (f'<div class="so"><div><h3>Why it matters</h3><p>{e(s["why"])}</p></div>'
            f'<div><h3>What to watch</h3><p>{e(s["watch"])}</p></div></div>')


def place_caption(s):
    pts = [p["name"] for p in s.get("places", {}).get("points", [])]
    return f'<figcaption>{e(", ".join(pts))}</figcaption>' if pts else ""


def story_lead(s, threads, prefix):
    m = maps.map_svg(s.get("places"), 560, 420, labels=True, cls="map-lead")
    fig = f'<figure class="lead-map">{m}{place_caption(s)}</figure>' if m else ""
    return (f'<article class="story story-lead{"" if m else " nomap"}" id="{e(s["thread"])}"><div class="lead-text">{story_meta(s, threads, prefix)}'
            f'<h2>{e(s["headline"])}</h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="body">{paras(s["body"])}</div>{so_block(s)}{sources_block(s["sources"])}</div>{fig}</article>')


def story_second(s, threads, prefix):
    m = maps.map_svg(s.get("places"), 520, 250, labels=True, cls="map-second")
    fig = f'<figure class="second-map">{m}</figure>' if m else ""
    return (f'<article class="story story-second" id="{e(s["thread"])}">{fig}{story_meta(s, threads, prefix)}'
            f'<h2>{e(s["headline"])}</h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="body">{paras(s["body"])}</div>{so_block(s)}{sources_block(s["sources"])}</article>')


def story_compact(s, threads, prefix):
    m = maps.map_svg(s.get("places"), 160, 160, labels=False, cls="map-thumb")
    thumb = f'<div class="thumb">{m}</div>' if m else ""
    return (f'<article class="story story-compact" id="{e(s["thread"])}">{thumb}<div class="c-text">'
            f'{story_meta(s, threads, prefix)}<h2>{e(s["headline"])}</h2><p class="dek">{e(s["dek"])}</p>'
            f'<details class="more-story"><summary>Read the full story</summary>'
            f'<div class="body">{paras(s["body"])}</div>{so_block(s)}{sources_block(s["sources"])}</details></div></article>')


def story_frontier(s, threads, prefix):
    t = threads[s["thread"]]
    meta = (f'<div class="meta"><span class="field field-{e(s["field"].lower())}">{e(s["field"])}</span>{badges(s)}'
            f'<a class="thread" href="{prefix}threads/{t["id"]}/">{e(t["title"])}</a></div>')
    return (f'<article class="story story-frontier" id="{e(s["thread"])}">{meta}'
            f'<h2>{e(s["headline"])}</h2>'
            f'<div class="picture"><h3>This changes the picture because</h3><p>{e(s["picture"])}</p></div>'
            f'<details class="more-story"><summary>Read more</summary><p class="dek">{e(s["dek"])}</p>'
            f'<div class="body">{paras(s["body"])}</div>{sources_block(s["sources"])}</details></article>')


def markets_strip(m):
    if not m:
        return ""
    cells = []
    for it in m["items"]:
        ch = it.get("change")
        if ch is None:
            delta = '<span class="mk-d">&nbsp;</span>'
        else:
            cls = "up" if ch > 0 else "down" if ch < 0 else "flat"
            sign = "+" if ch > 0 else "−" if ch < 0 else ""
            delta = f'<span class="mk-d mk-{cls}">{sign}{abs(ch):g}%</span>'
        approx = "≈" if it.get("approx") else ""
        cells.append(f'<li><span class="mk-n">{e(it["name"])}</span><span class="mk-v">{approx}{e(it["value"])}</span>{delta}</li>')
    return (f'<section class="markets" aria-label="Markets"><p class="mk-h">Markets, {e(m["label"])}</p>'
            f'<ul>{"".join(cells)}</ul>{sources_block(m.get("sources", []))}</section>')


def date_weight(ed):
    items = ed["stories"] + ed.get("frontiers", [])
    avg = sum(CHANGE[s["change"]][1] for s in items) / max(len(items), 1)
    return round(220 + 580 * min(max((avg - 0.18) / 0.82, 0), 1))


def forecast_rail(forecasts, ed_date, prefix):
    rows = []
    open_f = [f for f in forecasts if f["status"] == "open"]
    for f in open_f:
        hist = [h for h in f["history"] if h["date"] <= ed_date]
        if not hist:
            continue
        cur = hist[-1]["p"]
        prev = hist[-2]["p"] if len(hist) > 1 else None
        if prev is None:
            delta = '<span class="delta new">Opened</span>' if hist[-1]["date"] == ed_date else ""
        elif cur == prev:
            delta = '<span class="delta">No change</span>'
        else:
            sign = "up" if cur > prev else "down"
            delta = f'<span class="delta d-{sign}">{"+" if cur > prev else "−"}{abs(cur - prev)} from {prev}%</span>'
        rows.append(f'<li><a href="{prefix}forecasts/#{f["id"]}"><span class="fq">{e(f["question"])}</span>'
                    f'<span class="fp"><span class="pct">{cur}%</span>{delta}</span>'
                    f'<span class="bar" aria-hidden="true"><span style="width:{cur}%"></span></span></a></li>')
    return (f'<section class="rail-block" aria-labelledby="rf"><h2 id="rf">Forecasts</h2>'
            f'<p class="rail-note">Our running odds. Every change is logged with a reason.</p>'
            f'<ul class="flist">{"".join(rows)}</ul>'
            f'<a class="more" href="{prefix}forecasts/">All forecasts and the track record</a></section>')


def pulse_html(ed, threads, prefix):
    order = {r: i for i, r in enumerate(REGIONS)}
    items = []
    for p in sorted(ed["pulse"], key=lambda x: order[x["region"]]):
        links = " ".join(f'<a href="{prefix}threads/{tid}/">{e(threads[tid]["title"])}</a>' for tid in p.get("threads", []))
        src = sources_block(p.get("sources", []))
        items.append(f'<li class="pulse-{p["status"]}"><h3>{e(p["region"])}</h3><p>{e(p["text"])}</p>'
                     f'{f"<p class=pl>{links}</p>" if links else ""}{src}</li>')
    return (f'<section class="pulse" aria-labelledby="wp"><h2 id="wp">World pulse</h2>'
            f'<p class="rail-note">Every region, every day, even when the answer is nothing.</p>'
            f'<ul>{"".join(items)}</ul></section>')


def edition_body(ed, threads, forecasts, prefix, is_today, prev_ed, next_ed):
    nav = []
    if prev_ed:
        nav.append(f'<a href="{prefix}editions/{prev_ed["date"]}/">Previous edition, {e(day_month(prev_ed["date"]))}</a>')
    if next_ed:
        nav.append(f'<a href="{prefix}editions/{next_ed["date"]}/">Next edition, {e(day_month(next_ed["date"]))}</a>')
    elif not is_today:
        nav.append(f'<a href="{prefix}">Today\'s edition</a>')
    st = ed["stories"]
    lead = story_lead(st[0], threads, prefix)
    second = "".join(story_second(x, threads, prefix) for x in st[1:3])
    rest = "".join(story_compact(x, threads, prefix) for x in st[3:])
    fronts = "".join(story_frontier(s, threads, prefix) for s in ed.get("frontiers", []))
    fnote = (f'<div class="f-note"><p>{e(ed["frontier_note"])}</p>{sources_block(ed.get("frontier_note_sources", []))}</div>'
             if ed.get("frontier_note") else "")
    note = f'<p class="launch">{e(ed["launch_note"])}</p>' if ed.get("launch_note") else ""
    corr = ""
    if ed.get("corrections"):
        corr = ('<section class="corrections"><h2>Corrections</h2><ul>' +
                "".join(f'<li><strong>{e(short_date(c["date"]))}.</strong> {e(c["text"])}</li>' for c in ed["corrections"]) +
                "</ul></section>")
    counts = {}
    for s in ed["stories"] + ed.get("frontiers", []):
        counts[s["change"]] = counts.get(s["change"], 0) + 1
    summary = ", ".join(f'{n} {CHANGE[k][0].lower()}' for k, n in sorted(counts.items(), key=lambda kv: -CHANGE[kv[0]][1]))
    d = pdate(ed["date"])
    wgt = date_weight(ed)
    return f"""
<section class="hero hero-ed">
  <div class="wrap">
    <div class="dateline">
      <h1 class="bigdate" style="--w:{wgt}"><span class="sr">The Signal, </span><span class="dow">{e(d.strftime("%A"))}</span><span class="dm">{d.day} {e(d.strftime("%B"))}</span></h1>
      <div class="ed-meta">
        <p>Edition {ed.get("number", "")}, {d.year}</p>
        <p>{len(ed["stories"])} world stories, {len(ed.get("frontiers", []))} from the frontiers: {e(summary)}.</p>
        <p class="wkey">The date's weight tracks the day: light when little changed, heavy when a lot did.</p>
      </div>
    </div>
    <figure class="trace-fig">
      <div class="trace-box">{edition_trace(ed, threads, prefix)}<div class="tip" role="status" hidden></div></div>
      <figcaption>One spike per story. Height shows how much our picture changed; the dot shows whether the situation is <span class="k k-up">intensifying</span>, <span class="k k-steady">holding</span> or <span class="k k-down">easing</span>.</figcaption>
    </figure>
    {markets_strip(ed.get("markets"))}
    <div class="lede-row"><p class="lede">{e(ed["lede"])}</p>{note}</div>
  </div>
</section>
<div class="mini-bar" aria-hidden="true" inert><div class="wrap"><span class="mini-date">{d.day} {e(d.strftime("%b"))}</span>{edition_trace(ed, threads, prefix, mini=True)}</div></div>
<div class="wrap">
  <section aria-label="Top story" class="lead-wrap">{lead}</section>
  <section aria-label="Also major today" class="second-wrap">{second}</section>
</div>
<div class="wrap layout">
  <div class="col-main">
    <h2 class="sec-h">More that changed</h2>
    <section aria-label="More world stories" class="stories">{rest}</section>
  </div>
  <aside class="col-rail">
    {forecast_rail(forecasts, ed["date"], prefix)}
    {pulse_html(ed, threads, prefix)}
  </aside>
</div>
<section class="ai-band" aria-labelledby="ai-h">
  <div class="wrap">
    <header class="ai-head">
      <h2 id="ai-h">Frontiers</h2>
      <p>AI, science, medicine, space and energy: only what could change where the future is heading.</p>
    </header>
    <div class="f-grid">{fronts}</div>
    {fnote}
  </div>
</section>
<div class="wrap">{corr}<nav class="ed-nav" aria-label="Editions">{"".join(nav)}</nav></div>
"""


# --------------------------------------------------------------------------- threads

def thread_entries(threads, editions):
    out = {tid: [] for tid in threads}
    for ed in editions:
        for kind in ("stories", "frontiers"):
            for s in ed.get(kind, []):
                out[s["thread"]].append((ed["date"], s))
    return out


def thread_trace(entries, seed):
    if not entries:
        return ""
    dates = [pdate(d) for d, _ in entries]
    lo, hi = min(dates), max(dates)
    span = max((hi - lo).days, 6)
    pts = []
    for d, s in entries:
        x = 0.06 + 0.88 * ((pdate(d) - lo).days / span)
        pts.append({"x": x, "amp": CHANGE[s["change"]][1], "mom": s["momentum"],
                    "label": day_month(d), "href": f"#e-{d}", "title": s["headline"]})
    aria = "This thread's trace over time."
    return (trace_svg(pts, seed=seed, aria=aria, height=150, cls="trace-wide") +
            trace_svg(pts, seed=seed, aria=aria, W=420, height=110, labels=False, cls="trace-narrow"))


def thread_page(t, entries, forecasts, prefix):
    rel_f = [f for f in forecasts if t["id"] in f.get("threads", [])]
    latest = entries[-1][1] if entries else None
    status = ""
    if latest:
        status = f'<div class="meta">{badges(latest)}<span class="asof">as of {e(short_date(entries[-1][0]))}</span></div>'
    tl = []
    for d, s in reversed(entries):
        tl.append(f'<li id="e-{d}"><div class="tl-date"><a href="{prefix}editions/{d}/#{t["id"]}">{e(long_date(d))}</a></div>'
                  f'<div class="tl-body"><div class="meta">{badges(s)}</div><h3>{e(s["headline"])}</h3>'
                  f'<p class="dek">{e(s["dek"])}</p>{paras(s["body"])}'
                  + (f'<p class="wm"><strong>Why it matters.</strong> {e(s["why"])}</p>' if s.get("why") else "")
                  + (f'<p class="wm"><strong>This changes the picture because</strong> {e(s["picture"])}</p>' if s.get("picture") else "")
                  + f'{sources_block(s["sources"])}</div></li>')
    bg = ""
    if t.get("background"):
        bg = ('<section class="bg"><h2>Before we started following</h2><ul>' +
              "".join(f'<li><span>{e(flex_date(b["date"]))}</span>{e(b["text"])}</li>' for b in t["background"]) +
              "</ul></section>")
    fhtml = ""
    if rel_f:
        fhtml = ('<section class="rail-block"><h2>Related forecasts</h2><ul class="flist">' +
                 "".join(f'<li><a href="{prefix}forecasts/#{f["id"]}"><span class="fq">{e(f["question"])}</span>'
                         f'<span class="fp"><span class="pct">{f["history"][-1]["p"]}%</span></span>'
                         f'<span class="bar" aria-hidden="true"><span style="width:{f["history"][-1]["p"]}%"></span></span></a></li>'
                         for f in rel_f) + "</ul></section>")
    return f"""
<section class="hero hero-thread">
  <div class="wrap">
    <p class="crumb"><a href="{prefix}threads/">Threads</a> / {e(t["region"])}</p>
    <h1 class="thread-title">{e(t["title"])}</h1>
    <p class="lede">{e(t["summary"])}</p>
    {status}
    <p class="since">{e(t["started_label"])}. {len(entries)} {"update" if len(entries) == 1 else "updates"} in The Signal.</p>
    <figure class="trace-fig trace-small">{thread_trace(entries, t["id"])}</figure>
  </div>
</section>
<div class="wrap layout">
  <div class="col-main"><ol class="timeline">{"".join(tl)}</ol>{bg}</div>
  <aside class="col-rail">{fhtml}</aside>
</div>
"""


def threads_index(threads, entries, prefix):
    groups = {}
    for t in threads.values():
        groups.setdefault(t["region"], []).append(t)
    order = REGIONS + ["Frontiers"]
    secs = []
    for region in order:
        ts = groups.get(region, [])
        if not ts:
            continue
        ts.sort(key=lambda t: entries[t["id"]][-1][0] if entries[t["id"]] else "", reverse=True)
        lis = []
        for t in ts:
            en = entries[t["id"]]
            last = en[-1] if en else None
            lis.append(f'<li><a href="{prefix}threads/{t["id"]}/"><span class="tt">{e(t["title"])}</span>'
                       + (f'<span class="meta">{badges(last[1])}<span class="asof">{e(day_month(last[0]))}</span></span>' if last else "")
                       + f'<span class="ts">{e(t["summary"])}</span></a></li>')
        secs.append(f'<section class="tgroup"><h2>{e(region)}</h2><ul>{"".join(lis)}</ul></section>')
    return f"""
<section class="hero hero-plain"><div class="wrap">
  <h1 class="page-title">Threads</h1>
  <p class="lede">Every story we cover belongs to a thread: a situation we keep following until it stops changing. Each thread page shows its full timeline.</p>
</div></section>
<div class="wrap tgrid">{"".join(secs)}</div>
"""


# --------------------------------------------------------------------------- forecasts

def sparkline(hist, closes):
    W, H = 220, 56
    if not hist:
        return ""
    d0 = pdate(hist[0]["date"])
    d1 = max(pdate(closes), pdate(hist[-1]["date"]) + dt.timedelta(days=1))
    span = max((d1 - d0).days, 1)
    pts = []
    for h in hist:
        x = 4 + (W - 8) * ((pdate(h["date"]) - d0).days / span)
        y = H - 4 - (H - 8) * h["p"] / 100
        pts.append((x, y))
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
    # step line to today
    lx, ly = pts[-1]
    mid = f'<line x1="4" y1="{H/2}" x2="{W-4}" y2="{H/2}" class="mid"/>'
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" aria-hidden="true">{mid}'
            f'<path d="{line}" class="sl"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" class="sd"/></svg>')


def forecasts_page(forecasts, threads, prefix):
    open_f = [f for f in forecasts if f["status"] == "open"]
    done = [f for f in forecasts if f["status"] == "resolved" and f.get("resolution") in ("yes", "no")]
    cards = []
    for f in sorted(open_f, key=lambda f: f["closes"]):
        cur = f["history"][-1]["p"]
        ledger = "".join(f'<tr><td>{e(short_date(h["date"]))}</td><td class="num">{h["p"]}%</td><td>{e(h["note"])}</td></tr>'
                         for h in reversed(f["history"]))
        tl = ", ".join(f'<a href="{prefix}threads/{tid}/">{e(threads[tid]["title"])}</a>' for tid in f.get("threads", []))
        cards.append(f"""
<article class="fc" id="{e(f['id'])}">
  <div class="fc-top">
    <div><p class="fc-cat">{e(f['category'])}, closes {e(short_date(f['closes']))}</p><h2>{e(f['question'])}</h2></div>
    <div class="fc-num"><span class="pct">{cur}%</span>{sparkline(f['history'], f['closes']) if len(f['history']) > 1 else f'<span class="opened">Opened {e(short_date(f["opened"]))}</span>'}</div>
  </div>
  <p class="crit"><strong>How it resolves.</strong> {e(f['criteria'])}</p>
  <details class="ledger"><summary>Ledger ({len(f['history'])} {'entry' if len(f['history']) == 1 else 'entries'})</summary>
  <table><thead><tr><th scope="col">Date</th><th scope="col">Odds</th><th scope="col">Why</th></tr></thead><tbody>{ledger}</tbody></table></details>
  {f'<p class="fc-threads">Thread: {tl}</p>' if tl else ''}
</article>""")
    if done:
        brier = sum(((f["history"][-1]["p"] / 100) - (1 if f["resolution"] == "yes" else 0)) ** 2 for f in done) / len(done)
        rows = "".join(f'<tr><td>{e(f["question"])}</td><td class="num">{f["history"][-1]["p"]}%</td>'
                       f'<td>{"Yes" if f["resolution"] == "yes" else "No"}</td></tr>' for f in done)
        record = (f'<p>{len(done)} resolved. Average Brier score <strong>{brier:.3f}</strong> '
                  f'(0 is perfect; always guessing 50% scores 0.25).</p>'
                  f'<table><thead><tr><th scope="col">Question</th><th scope="col">Final odds</th><th scope="col">Outcome</th></tr></thead><tbody>{rows}</tbody></table>')
    else:
        first = min(open_f, key=lambda f: f["closes"]) if open_f else None
        record = ("<p>No forecasts have resolved yet." +
                  (f' The first closes on {e(short_date(first["closes"]))}.' if first else "") +
                  " Once they do, this section scores every one, including the misses.</p>")
    return f"""
<section class="hero hero-plain"><div class="wrap">
  <h1 class="page-title">Forecasts</h1>
  <p class="lede">A small set of questions with precise answers, updated each morning when the evidence moves. Old numbers are never edited; every change is logged with its reason.</p>
</div></section>
<div class="wrap fwrap">
  <div class="fcs">{"".join(cards)}</div>
  <section class="record" aria-labelledby="tr"><h2 id="tr">Track record</h2>{record}</section>
</div>
"""


# --------------------------------------------------------------------------- archive / about

def archive_page(editions, prefix):
    rows = []
    for ed in reversed(editions):
        heads = "".join(f"<li>{e(s['headline'])}</li>" for s in ed["stories"][:3])
        rows.append(f'<li><a href="{prefix}editions/{ed["date"]}/"><span class="ad">{e(long_date(ed["date"]))}</span>'
                    f'<span class="an">Edition {ed.get("number", "")}</span></a><ul class="ah">{heads}</ul></li>')
    return f"""
<section class="hero hero-plain"><div class="wrap">
  <h1 class="page-title">Archive</h1>
  <p class="lede">Every edition, kept as published. Corrections are added at the bottom of the edition they fix.</p>
</div></section>
<div class="wrap"><ol class="archive">{"".join(rows)}</ol></div>
"""


def about_page(prefix):
    rows = "".join(f'<tr><th scope="row"><span class="chg chg-{k}">{e(v[0])}</span></th><td>{e(d)}</td></tr>' for k, v, d in [
        ("major", CHANGE["major"], "Our understanding of the situation changed substantially today."),
        ("new", CHANGE["new"], "A situation that matters and that we were not following yesterday."),
        ("developing", CHANGE["developing"], "Real movement, but in the direction we already expected."),
        ("quiet", CHANGE["quiet"], "Still important, little changed. Usually left out of the edition."),
    ])
    return f"""
<section class="hero hero-plain"><div class="wrap">
  <h1 class="page-title">How it works</h1>
  <p class="lede">The Signal is a once-a-day briefing that asks one question: what changed in the world today that changes our picture of it?</p>
</div></section>
<div class="wrap prose">
  <h2>One edition a day, and then it stops</h2>
  <p>There is no feed and no breaking-news banner. Each morning we publish around ten world stories, a short Frontiers section on AI and science and a pulse check on every region. If nothing important happened somewhere, we say so.</p>
  <h2>Stories belong to threads</h2>
  <p>A thread is a situation we keep following: an election, a war, an outbreak. Each day's story is the latest entry in its thread, so you can see how a situation got here. Thread pages keep the whole timeline.</p>
  <h2>Change and momentum</h2>
  <p>Every story carries two labels. Change says how much today's news altered the picture:</p>
  <table class="rubric"><tbody>{rows}</tbody></table>
  <p>Momentum says which way the situation is moving: <span class="mom mom-up">{momentum_icon("up")}Intensifying</span>, <span class="mom mom-steady">{momentum_icon("steady")}Holding</span> or <span class="mom mom-down">{momentum_icon("down")}Easing</span>. We use words rather than scores on purpose; a score like 7.8 implies a precision nobody has.</p>
  <h2>Forecasts</h2>
  <p>We keep a small set of questions with exact resolution rules and give our odds. When evidence moves, the odds move, with the reason logged. Past numbers are never edited, and when a question resolves it is scored, so you can judge whether we are any good.</p>
</div>
"""


# --------------------------------------------------------------------------- feeds

def feed_xml(editions):
    items = []
    for ed in reversed(editions[-30:]):
        url = f"{SITE_URL}/editions/{ed['date']}/"
        body = "<p>" + e(ed["lede"]) + "</p><ul>" + "".join(f"<li>{e(s['headline'])}</li>" for s in ed["stories"]) + "</ul>"
        pub = dt.datetime.fromisoformat(ed.get("published_at", ed["date"] + "T12:00:00+00:00"))
        items.append(f"<item><title>{e(long_date(ed['date']))}</title><link>{url}</link><guid>{url}</guid>"
                     f"<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
                     f"<description>{e(body)}</description></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{SITE_NAME}</title>'
            f"<link>{SITE_URL}/</link><description>{e(DESCRIPTION)}</description><language>en</language>"
            f'{"".join(items)}</channel></rss>\n')


def sitemap(paths):
    urls = "".join(f"<url><loc>{SITE_URL}/{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


# --------------------------------------------------------------------------- build

def write(path, text):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build():
    threads, editions, forecasts = load()
    validate(threads, editions, forecasts)
    if "--check" in sys.argv:
        print(f"OK: {len(editions)} editions, {len(threads)} threads, {len(forecasts)} forecasts")
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "assets").mkdir()
    for f in SRC.iterdir():
        shutil.copy(f, OUT / "assets" / f.name)
    (OUT / ".nojekyll").write_text("")
    paths = [""]
    latest = editions[-1]
    for i, ed in enumerate(editions):
        prev_ed = editions[i - 1] if i > 0 else None
        next_ed = editions[i + 1] if i + 1 < len(editions) else None
        body = edition_body(ed, threads, forecasts, "../../", False, prev_ed, next_ed)
        write(f"editions/{ed['date']}/index.html",
              page(long_date(ed["date"]), body, "../../", f"editions/{ed['date']}/", active="archive",
                   description=ed["lede"][:300]))
        paths.append(f"editions/{ed['date']}/")
    body = edition_body(latest, threads, forecasts, "", True, editions[-2] if len(editions) > 1 else None, None)
    write("index.html", page(SITE_NAME, body, "", "", active="today"))
    entries = thread_entries(threads, editions)
    for t in threads.values():
        write(f"threads/{t['id']}/index.html",
              page(t["title"], thread_page(t, entries[t["id"]], forecasts, "../../"), "../../",
                   f"threads/{t['id']}/", active="threads", description=t["summary"]))
        paths.append(f"threads/{t['id']}/")
    write("threads/index.html", page("Threads", threads_index(threads, entries, "../"), "../", "threads/", active="threads"))
    write("forecasts/index.html", page("Forecasts", forecasts_page(forecasts, threads, "../"), "../", "forecasts/", active="forecasts",
                                       description="Running odds on the questions that matter, with every change logged and every result scored."))
    write("archive/index.html", page("Archive", archive_page(editions, "../"), "../", "archive/", active="archive"))
    write("about/index.html", page("How it works", about_page("../"), "../", "about/", active="about"))
    write("404.html", page("Not found", '<section class="hero hero-plain"><div class="wrap"><h1 class="page-title">Nothing here</h1>'
                            f'<p class="lede">That page does not exist. <a href="{SITE_URL}/">Go to today\'s edition</a>.</p></div></section>',
                            f"{SITE_URL}/", "404.html"))
    paths += ["threads/", "forecasts/", "archive/", "about/"]
    write("feed.xml", feed_xml(editions))
    write("sitemap.xml", sitemap(paths))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"Built {len(editions)} editions, {len(threads)} threads, {len(forecasts)} forecasts into docs/")


if __name__ == "__main__":
    try:
        build()
    except BuildError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
