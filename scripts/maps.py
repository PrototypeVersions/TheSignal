"""Small locator maps for stories, drawn as inline SVG from data/geo/countries.json.

A story may carry:
  "places": {
    "countries": ["FRA"],                       # ISO 3166 alpha-3 codes to highlight
    "related": ["DEU"],                         # optional: involved countries, drawn lighter
    "points": [{"name": "Paris", "lat": 48.86, "lon": 2.35}],
    "view": [lon_west, lat_south, lon_east, lat_north]   # optional framing
  }
Country shapes: Natural Earth via github.com/johan/world.geo.json (public domain).
"""
import html
import json
import math
import zlib
from pathlib import Path

GEO = Path(__file__).resolve().parent.parent / "data" / "geo" / "countries.json"
_world = None
e = html.escape


def world():
    global _world
    if _world is None:
        _world = json.loads(GEO.read_text(encoding="utf-8"))
        for c in _world.values():
            c["bbox"] = [_bbox([r]) for r in c["rings"]]
    return _world


def _bbox(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return [min(xs), min(ys), max(xs), max(ys)]


def _main_bbox(code):
    """Bounding box of a country's largest ring (ignores far-flung territories)."""
    c = world()[code]
    best = max(c["bbox"], key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    return best


def validate_places(places, where):
    errs = []
    if not places:
        return errs
    for code in places.get("countries", []) + places.get("related", []):
        if code not in world():
            errs.append(f"{where}: unknown country code '{code}' in places (use ISO alpha-3, e.g. FRA)")
    for p in places.get("points", []):
        if not isinstance(p.get("lat"), (int, float)) or not isinstance(p.get("lon"), (int, float)) or not p.get("name"):
            errs.append(f"{where}: each place point needs name, lat and lon")
    v = places.get("view")
    if v is not None and (len(v) != 4 or v[0] >= v[2] or v[1] >= v[3]):
        errs.append(f"{where}: view must be [lon_west, lat_south, lon_east, lat_north]")
    return errs


def _frame(places, aspect):
    if places.get("view"):
        w, s, east, n = places["view"]
    else:
        boxes = [_main_bbox(c) for c in places.get("countries", [])]
        boxes += [[p["lon"], p["lat"], p["lon"], p["lat"]] for p in places.get("points", [])]
        if not boxes:
            return None
        w = min(b[0] for b in boxes); s = min(b[1] for b in boxes)
        east = max(b[2] for b in boxes); n = max(b[3] for b in boxes)
        # breathing room, and a minimum span so tiny places get context
        padx = max((east - w) * 0.35, 4); pady = max((n - s) * 0.35, 3)
        w, east, s, n = w - padx, east + padx, s - pady, n + pady
    s, n = max(s, -80), min(n, 84)
    k = math.cos(math.radians((s + n) / 2))
    spanx, spany = (east - w) * k, (n - s)
    # grow the shorter side to match the requested aspect (width / height)
    if spanx / spany < aspect:
        grow = (spany * aspect / k - (east - w)) / 2
        w, east = w - grow, east + grow
    else:
        grow = (spanx / aspect - spany) / 2
        s, n = s - grow, n + grow
    return w, s, east, n, k


def map_svg(places, width=400, height=300, labels=True, cls=""):
    if not places:
        return ""
    fr = _frame(places, width / height)
    if not fr:
        return ""
    w, s, east, n, k = fr
    sx = width / (east - w)
    sy = height / (n - s)

    def P(lon, lat):
        return (lon - w) * sx, (n - lat) * sy

    hi = set(places.get("countries", []))
    rel = set(places.get("related", [])) - hi
    land, mark, soft = [], [], []
    for code, c in world().items():
        for ring, bb in zip(c["rings"], c["bbox"]):
            if bb[2] < w - 2 or bb[0] > east + 2 or bb[3] < s - 2 or bb[1] > n + 2:
                continue
            d, prev = [], None
            for lon, lat in ring:
                x, y = P(lon, lat)
                cmd = "M" if prev is None or abs(lon - prev) > 180 else "L"
                d.append(f"{cmd}{x:.1f} {y:.1f}")
                prev = lon
            path = "".join(d) + "Z"
            (mark if code in hi else soft if code in rel else land).append(path)
    # graticule
    step = 1 if (east - w) < 12 else 5 if (east - w) < 60 else 10 if (east - w) < 140 else 20
    grat = []
    g0 = math.ceil(w / step) * step
    lon = g0
    while lon < east:
        x, _ = P(lon, 0)
        grat.append(f"M{x:.1f} 0V{height}")
        lon += step
    lat = math.ceil(s / step) * step
    while lat < n:
        _, y = P(0, lat)
        grat.append(f"M0 {y:.1f}H{width}")
        lat += step
    pts = []
    for i, p in enumerate(places.get("points", [])):
        x, y = P(p["lon"], p["lat"])
        if not (0 <= x <= width and 0 <= y <= height):
            continue
        lab = ""
        if labels:
            anchor = "start" if x < width * 0.7 else "end"
            dx = 9 if anchor == "start" else -9
            lab = f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" class="ml">{e(p["name"])}</text>'
        pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4.5 if i == 0 else 3.5}" class="mp{" mp0" if i == 0 else ""}"/>{lab}')
    names = [world()[c]["name"] for c in places.get("countries", [])] + [p["name"] for p in places.get("points", [])]
    label = "Map: " + ", ".join(dict.fromkeys(names))
    uid = "m%08x" % zlib.crc32(f"{sorted(hi)}{width}{height}{w:.3f}{s:.3f}".encode())
    return (f'<svg class="map {cls}" viewBox="0 0 {width} {height}" role="img" aria-label="{e(label)}">'
            f'<defs><clipPath id="{uid}"><rect width="{width}" height="{height}" rx="6"/></clipPath></defs>'
            f'<g clip-path="url(#{uid})"><rect width="{width}" height="{height}" class="sea"/>'
            f'<path d="{"".join(grat)}" class="grat"/>'
            f'<path d="{"".join(land)}" class="land"/><path d="{"".join(soft)}" class="rel"/><path d="{"".join(mark)}" class="hl"/>'
            f'{"".join(pts)}</g></svg>')


# --------------------------------------------------------------------------- world overview

WORLD_W, WORLD_H = 1000, 470
WORLD_N, WORLD_S = 84.0, -58.0


def world_xy(lon, lat):
    """Equirectangular position on the world overview."""
    return (lon + 180) / 360 * WORLD_W, (WORLD_N - lat) / (WORLD_N - WORLD_S) * WORLD_H


def world_svg_file():
    """A standalone world map (Natural Earth outlines) in the site's dark colours, used as a backdrop."""
    land = []
    for c in world().values():
        for ring in c["rings"]:
            d, prev = [], None
            for lon, lat in ring:
                if lat < WORLD_S - 2:
                    lat = WORLD_S - 2
                x, y = world_xy(lon, lat)
                cmd = "M" if prev is None or abs(lon - prev) > 180 else "L"
                d.append(f"{cmd}{x:.1f} {y:.1f}")
                prev = lon
            land.append("".join(d) + "Z")
    grat = []
    for lon in range(-150, 180, 30):
        x, _ = world_xy(lon, 0)
        grat.append(f"M{x:.1f} 0V{WORLD_H}")
    for lat in range(-30, 84, 30):
        _, y = world_xy(0, lat)
        grat.append(f"M0 {y:.1f}H{WORLD_W}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WORLD_W} {WORLD_H}">'
            f'<path d="{"".join(grat)}" fill="none" stroke="#1F2C44" stroke-width="1"/>'
            f'<path d="{"".join(land)}" fill="#1A2943" stroke="#2F4163" stroke-width=".7" stroke-linejoin="round"/></svg>')
