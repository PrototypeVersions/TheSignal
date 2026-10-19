#!/usr/bin/env python3
"""Build The Signal's static site from the JSON in /data into /docs.

Standard library only, so the daily run needs no installs.
Usage: python3 scripts/build.py          (validate + build)
       python3 scripts/build.py --check  (validate only)
"""
import datetime as dt
import html
import json
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
DESCRIPTION = ("A daily briefing on the handful of developments that changed the picture today, "
               "with maps, full reports and sources.")

CHANGE = {
    "major": ("Major shift", 1.0),
    "new": ("New", 0.78),
    "developing": ("Developing", 0.5),
    "quiet": ("Quiet", 0.18),
}
MOMENTUM = {"up": "Intensifying", "steady": "Holding", "down": "Easing"}
FIELDS = ["AI", "Science", "Medicine", "Space", "Energy", "Climate"]
REGIONS = ["North America", "Latin America", "Europe", "Africa", "Middle East", "Asia", "Oceania"]
# where each region's numbered marker sits on the world map (lon, lat)
REGION_PINS = {
    "North America": (-101, 47), "Latin America": (-62, -12), "Europe": (15, 51), "Africa": (20, 4),
    "Middle East": (47, 28), "Asia": (97, 40), "Oceania": (140, -25),
}
# editions from this date on must carry a full report for every story
FULL_REPORTS_FROM = "2026-10-19"

e = html.escape


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


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
    return threads, editions


def validate(threads, editions):
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
        strict = d >= FULL_REPORTS_FROM
        if not date_re.match(d):
            errs.append(f"edition {d}: bad date")
        if d in seen:
            errs.append(f"edition {d}: duplicate date")
        seen.add(d)
        if not ed.get("lede"):
            errs.append(f"edition {d}: missing lede")
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
                need = ["headline", "dek", "sources"] + (["why", "watch"] if group == "stories" else ["picture"])
                if group == "frontiers" and s.get("field") not in FIELDS:
                    errs.append(f"{where}: field must be one of {FIELDS}")
                for k in need:
                    if not s.get(k):
                        errs.append(f"{where}: missing '{k}'")
                if not s.get("report") and not s.get("body"):
                    errs.append(f"{where}: needs a 'report' (the full story)")
                if strict and not s.get("report"):
                    errs.append(f"{where}: needs a 'report' (two to five sections of the full story)")
                if strict and not s.get("key_facts"):
                    errs.append(f"{where}: needs 'key_facts' (three to five short facts)")
                errs += check_report(s, where)
                img = s.get("image")
                if img:
                    asset = str(img.get("asset", ""))
                    if not re.fullmatch(r"images/\d{4}-\d{2}-\d{2}/[a-z0-9-]+\.(svg|png|jpg|jpeg|webp)", asset) or not (ROOT / asset).is_file():
                        errs.append(f"{where}: image asset must be an existing file under images/YYYY-MM-DD/ ({asset})")
                    if not img.get("alt"):
                        errs.append(f"{where}: image needs alt text")
                if "body" in s and not isinstance(s["body"], list):
                    errs.append(f"{where}: body must be a list of paragraphs")
                errs += check_sources(s.get("sources", []), where)
                errs += maps.validate_places(s.get("places"), where)
                errs += check_updates(s, where)
        errs += check_markets(ed.get("markets"), f"edition {d} markets")
        if ed.get("updated_at"):
            try:
                dt.datetime.fromisoformat(ed["updated_at"])
            except ValueError:
                errs.append(f"edition {d}: updated_at must be an ISO time")
        errs += check_sources(ed.get("frontier_note_sources", []), f"edition {d} frontier_note", allow_empty=True)
        if len(ed.get("stories", [])) < 3:
            errs.append(f"edition {d}: needs at least 3 stories")
        regions = [p.get("region") for p in ed.get("pulse", [])]
        if sorted(regions) != sorted(REGIONS):
            errs.append(f"edition {d}: pulse must cover exactly {REGIONS}")
        for p in ed.get("pulse", []):
            where = f"edition {d} pulse {p.get('region')}"
            for tid in p.get("threads", []):
                if tid not in threads:
                    errs.append(f"{where}: unknown thread '{tid}'")
            errs += check_sources(p.get("sources", []), where, allow_empty=True)
            for b in p.get("briefs", []):
                if not b.get("headline") or not b.get("text"):
                    errs.append(f"{where}: each brief needs a headline and text")
                errs += check_sources(b.get("sources", []), f"{where} brief")
    if errs:
        raise BuildError("Validation failed:\n  - " + "\n  - ".join(errs))


def check_report(s, where):
    errs = []
    kf = s.get("key_facts")
    if kf is not None and (not isinstance(kf, list) or not 2 <= len(kf) <= 6 or not all(isinstance(x, str) and x.strip() for x in kf)):
        errs.append(f"{where}: key_facts must be a list of 2 to 6 short sentences")
    rep = s.get("report")
    if rep is not None:
        if not isinstance(rep, list) or not rep:
            errs.append(f"{where}: report must be a list of sections")
        else:
            for sec in rep:
                if not sec.get("heading") or not isinstance(sec.get("paragraphs"), list) or not sec["paragraphs"]:
                    errs.append(f"{where}: each report section needs a heading and a list of paragraphs")
    return errs


def check_updates(s, where):
    errs = []
    for u in s.get("updates", []):
        if not u.get("text") or not u.get("at"):
            errs.append(f"{where}: each update needs 'at' (ISO time) and 'text'")
        else:
            try:
                dt.datetime.fromisoformat(u["at"])
            except ValueError:
                errs.append(f"{where}: update 'at' must be an ISO time like 2026-10-18T17:55:00-05:00")
        errs += check_sources(u.get("sources", []), where, allow_empty=True)
    return errs


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
        return dt.date.fromisoformat(s + "-01").strftime("%B %Y")
    return short_date(s)


def clock(iso):
    t = dt.datetime.fromisoformat(iso)
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'} CT"


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


def sources_list(sources):
    items = "".join(
        f'<li><a href="{e(s["url"])}" rel="noopener" target="_blank">{e(s["title"])}</a>'
        f'<span class="outlet">{e(s["outlet"])}</span></li>' for s in sources)
    return f'<ul class="src-list">{items}</ul>'


def paras(body):
    return "".join(f"<p>{e(p)}</p>" for p in body)


def story_url(ed_date, s, prefix):
    return f'{prefix}editions/{ed_date}/{s["thread"]}/'


def updated_tag(s, url):
    ups = s.get("updates", [])
    if not ups:
        return ""
    return f'<a class="up-tag" href="{url}#updates">Updated {e(clock(ups[-1]["at"]))}</a>'


def story_meta(s, threads, prefix, field=False):
    t = threads[s["thread"]]
    f = f'<span class="field field-{e(s["field"].lower())}">{e(s["field"])}</span>' if field and s.get("field") else ""
    return (f'<div class="meta">{f}{badges(s)}'
            f'<a class="thread" href="{prefix}threads/{t["id"]}/">{e(t["title"])}</a></div>')


def place_caption(s):
    pts = [p["name"] for p in s.get("places", {}).get("points", [])]
    return f'<figcaption>{e(", ".join(pts))}</figcaption>' if pts else ""


# --------------------------------------------------------------------------- page shell

FONTS = ("https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800"
         "&family=Schibsted+Grotesk:wght@400..800&family=DM+Sans:wght@400;500&display=swap")


def page(title, body, prefix, path, active="", description=DESCRIPTION):
    full_title = f"{title} — {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME}: {TAGLINE.lower()}"
    canon = f"{SITE_URL}/{path}"
    nav = [("Today", "", "today"), ("Regions", "#regions", "regions"), ("Threads", "threads/", "threads"),
           ("Archive", "archive/", "archive"), ("How it works", "about/", "about")]
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
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="mast">
  <div class="wrap mast-in">
    <a class="brand" href="{prefix}" aria-label="{SITE_NAME}, today's edition">
      <svg viewBox="0 0 64 24" aria-hidden="true"><path d="M1 16 H18 L22 13 L26 20 L31 3 L36 22 L40 11 L44 16 H63" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>The Signal</span>
    </a>
    <div class="mast-r"><nav class="nav" aria-label="Sections">{nav_html}</nav></div>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <p class="foot-brand">The Signal</p>
    <p>Read <a href="{prefix}about/">how it works</a> or browse the <a href="{prefix}archive/">archive</a>.</p>
  </div>
</footer>
<script src="{prefix}assets/signal.js" defer></script>
</body>
</html>
"""


# --------------------------------------------------------------------------- front page

def report_button(url, label="Full report"):
    return f'<a class="report-btn" href="{url}">{e(label)} <span aria-hidden="true">→</span></a>'


def story_lead(s, threads, prefix, ed_date):
    url = story_url(ed_date, s, prefix)
    m = maps.map_svg(s.get("places"), 560, 420, labels=True, cls="map-lead")
    fig = f'<figure class="lead-map">{m}{place_caption(s)}</figure>' if m else ""
    return (f'<article class="story story-lead{"" if m else " nomap"}" id="{e(s["thread"])}"><div class="lead-text">'
            f'{story_meta(s, threads, prefix)}<h2><a href="{url}">{e(s["headline"])}</a></h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="why"><h3>Why it matters</h3><p>{e(s["why"])}</p></div>'
            f'<div class="actions">{report_button(url)}{updated_tag(s, url)}</div></div>{fig}</article>')


def story_second(s, threads, prefix, ed_date):
    url = story_url(ed_date, s, prefix)
    m = maps.map_svg(s.get("places"), 520, 250, labels=True, cls="map-second")
    fig = f'<figure class="second-map"><a href="{url}" tabindex="-1" aria-hidden="true">{m}</a></figure>' if m else ""
    return (f'<article class="story story-second" id="{e(s["thread"])}">{fig}{story_meta(s, threads, prefix)}'
            f'<h2><a href="{url}">{e(s["headline"])}</a></h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="actions">{report_button(url)}{updated_tag(s, url)}</div></article>')


def story_art(s, prefix, url=None):
    img = s.get("image")
    if not img:
        return ""
    tag = f'<img src="{prefix}{e(img["asset"])}" alt="{e(img["alt"])}" width="1200" height="800" loading="lazy" decoding="async">'
    if url:
        tag = f'<a href="{url}" tabindex="-1" aria-hidden="true">{tag}</a>'
    return f'<figure class="f-art">{tag}<figcaption>{e(img.get("credit", "Illustration"))}</figcaption></figure>'


def story_compact(s, threads, prefix, ed_date, frontier=False):
    url = story_url(ed_date, s, prefix)
    thumb = story_art(s, prefix, url) if frontier else ""
    if not frontier:
        m = maps.map_svg(s.get("places"), 160, 160, labels=False, cls="map-thumb")
        thumb = f'<a class="thumb" href="{url}" tabindex="-1" aria-hidden="true">{m}</a>' if m else ""
    return (f'<article class="story story-compact{" story-frontier" if frontier else ""}" id="{e(s["thread"])}">{thumb}<div class="c-text">'
            f'{story_meta(s, threads, prefix, field=frontier)}<h2><a href="{url}">{e(s["headline"])}</a></h2><p class="dek">{e(s["dek"])}</p>'
            f'<div class="actions"><a class="read-full" href="{url}">Read the full story <span aria-hidden="true">→</span></a>{updated_tag(s, url)}</div></div></article>')


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


def glance_bar(ed):
    """An at-a-glance instrument strip: what kind of day it was."""
    allst = ed["stories"] + ed.get("frontiers", [])
    n = len(allst) or 1

    def meter(parts):
        segs = "".join(f'<span class="gl-seg gl-{k}" style="width:{100 * v / n:.1f}%"></span>' for k, v in parts if v)
        return f'<span class="gl-meter" aria-hidden="true">{segs}</span>'

    ch = {k: sum(1 for s in allst if s["change"] == k) for k in CHANGE}
    mo = {k: sum(1 for s in allst if s["momentum"] == k) for k in MOMENTUM}
    moved = sum(1 for p in ed.get("pulse", []) if p.get("status") == "moved")
    words = len(ed["lede"].split()) + sum(len(s["dek"].split()) + len(s["headline"].split()) for s in allst)
    full = sum(len(x.split()) for s in allst for sec in s.get("report", []) for x in sec["paragraphs"]) or \
        sum(len(x.split()) for s in allst for x in s.get("body", []))
    when = clock(ed["updated_at"]) if ed.get("updated_at") else clock(ed["published_at"]) if ed.get("published_at") else ""
    change_txt = " · ".join(f"{v} {CHANGE[k][0].lower()}" for k, v in ch.items() if v)
    cells = [
        ("Today", f'{len(ed["stories"]) + len(ed.get("frontiers", []))} stories', f'{len(ed["stories"])} world · {len(ed.get("frontiers", []))} from the frontiers'),
        ("How much changed", meter([(k, v) for k, v in ch.items()]), change_txt),
        ("Direction", meter([("up", mo["up"]), ("steady", mo["steady"]), ("down", mo["down"])]),
         " · ".join(f'<span class="k-{k}">{mo[k]} {lbl}</span>' for k, lbl in (("up", "intensifying"), ("steady", "holding"), ("down", "easing")) if mo[k])),
        ("Regions", f'{moved} of {len(REGIONS)} moved', '<a href="#regions">See the map ↓</a>'),
        ("Reading time", f'≈ {max(1, round(words / 230))} min', f'≈ {max(1, round(full / 230))} min with every full report'),
    ]
    if when:
        cells.append(("Updated" if ed.get("updated_at") else "Published", when, "Updated again each evening" if not ed.get("updated_at") else "Evening update included"))
    lis = "".join(f'<li><span class="gl-k">{e(k)}</span><span class="gl-v">{v}</span><span class="gl-s">{s}</span></li>' for k, v, s in cells)
    return f'<section class="glance" aria-label="Today at a glance"><p class="gl-h">At a glance</p><ul>{lis}</ul></section>'


# --------------------------------------------------------------------------- regions

def region_items(ed, threads):
    """For each region: its pulse entry, the edition's stories that belong to it, and its extra briefs."""
    pulse = {p["region"]: p for p in ed.get("pulse", [])}
    out = []
    for n, region in enumerate(REGIONS, 1):
        p = pulse.get(region, {})
        linked = set(p.get("threads", []))
        stories = [s for s in ed["stories"] if threads[s["thread"]]["region"] == region or s["thread"] in linked]
        out.append({"name": region, "slug": slug(region), "n": n, "pulse": p, "stories": stories,
                    "briefs": p.get("briefs", [])})
    return out


def count_label(r):
    k = len(r["stories"]) + len(r["briefs"])
    return f'{k} item{"" if k == 1 else "s"}'


def region_panel(r, ed, prefix, base, active):
    stories = "".join(f'<li><a href="{story_url(ed["date"], s, prefix)}">{e(s["headline"])}</a></li>' for s in r["stories"]) \
        or f'<li class="empty">No {e(r["name"])} story made today’s edition.</li>'
    briefs = "".join(f'<li><a href="{base}regions/{r["slug"]}/#brief-{i}">{e(b["headline"])}'
                     f'<span class="outlet">{e(b["sources"][0]["outlet"])}</span></a></li>' for i, b in enumerate(r["briefs"], 1)) \
        or '<li class="empty">No further development cleared our bar today.</li>'
    summary = f'<p class="rp-sum">{e(r["pulse"].get("text", ""))}</p>' if r["pulse"].get("text") else ""
    return (f'<div class="reg-panel" id="region-panel-{r["slug"]}" data-panel="{r["slug"]}"{"" if active else " hidden"}>'
            f'<p class="rp-k">Region {r["n"]:02} · {count_label(r)}</p><h3>{e(r["name"])}</h3>{summary}'
            f'<h4>In today’s edition</h4><ul class="rp-list">{stories}</ul>'
            f'<h4>More from {e(r["name"])}</h4><ul class="rp-list rp-briefs">{briefs}</ul>'
            + report_button(base + "regions/" + r["slug"] + "/", "All " + r["name"] + " news") + '</div>')


def regions_section(ed, threads, prefix, base):
    regions = region_items(ed, threads)
    pins = ""
    for r in regions:
        x, y = maps.world_xy(*REGION_PINS[r["name"]])
        k = len(r["stories"]) + len(r["briefs"])
        pins += (f'<a href="{base}regions/{r["slug"]}/" class="rpin" data-region="{r["slug"]}" aria-label="{e(r["name"])}: {count_label(r)}">'
                 f'<circle class="halo" cx="{x:.1f}" cy="{y:.1f}" r="36"/><circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="25"/>'
                 f'<text x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle">{r["n"]:02}</text>'
                 f'<text class="rname" x="{x:.1f}" y="{y + 54:.1f}" text-anchor="middle">{e(r["name"])} · {k}</text></a>')
    chips = "".join(f'<a href="{base}regions/{r["slug"]}/" class="rchip" data-region="{r["slug"]}"><span>{r["n"]:02}</span>{e(r["name"])}'
                    f'<small>{len(r["stories"]) + len(r["briefs"])}</small></a>' for r in regions)
    panels = "".join(region_panel(r, ed, prefix, base, i == 0) for i, r in enumerate(regions))
    W, H = maps.WORLD_W, maps.WORLD_H
    return f"""
<section class="regions" id="regions" aria-labelledby="rg-h">
  <div class="wrap">
    <header class="sec-head"><h2 id="rg-h" class="sec-h">The world, by region</h2>
      <p class="sec-note">Every region, every day, even when the answer is nothing. Choose a region for its stories today, plus news that didn’t make the edition.</p></header>
    <div class="reg-layout">
      <div class="reg-map">
        <svg viewBox="0 -14 {W} {H + 28}" role="group" aria-label="World map with seven numbered regions">
          <image href="{prefix}assets/world.svg" width="{W}" height="{H}"/>{pins}
        </svg>
        <nav class="rchips" aria-label="Regions">{chips}</nav>
      </div>
      <aside class="reg-side" aria-live="polite">{panels}</aside>
    </div>
  </div>
</section>"""


def region_page(r, ed, threads, prefix, others):
    stories = "".join(
        f'<article class="rstory">{story_meta(s, threads, prefix)}<h3><a href="{story_url(ed["date"], s, prefix)}">{e(s["headline"])}</a></h3>'
        f'<p class="dek">{e(s["dek"])}</p><a class="read-full" href="{story_url(ed["date"], s, prefix)}">Read the full story <span aria-hidden="true">→</span></a></article>'
        for s in r["stories"]) or f'<p class="empty">No {e(r["name"])} story made this edition.</p>'
    briefs = "".join(
        f'<article class="rbrief" id="brief-{i}"><h3>{e(b["headline"])}</h3>{paras([b["text"]])}{sources_block(b["sources"])}</article>'
        for i, b in enumerate(r["briefs"], 1)) or '<p class="empty">No further development cleared our bar today.</p>'
    switch = "".join(f'<a href="../{o["slug"]}/"{" aria-current=\"page\"" if o["slug"] == r["slug"] else ""}><span>{o["n"]:02}</span>{e(o["name"])}</a>' for o in others)
    summary = f'<p class="lede">{e(r["pulse"].get("text", ""))}</p>' if r["pulse"].get("text") else ""
    return f"""
<section class="hero hero-plain"><div class="wrap narrow">
  <p class="crumb"><a href="{prefix}editions/{ed["date"]}/#regions">Edition {ed.get("number", "")}, {e(long_date(ed["date"]))}</a> / Region {r["n"]:02}</p>
  <h1 class="page-title">{e(r["name"])}</h1>
  {summary}
  <nav class="rswitch" aria-label="Other regions">{switch}</nav>
</div></section>
<div class="wrap narrow region-body">
  <h2 class="sec-h">In today’s edition</h2>{stories}
  <h2 class="sec-h">More from {e(r["name"])}</h2>
  <p class="sec-note">These developments did not make the main edition. Each is summarized from the linked reporting.</p>{briefs}
</div>
"""


# --------------------------------------------------------------------------- edition page

def edition_body(ed, threads, prefix, is_today, prev_ed, next_ed):
    nav = []
    if prev_ed:
        nav.append(f'<a href="{prefix}editions/{prev_ed["date"]}/">Previous edition, {e(day_month(prev_ed["date"]))}</a>')
    if next_ed:
        nav.append(f'<a href="{prefix}editions/{next_ed["date"]}/">Next edition, {e(day_month(next_ed["date"]))}</a>')
    elif not is_today:
        nav.append(f'<a href="{prefix}">Today\'s edition</a>')
    d = ed["date"]
    base = prefix if is_today else f"{prefix}editions/{d}/"
    st = ed["stories"]
    lead = story_lead(st[0], threads, prefix, d)
    second = "".join(story_second(x, threads, prefix, d) for x in st[1:3])
    rest = "".join(story_compact(x, threads, prefix, d) for x in st[3:])
    fronts = "".join(story_compact(s, threads, prefix, d, frontier=True) for s in ed.get("frontiers", []))
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
    dd = pdate(d)
    more = f"""
<div class="wrap more-wrap">
  <h2 class="sec-h">More that changed</h2>
  <section aria-label="More world stories" class="stories">{rest}</section>
</div>""" if rest else ""
    return f"""
<section class="hero hero-ed">
  <div class="wrap">
    <div class="dateline">
      <h1 class="bigdate"><span class="sr">The Signal, </span><span class="dow">{e(dd.strftime("%A"))}</span><span class="dm">{dd.day} {e(dd.strftime("%B"))}</span></h1>
      <div class="ed-meta">
        <p>Edition {ed.get("number", "")}, {dd.year}{f'. Updated {e(clock(ed["updated_at"]))}' if ed.get("updated_at") else ""}</p>
      </div>
    </div>
    {glance_bar(ed)}
    <div class="lede-row"><p class="lede">{e(ed["lede"])}</p>{note}</div>
  </div>
</section>
<div class="wrap">
  <section aria-label="Top story" class="lead-wrap">{lead}</section>
  <section aria-label="Also major today" class="second-wrap">{second}</section>
</div>
{more}
{regions_section(ed, threads, prefix, base)}
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


# --------------------------------------------------------------------------- story pages

def full_story(s):
    facts = ""
    if s.get("key_facts"):
        facts = ('<aside class="key-facts"><h2>Key facts</h2><ul>' +
                 "".join(f"<li>{e(x)}</li>" for x in s["key_facts"]) + "</ul></aside>")
    if s.get("report"):
        body = "".join(f'<h2>{e(sec["heading"])}</h2>{paras(sec["paragraphs"])}' for sec in s["report"])
    else:
        body = paras(s.get("body", []))
    return facts + f'<div class="report">{body}</div>'


def story_updates(s):
    ups = s.get("updates", [])
    if not ups:
        return ""
    items = "".join(f'<li><span class="up-t">Update, {e(clock(u["at"]))}</span><p>{e(u["text"])}</p>'
                    f'{sources_block(u.get("sources", []))}</li>' for u in ups)
    return f'<section class="story-updates" id="updates"><h2>Since this morning</h2><ul>{items}</ul></section>'


def story_page(s, ed, threads, entries, prefix, frontier=False):
    t = threads[s["thread"]]
    d = ed["date"]
    m = "" if frontier else maps.map_svg(s.get("places"), 760, 420, labels=True, cls="map-story")
    fig = f'<figure class="story-map">{m}{place_caption(s)}</figure>' if m else story_art(s, prefix)
    if frontier:
        assess = f'<section class="assess"><div><h2>Why it matters</h2><p>{e(s["picture"])}</p></div></section>'
    else:
        assess = (f'<section class="assess"><div><h2>Why it matters</h2><p>{e(s["why"])}</p></div>'
                  f'<div><h2>What to watch</h2><p>{e(s["watch"])}</p></div></section>')
    earlier = [(dd, x) for dd, x in entries if dd < d]
    hist = ""
    if earlier:
        rows = "".join(f'<li><a href="{prefix}editions/{dd}/{x["thread"]}/"><span class="hd">{e(long_date(dd))}</span>'
                       f'<span class="hh">{e(x["headline"])}</span></a></li>' for dd, x in reversed(earlier[-8:]))
        hist = (f'<section class="earlier"><h2>Earlier in this story</h2><ul>{rows}</ul>'
                f'<a class="read-full" href="{prefix}threads/{t["id"]}/">The whole timeline <span aria-hidden="true">→</span></a></section>')
    upd = f' · Updated {e(clock(s["updates"][-1]["at"]))}' if s.get("updates") else ""
    return f"""
<article class="story-page">
<section class="hero hero-plain"><div class="wrap narrow">
  <p class="crumb"><a href="{prefix}editions/{d}/#{e(s["thread"])}">Edition {ed.get("number", "")}, {e(long_date(d))}</a> / <a href="{prefix}threads/{t["id"]}/">{e(t["title"])}</a></p>
  {story_meta(s, threads, prefix, field=frontier)}
  <h1 class="story-title">{e(s["headline"])}</h1>
  <p class="lede">{e(s["dek"])}</p>
  <p class="byline">The Signal · {e(long_date(d))}{upd}</p>
</div></section>
<div class="wrap narrow story-body">
  {fig}{story_updates(s)}{full_story(s)}{assess}
  <section class="story-sources"><h2>Sources</h2>{sources_list(s["sources"])}</section>
  {hist}
  <p class="back"><a href="{prefix}editions/{d}/">← Back to the {e(day_month(d))} edition</a></p>
</div>
</article>
"""


# --------------------------------------------------------------------------- threads

def thread_entries(threads, editions):
    out = {tid: [] for tid in threads}
    for ed in editions:
        for kind in ("stories", "frontiers"):
            for s in ed.get(kind, []):
                out[s["thread"]].append((ed["date"], s))
    return out


def thread_page(t, entries, prefix):
    latest = entries[-1][1] if entries else None
    status = ""
    if latest:
        status = f'<div class="meta">{badges(latest)}<span class="asof">as of {e(short_date(entries[-1][0]))}</span></div>'
    tl = []
    for d, s in reversed(entries):
        url = f"{prefix}editions/{d}/{s['thread']}/"
        tl.append(f'<li id="e-{d}"><div class="tl-date"><a href="{prefix}editions/{d}/#{t["id"]}">{e(long_date(d))}</a></div>'
                  f'<div class="tl-body"><div class="meta">{badges(s)}</div><h3><a href="{url}">{e(s["headline"])}</a></h3>'
                  f'<p class="dek">{e(s["dek"])}</p>'
                  f'<div class="actions"><a class="read-full" href="{url}">Read the full story <span aria-hidden="true">→</span></a>{updated_tag(s, url)}</div></div></li>')
    bg = ""
    if t.get("background"):
        bg = ('<section class="bg"><h2>Before we started following</h2><ul>' +
              "".join(f'<li><span>{e(flex_date(b["date"]))}</span>{e(b["text"])}</li>' for b in t["background"]) +
              "</ul></section>")
    return f"""
<section class="hero hero-thread">
  <div class="wrap narrow">
    <p class="crumb"><a href="{prefix}threads/">Threads</a> / {e(t["region"])}</p>
    <h1 class="thread-title">{e(t["title"])}</h1>
    <p class="lede">{e(t["summary"])}</p>
    {status}
    <p class="since">{e(t["started_label"])}. {len(entries)} {"report" if len(entries) == 1 else "reports"} in The Signal.</p>
  </div>
</section>
<div class="wrap narrow"><ol class="timeline">{"".join(tl)}</ol>{bg}</div>
"""


def threads_index(threads, entries, prefix):
    groups = {}
    for t in threads.values():
        groups.setdefault(t["region"], []).append(t)
    secs = []
    for region in REGIONS + ["Frontiers"]:
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
  <p class="lede">The Signal is a daily briefing that asks one question: what changed in the world today that changes our picture of it?</p>
</div></section>
<div class="wrap prose">
  <h2>One edition a day</h2>
  <p>There is no feed and no breaking-news banner. Each morning we publish around ten world stories and a short Frontiers section on AI and science, and each evening we add what has changed since. Every story fits in a few lines on the front page; its full report, with key facts, background, what to watch and every source, is one click away.</p>
  <h2>Every region, every day</h2>
  <p>The region map covers North America, Latin America, Europe, Africa, the Middle East, Asia and Oceania. Each region shows its stories from the edition plus news that did not make the main page. If nothing important happened somewhere, we say so.</p>
  <h2>Stories belong to threads</h2>
  <p>A thread is a situation we keep following: an election, a war, an outbreak. Each day's story is the latest entry in its thread, so you can see how a situation got here. Thread pages keep the whole timeline.</p>
  <h2>Change and momentum</h2>
  <p>Every story carries two labels. Change says how much today's news altered the picture:</p>
  <table class="rubric"><tbody>{rows}</tbody></table>
  <p>Momentum says which way the situation is moving: <span class="mom mom-up">{momentum_icon("up")}Intensifying</span>, <span class="mom mom-steady">{momentum_icon("steady")}Holding</span> or <span class="mom mom-down">{momentum_icon("down")}Easing</span>. We use words rather than scores on purpose; a score like 7.8 implies a precision nobody has.</p>
  <h2>Sources and corrections</h2>
  <p>Every story links the reporting it is based on, and we paraphrase rather than reprint. When we get something wrong, the correction is added to the edition it fixes.</p>
</div>
"""


# --------------------------------------------------------------------------- feeds

def feed_xml(editions):
    items = []
    for ed in reversed(editions[-30:]):
        url = f"{SITE_URL}/editions/{ed['date']}/"
        body = "<p>" + e(ed["lede"]) + "</p><ul>" + "".join(
            f'<li><a href="{SITE_URL}/editions/{ed["date"]}/{s["thread"]}/">{e(s["headline"])}</a></li>' for s in ed["stories"]) + "</ul>"
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


def redirect(to):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{SITE_NAME}</title>'
            f'<meta http-equiv="refresh" content="0; url={to}"><link rel="canonical" href="{to}"></head>'
            f'<body><p><a href="{to}">Continue to The Signal →</a></p></body></html>')


def build():
    threads, editions = load()
    validate(threads, editions)
    if "--check" in sys.argv:
        print(f"OK: {len(editions)} editions, {len(threads)} threads")
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "assets").mkdir()
    for f in SRC.iterdir():
        shutil.copy(f, OUT / "assets" / f.name)
    (OUT / "assets" / "world.svg").write_text(maps.world_svg_file(), encoding="utf-8")
    if (ROOT / "images").is_dir():
        shutil.copytree(ROOT / "images", OUT / "images")
    (OUT / ".nojekyll").write_text("")
    paths = [""]
    latest = editions[-1]
    entries = thread_entries(threads, editions)
    for i, ed in enumerate(editions):
        prev_ed = editions[i - 1] if i > 0 else None
        next_ed = editions[i + 1] if i + 1 < len(editions) else None
        d = ed["date"]
        body = edition_body(ed, threads, "../../", False, prev_ed, next_ed)
        write(f"editions/{d}/index.html",
              page(long_date(d), body, "../../", f"editions/{d}/", active="archive", description=ed["lede"][:300]))
        paths.append(f"editions/{d}/")
        for kind in ("stories", "frontiers"):
            for s in ed.get(kind, []):
                write(f"editions/{d}/{s['thread']}/index.html",
                      page(s["headline"], story_page(s, ed, threads, entries[s["thread"]], "../../../", frontier=kind == "frontiers"),
                           "../../../", f"editions/{d}/{s['thread']}/", description=s["dek"]))
                paths.append(f"editions/{d}/{s['thread']}/")
        regions = region_items(ed, threads)
        for r in regions:
            html_ = page(f"{r['name']}, {day_month(d)}", region_page(r, ed, threads, "../../../../", regions),
                         "../../../../", f"editions/{d}/regions/{r['slug']}/", description=r["pulse"].get("text", "")[:300] or DESCRIPTION)
            write(f"editions/{d}/regions/{r['slug']}/index.html", html_)
            if ed is latest:
                write(f"regions/{r['slug']}/index.html",
                      page(r["name"], region_page(r, ed, threads, "../../", regions), "../../", f"regions/{r['slug']}/",
                           description=r["pulse"].get("text", "")[:300] or DESCRIPTION))
                paths.append(f"regions/{r['slug']}/")
    body = edition_body(latest, threads, "", True, editions[-2] if len(editions) > 1 else None, None)
    write("index.html", page(SITE_NAME, body, "", "", active="today"))
    for t in threads.values():
        write(f"threads/{t['id']}/index.html",
              page(t["title"], thread_page(t, entries[t["id"]], "../../"), "../../",
                   f"threads/{t['id']}/", active="threads", description=t["summary"]))
        paths.append(f"threads/{t['id']}/")
    write("threads/index.html", page("Threads", threads_index(threads, entries, "../"), "../", "threads/", active="threads"))
    write("forecasts/index.html", redirect(f"{SITE_URL}/"))
    write("archive/index.html", page("Archive", archive_page(editions, "../"), "../", "archive/", active="archive"))
    write("about/index.html", page("How it works", about_page("../"), "../", "about/", active="about"))
    write("404.html", page("Not found", '<section class="hero hero-plain"><div class="wrap"><h1 class="page-title">Nothing here</h1>'
                            f'<p class="lede">That page does not exist. <a href="{SITE_URL}/">Go to today\'s edition</a>.</p></div></section>',
                            f"{SITE_URL}/", "404.html"))
    paths += ["threads/", "archive/", "about/"]
    write("feed.xml", feed_xml(editions))
    write("sitemap.xml", sitemap(paths))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"Built {len(editions)} editions, {len(threads)} threads into docs/")


if __name__ == "__main__":
    try:
        build()
    except BuildError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
