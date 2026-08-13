#!/usr/bin/env python3
"""
make_previews.py
----------------
Render a static map preview image for each channel, used as the thumbnail on
the home page (index.html). Each preview is a plain PNG fitted to the bounding
box of that channel's locations, with no markers.

Because the previews are images, the home page works even when opened directly
from disk (double-clicked) — no local web server needed. Re-run this script
whenever a channel's coordinates change to refresh its preview.

--------------------------------------------------------------------------
SETUP
--------------------------------------------------------------------------
    pip install staticmap

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
# Render previews for every channel data file in this folder:
    python make_previews.py

# Render just one:
    python make_previews.py japanese-food-noodles.js

# Check what it would do without downloading tiles:
    python make_previews.py --dry-run

Force a fixed frame instead of fitting to the markers (handy when a channel has
a few far-flung points that would otherwise zoom the thumbnail right out):
    python make_previews.py timeteam-classics.js --region uk

Options:
    --width N     image width in pixels  (default 480)
    --height N    image height in pixels (default 300)
    --max-zoom N  don't zoom in tighter than this (default 8; keeps a
                  single location from filling the frame at street level)
    --region NAME force a named frame: uk, uk-ireland, gb, japan
    --bbox BOX    force a custom frame: 'min_lat,min_lng,max_lat,max_lng'
    --dry-run     compute bounding box / center / zoom and print, but render nothing
--------------------------------------------------------------------------

A channel data file is any "<slug>.js" that has a matching "<slug>.html"
next to it (so map.js and index-only files are ignored).
"""

import re
import os
import sys
import glob
import math
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COORD_RE = re.compile(r"lat:\s*(-?\d+(?:\.\d+)?)\s*,\s*lng:\s*(-?\d+(?:\.\d+)?)")


def coords_from_js(path):
    """Return [(lat, lng), ...] for every entry with real coordinates.
    Lines with `lat: null` don't match the number pattern, so they're skipped."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [(float(a), float(b)) for a, b in COORD_RE.findall(text)]


def find_data_files():
    """Every <slug>.js at the site root that has a sibling <slug>.html."""
    out = []
    for js in sorted(glob.glob(os.path.join(ROOT, "*.js"))):
        if os.path.exists(js[:-3] + ".html"):
            out.append(js)
    return out


# --- Web-mercator helpers for fitting a bounding box ----------------------

def _x(lng):
    return (lng + 180.0) / 360.0


def _y(lat):
    lat = max(min(lat, 85.05112878), -85.05112878)
    s = math.sin(math.radians(lat))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def fit_center_zoom(coords, width, height, max_zoom, tile=256, pad=0.18):
    """Compute (center_lat, center_lng, zoom) that fits all coords in width x height."""
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    center = ((min_lat + max_lat) / 2.0, (min_lng + max_lng) / 2.0)

    dx = abs(_x(max_lng) - _x(min_lng)) * (1 + pad)
    dy = abs(_y(min_lat) - _y(max_lat)) * (1 + pad)

    zoom = max_zoom
    for z in range(max_zoom, -1, -1):
        world = tile * (2 ** z)
        if dx * world <= width and dy * world <= height:
            zoom = z
            break
        zoom = z  # keep going down; last assignment is z=0 if nothing fits
    return center[0], center[1], zoom


# Named frames you can force with --region, as (min_lat, min_lng, max_lat, max_lng).
REGIONS = {
    "uk": (50.0, -11.0, 59.2, 2.0),          # UK & Ireland, framed to the main landmass
    "uk-ireland": (50.0, -11.0, 59.2, 2.0),
    "uk-full": (49.0, -11.0, 61.0, 2.2),     # also includes Channel Islands & Shetland (zooms out more)
    "gb": (49.9, -8.7, 59.5, 1.9),           # Great Britain only
    "japan": (30.5, 129.0, 45.7, 146.0),
}


def parse_bbox(s):
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 'min_lat,min_lng,max_lat,max_lng'")
    return tuple(parts)


def main():
    ap = argparse.ArgumentParser(description="Render static map previews for channel cards.")
    ap.add_argument("files", nargs="*", help="Specific data files (default: all channel .js files)")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=300)
    ap.add_argument("--max-zoom", type=int, default=8)
    ap.add_argument("--region", choices=sorted(REGIONS), help="Force a named frame (e.g. uk) instead of fitting to the markers")
    ap.add_argument("--bbox", help="Force a custom frame: 'min_lat,min_lng,max_lat,max_lng'")
    ap.add_argument("--dry-run", action="store_true", help="Compute and print, but render nothing")
    args = ap.parse_args()

    forced = None
    if args.bbox:
        forced = parse_bbox(args.bbox)
    elif args.region:
        forced = REGIONS[args.region]

    # Resolve any explicitly-named files against the site root if needed.
    files = [f if os.path.exists(f) else os.path.join(ROOT, f) for f in args.files] or find_data_files()
    if not files:
        sys.exit("No channel data files found (need a <slug>.js with a matching <slug>.html).")

    StaticMap = None
    if not args.dry_run:
        try:
            from staticmap import StaticMap
        except ImportError:
            sys.exit("staticmap is not installed. Run:  pip install staticmap")

    for js in files:
        slug = js[:-3] if js.endswith(".js") else js

        if forced:
            # Frame a fixed box (e.g. UK & Ireland), ignoring where the markers are.
            fit_pts = [(forced[0], forced[1]), (forced[2], forced[3])]
            npts = "forced frame"
        else:
            fit_pts = coords_from_js(js)
            if not fit_pts:
                print("%-32s no coordinates — skipped" % js)
                continue
            npts = "%d points" % len(fit_pts)

        lat, lng, zoom = fit_center_zoom(fit_pts, args.width, args.height, args.max_zoom)
        print("%-32s %s  center=(%.3f, %.3f)  zoom=%d"
              % (js, npts, lat, lng, zoom))

        if args.dry_run:
            continue

        out_png = slug + ".png"
        # Polite tile usage: set a descriptive User-Agent (OSM tile policy).
        headers = {"User-Agent": "youtube-maps-preview/1.0 (personal project)"}
        try:
            m = StaticMap(args.width, args.height,
                          url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
                          headers=headers)
        except TypeError:
            # Older staticmap versions don't accept headers=
            m = StaticMap(args.width, args.height,
                          url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")

        image = m.render(zoom=zoom, center=[lng, lat])  # note: staticmap wants [lng, lat]
        image.save(out_png)
        print("    -> wrote %s" % out_png)


if __name__ == "__main__":
    main()
