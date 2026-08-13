#!/usr/bin/env python3
"""
parse_timeteam.py
-----------------
Turn Time Team Classics video titles into a CSV you can curate for the map.

Time Team titles usually name the dig location in brackets at the end, e.g.
    "The Lost Roman Villa | Time Team (Dinnington, Somerset) S7 ep7"
and often carry a season/episode marker like "S7 ep7", "S12 E9", or
"Series 3 Episode 4". This script pulls those out of each title and (optionally)
geocodes the location to latitude/longitude.

Output CSV columns:
    video_url, title, location, lat, lng, season, episode

Because the location text is fuzzy, treat the CSV as a starting point: the
script fills what it can and leaves the rest blank for you to correct by hand.

--------------------------------------------------------------------------
SETUP
--------------------------------------------------------------------------
    pip install requests

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
# 1) First pull the channel's videos (creates timeteam-classics.json):
    python fetch_channel.py "https://www.youtube.com/@TimeTeamClassics" --out timeteam-classics

# 2) Parse titles + geocode into a CSV:
    python parse_timeteam.py --json timeteam-classics.json --out timeteam-classics.csv

# See how the title parsing behaves on built-in examples (no network):
    python parse_timeteam.py --demo

Options:
    --json FILE      fetch_channel.py output to read (default: timeteam-classics.json)
    --out FILE       CSV to write (default: timeteam-classics.csv)
    --no-geocode     don't look up coordinates; just parse titles
    --no-uk-bias     geocode worldwide instead of restricting to Great Britain
    --demo           parse a set of example titles and print the result
--------------------------------------------------------------------------
"""

import os
import re
import csv
import sys
import json
import time
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

try:
    import requests
except ImportError:
    requests = None


# Season / episode, e.g. "S7 ep7", "S12E9", "S07 E07", "Series 3 Episode 4".
SE_RE = re.compile(
    r"(?:S|Series|Season)\s*\.?\s*(\d{1,2})\s*[,\-]?\s*(?:E|Ep|Episode)\s*\.?\s*(\d{1,3})",
    re.I,
)

# Bracket contents that are NOT a location.
NON_LOCATION = re.compile(
    r"^\s*(?:\d+\s*k|hd|uhd|4k|full episode|full|part\s*\d+|pt\s*\d+|documentary|"
    r"compilation|special|remastered|restored|time team|clip|highlights|"
    r"season\s*\d+|series\s*\d+|s\d+\s*e\d+)\s*$",
    re.I,
)


def parse_season_episode(title):
    m = SE_RE.search(title)
    if not m:
        return "", ""
    return int(m.group(1)), int(m.group(2))


def parse_location(title):
    """Return the most plausible bracketed location, or '' if none."""
    candidates = re.findall(r"\(([^()]+)\)", title)
    for text in reversed(candidates):        # prefer the last bracket (usually the place)
        t = text.strip()
        if not t:
            continue
        if NON_LOCATION.match(t):
            continue
        if SE_RE.search(t):                  # a bracket that's really a season/episode
            continue
        if not re.search(r"[A-Za-z]", t):    # must contain letters
            continue
        return t
    return ""


def geocode(query, session, uk_bias, cache):
    """Look up (lat, lng) for a place name via OpenStreetMap Nominatim."""
    if query in cache:
        return cache[query]
    params = {"q": query, "format": "json", "limit": 1}
    if uk_bias:
        params["countrycodes"] = "gb"
    headers = {"User-Agent": "youtube-maps-timeteam/1.0 (personal project)"}
    lat = lng = None
    try:
        r = session.get("https://nominatim.openstreetmap.org/search",
                        params=params, headers=headers, timeout=25)
        if r.status_code == 200:
            data = r.json()
            if data:
                lat = round(float(data[0]["lat"]), 6)
                lng = round(float(data[0]["lon"]), 6)
    except Exception as exc:
        print("      geocode failed for %r (%s)" % (query, exc))
    cache[query] = (lat, lng)
    time.sleep(1.1)  # Nominatim usage policy: <= 1 request/second
    return lat, lng


def build_rows(videos, do_geocode, uk_bias):
    session = None
    cache = {}
    if do_geocode:
        if requests is None:
            print("(!) requests not installed — skipping geocoding. Run: pip install requests")
            do_geocode = False
        else:
            session = requests.Session()

    rows = []
    for i, v in enumerate(videos, 1):
        title = v.get("title", "") or ""
        vid = v.get("id", "")
        url = v.get("url") or ("https://www.youtube.com/watch?v=" + vid if vid else "")

        location = parse_location(title)
        season, episode = parse_season_episode(title)
        lat = lng = None

        if do_geocode and location:
            lat, lng = geocode(location, session, uk_bias, cache)

        status = ("%s, %s" % (lat, lng)) if lat is not None else ("no coords" if location else "no location")
        print("  [%d/%d] %-55s -> %s" % (i, len(videos), (location or "(none)")[:55], status))

        rows.append({
            "video_url": url,
            "title": title,
            "location": location,
            "lat": lat if lat is not None else "",
            "lng": lng if lng is not None else "",
            "season": season,
            "episode": episode,
        })
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "video_url", "title", "location", "lat", "lng", "season", "episode"])
        w.writeheader()
        w.writerows(rows)


DEMO = [
    {"title": "The Lost Roman Villa | Time Team (Dinnington, Somerset) S7 ep7", "id": "aaaaaaaaaaa"},
    {"title": "Skeletons Under the Church | Time Team (Blackfriars, Gloucester) S12 E9", "id": "bbbbbbbbbbb"},
    {"title": "Britain's Pompeii? | Time Team (Must Farm, Cambridgeshire)", "id": "ccccccccccc"},
    {"title": "Digging for Vikings | Time Team - Series 3 Episode 4 (York)", "id": "ddddddddddd"},
    {"title": "Full Episode | Time Team (Waddesdon, Buckinghamshire) (4K)", "id": "eeeeeeeeeee"},
    {"title": "Time Team's Greatest Discoveries (Compilation)", "id": "fffffffffff"},
    {"title": "The Roman Baths — Time Team S15E2", "id": "ggggggggggg"},
]


def main():
    ap = argparse.ArgumentParser(description="Parse Time Team titles into a map CSV.")
    ap.add_argument("--json", default=os.path.join(DATA, "timeteam-classics.json"), help="fetch_channel.py output to read")
    ap.add_argument("--out", default=os.path.join(DATA, "timeteam-classics.csv"), help="CSV file to write")
    ap.add_argument("--no-geocode", action="store_true", help="Skip coordinate lookup")
    ap.add_argument("--no-uk-bias", action="store_true", help="Geocode worldwide, not just Great Britain")
    ap.add_argument("--demo", action="store_true", help="Parse built-in example titles (no network)")
    args = ap.parse_args()

    if args.demo:
        rows = build_rows(DEMO, do_geocode=False, uk_bias=True)
        print("\nParsed (title -> location | season | episode):")
        for r in rows:
            print("  %-60s | loc=%-28s | S=%s E=%s"
                  % (r["title"][:60], r["location"] or "-", r["season"] or "-", r["episode"] or "-"))
        return

    try:
        with open(args.json, encoding="utf-8") as f:
            videos = json.load(f)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run fetch_channel.py first." % args.json)

    print("Parsing %d videos..." % len(videos))
    rows = build_rows(videos, do_geocode=not args.no_geocode, uk_bias=not args.no_uk_bias)
    write_csv(rows, args.out)

    with_loc = sum(1 for r in rows if r["location"])
    with_xy = sum(1 for r in rows if r["lat"] != "")
    print("\nWrote %s" % args.out)
    print("  %d videos, %d with a location, %d geocoded." % (len(rows), with_loc, with_xy))
    print("  Review the CSV and fill in any missing/incorrect coordinates by hand.")


if __name__ == "__main__":
    main()
