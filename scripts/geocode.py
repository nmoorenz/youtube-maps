#!/usr/bin/env python3
"""
geocode.py
----------
Fill in the MISSING coordinates in a channel's map data file, without touching
the ones you've already set.

It reads a <slug>.js map file, finds every entry whose lat/lng is null, looks
that place up using the details in the matching <slug>.json (the maps link and
address from the video description), and writes the coordinates back into the
.js in place. Entries that already have coordinates are never changed, so it's
safe to run repeatedly and safe alongside your hand-edited coordinates.

For anything it still can't resolve, just fill the lat/lng in by hand in the
.js (or add a better address to the .json and re-run).

--------------------------------------------------------------------------
SETUP
--------------------------------------------------------------------------
    pip install requests

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
# Fill missing coords in japanese-food-noodles.js using japanese-food-noodles.json:
    python geocode.py japanese-food-noodles.js --country jp

# See what it would do without writing or hitting the network for addresses:
    python geocode.py japanese-food-noodles.js --dry-run

Options:
    --json FILE     the data source (default: same name as the .js, .json)
    --country CC    ISO country code to bias address lookups (e.g. jp, gb)
    --guess-from-title   last-resort: geocode the marker title itself when the
                         description has no usable location (off by default,
                         because a bare name can land on the wrong place)
    --limit N       only attempt the first N unresolved entries this run
    --dry-run       report what it would resolve; don't call address geocoding
                    or write the file
--------------------------------------------------------------------------
"""

import re
import os
import sys
import json
import time
import argparse

try:
    import requests
except ImportError:
    requests = None

# Reuse the description parsing + maps-link resolver we already have.
import extract_places as ep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


# Fields are matched independently, so extra fields (e.g. "location") and any
# field order are fine.
TITLE_RE = re.compile(r'title:\s*"(?P<title>(?:[^"\\]|\\.)*)"')
LAT_NULL_RE = re.compile(r"lat:\s*null")
LNG_NULL_RE = re.compile(r"lng:\s*null")


def build_location_lookup(videos):
    """name -> {maps_url, address} gathered from all video descriptions."""
    lut = {}
    for v in videos:
        for rec in ep.parse_description(v.get("description", "") or ""):
            name = (rec.get("name") or "").strip()
            if name and name not in lut:
                lut[name] = {
                    "maps_url": rec.get("maps_url", ""),
                    "address": rec.get("address", ""),
                }
    return lut


def nominatim(query, session, country, cache):
    if query in cache:
        return cache[query]
    params = {"q": query, "format": "json", "limit": 1}
    if country:
        params["countrycodes"] = country
    headers = {"User-Agent": "youtube-maps-geocode/1.0 (personal project)"}
    lat = lng = None
    try:
        r = session.get("https://nominatim.openstreetmap.org/search",
                        params=params, headers=headers, timeout=25)
        if r.status_code == 200 and r.json():
            lat = round(float(r.json()[0]["lat"]), 6)
            lng = round(float(r.json()[0]["lon"]), 6)
    except Exception as exc:
        print("      address lookup failed for %r (%s)" % (query, exc))
    cache[query] = (lat, lng)
    time.sleep(1.1)  # Nominatim policy: <= 1 request/second
    return lat, lng


def resolve_one(title, lut, session, country, guess_from_title, cache):
    """Return (lat, lng, how) for a title, or (None, None, reason)."""
    info = lut.get(title, {})
    # 1) Best signal: the Google Maps short link from the description.
    if info.get("maps_url"):
        lat, lng = ep.resolve_coords(info["maps_url"], session)
        if lat is not None:
            return lat, lng, "maps link"
    # 2) The address text from the description.
    if info.get("address"):
        lat, lng = nominatim(info["address"], session, country, cache)
        if lat is not None:
            return lat, lng, "address"
    # 3) Last resort (opt-in): the marker title itself.
    if guess_from_title:
        lat, lng = nominatim(title, session, country, cache)
        if lat is not None:
            return lat, lng, "title guess"
    return None, None, "no location found"


def main():
    ap = argparse.ArgumentParser(description="Fill missing coordinates in a channel .js file.")
    ap.add_argument("js", help="The map data file, e.g. japanese-food-noodles.js")
    ap.add_argument("--json", default=None, help="Data source (default: same name, .json)")
    ap.add_argument("--country", default=None, help="ISO country code to bias address lookups (e.g. jp)")
    ap.add_argument("--guess-from-title", action="store_true",
                    help="Last resort: geocode the marker title when no address is available")
    ap.add_argument("--limit", type=int, default=None, help="Only attempt the first N unresolved entries")
    ap.add_argument("--dry-run", action="store_true", help="Report only; don't geocode addresses or write")
    args = ap.parse_args()

    # The .js is a site file at the repo root; the details JSON lives in data/.
    if not os.path.exists(args.js) and os.path.exists(os.path.join(ROOT, args.js)):
        args.js = os.path.join(ROOT, args.js)
    if not os.path.exists(args.js):
        sys.exit("Couldn't find %s." % args.js)
    base = os.path.splitext(os.path.basename(args.js))[0]
    json_path = args.json or os.path.join(DATA, base + ".json")
    if not os.path.exists(json_path):
        sys.exit("Couldn't find %s (needed for the location details)." % json_path)

    with open(json_path, encoding="utf-8") as f:
        videos = json.load(f)
    lut = build_location_lookup(videos)

    with open(args.js, encoding="utf-8") as f:
        lines = f.readlines()

    # Count what's missing up front (an entry line with a title and a null coord).
    missing = []
    for idx, line in enumerate(lines):
        tm = TITLE_RE.search(line)
        if tm and (LAT_NULL_RE.search(line) or LNG_NULL_RE.search(line)):
            missing.append((idx, tm.group("title")))
    print("%d entries with no coordinates." % len(missing))
    if args.limit:
        missing = missing[:args.limit]

    session = None
    if not args.dry_run:
        if requests is None:
            sys.exit("requests is not installed. Run:  pip install requests")
        session = requests.Session()

    cache = {}
    filled = 0
    for idx, title in missing:
        if args.dry_run:
            info = lut.get(title, {})
            hint = "maps link" if info.get("maps_url") else ("address" if info.get("address") else "no location in JSON")
            print("  would try: %-45s (%s)" % (title[:45], hint))
            continue

        lat, lng, how = resolve_one(title, lut, session, args.country,
                                    args.guess_from_title, cache)
        if lat is None:
            print("  [ ] %-45s -> %s" % (title[:45], how))
            continue

        # Fill only the null coordinate(s) on this line; everything else
        # (title, location, video, order) is left exactly as-is.
        lines[idx] = LAT_NULL_RE.sub("lat: %s" % lat, lines[idx], count=1)
        lines[idx] = LNG_NULL_RE.sub("lng: %s" % lng, lines[idx], count=1)
        filled += 1
        print("  [x] %-45s -> %s, %s (%s)" % (title[:45], lat, lng, how))

    if args.dry_run:
        print("\nDry run — nothing written.")
        return

    if filled:
        with open(args.js, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("\nFilled %d entr%s. Wrote %s." % (filled, "y" if filled == 1 else "ies", args.js))
    else:
        print("\nNothing new resolved; %s left unchanged." % args.js)
    left = len(missing) - filled
    if left > 0:
        print("%d still without coordinates — fill those by hand in the .js." % left)


if __name__ == "__main__":
    main()
