#!/usr/bin/env python3
"""
extract_places.py
-----------------
Read YouTube video descriptions and pull out, for each shop/place mentioned:
    - name        (from "Shop Name" / "Store Name" / "Name" labels)
    - maps_url    (the real Google Maps link)
    - video_id    (which video it came from)
    - address     (from the "Address" label)
    - lat, lng    (resolved by following the maps link)

Two tricky bits it handles automatically:
  * The visible "maps.app.goo.gl/..." text is often truncated. The real,
    complete link is hidden inside YouTube's redirect URL as the `q=`
    parameter, so this script unwraps those.
  * That same redirect URL carries the video id in `v=`, so each shop gets
    linked back to its video without extra work.

Turning a short maps link into coordinates means following the link over the
internet, so that step needs a network connection and the `requests` library.

--------------------------------------------------------------------------
SETUP
--------------------------------------------------------------------------
    pip install requests

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
# 1) See it work on the built-in examples (parsing only, no network):
    python extract_places.py --demo

# 2) Same, but also resolve coordinates (needs internet):
    python extract_places.py --demo --resolve

# 3) Parse a plain text file of descriptions and resolve coordinates:
    python extract_places.py --text descriptions.txt --resolve

# 4) Parse the JSON produced by fetch_channel.py (one record per shop found),
#    resolve coordinates, and write a map-ready data file:
    python extract_places.py --json channel_videos.json --resolve --js japanese-food-noodles.js --title "Japanese Food Noodles"

Outputs:
    places.csv                 always written (video_id, name, address, maps_url, lat, lng)
    <--js file>                optional; a ready-to-use PLACES data file for the map

Tip: run without --resolve first to check the names/links parse correctly,
then add --resolve once you're happy.
--------------------------------------------------------------------------
"""

import re
import csv
import json
import argparse
import sys
import time
from urllib.parse import urlparse, parse_qs, unquote

try:
    import requests
except ImportError:
    requests = None


MAPS_DOMAINS = ("maps.app.goo.gl", "goo.gl/maps", "google.com/maps", "maps.google.")

# Label that starts a record. Must be followed by ":" / "：" / full-width space,
# which prevents matching stray words like the "Store" in "Umi Store Map".
LABEL_RE = re.compile(r"(?:Shop\s*Name|Store\s*Name|Shop|Store|Name)[ \t]*[:：　]", re.I)
URL_RE = re.compile(r"https?://[^\s\)\]<>]+")
ADDRESS_RE = re.compile(r"Address[ \t]*[:：　]?[ \t]*(.+)", re.I)


def unwrap_url(url):
    """Return (maps_url_or_None, video_id_or_None) for a URL.
    If it's a YouTube redirect, pull the real link from q= and the video from v=."""
    if "youtube.com/redirect" in url:
        qs = parse_qs(urlparse(url).query)
        maps = unquote(qs["q"][0]) if "q" in qs else None
        vid = qs["v"][0] if "v" in qs else None
        return maps, vid
    return url, None


def find_maps_and_video(segment):
    """Find the best maps URL and any video id within a text segment."""
    maps_url = ""
    video_id = ""
    for u in URL_RE.findall(segment):
        m, v = unwrap_url(u)
        if v and not video_id:
            video_id = v
        if m and any(d in m for d in MAPS_DOMAINS):
            # Skip truncated/garbage links (contain "[" or "..." from display text)
            if "[" in m or "..." in m:
                continue
            if not maps_url:
                maps_url = m
    return maps_url, video_id


def parse_description(text, default_video_id=""):
    """Return a list of place records found in one description."""
    records = []
    matches = list(LABEL_RE.finditer(text))
    if not matches:
        return records

    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        segment = text[start:end]

        # Name = everything up to the "Map" keyword.
        name = re.split(r"\bMap\b", segment, maxsplit=1, flags=re.I)[0]
        name = name.strip(" \t\r\n:：　")

        maps_url, video_id = find_maps_and_video(segment)
        if not video_id:
            video_id = default_video_id

        addr_m = ADDRESS_RE.search(segment)
        address = addr_m.group(1).strip(" \t\r\n:：　") if addr_m else ""

        if name or maps_url:
            records.append({
                "name": name,
                "maps_url": maps_url,
                "video_id": video_id,
                "address": address,
                "lat": None,
                "lng": None,
            })
    return records


# --- Coordinate resolution (needs network) -------------------------------

COORD_PATTERNS = [
    re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)"),   # exact place coords
    re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)"),        # map center
    re.compile(r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)"),  # ll= param
    re.compile(r"/(-?\d+\.\d+),(-?\d+\.\d+)"),        # path coords
]


def resolve_coords(maps_url, session):
    """Follow a maps link and extract (lat, lng). Returns (None, None) on failure."""
    if not maps_url:
        return None, None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = session.get(maps_url, headers=headers, allow_redirects=True, timeout=25)
    except Exception as exc:
        print("      could not fetch %s (%s)" % (maps_url, exc))
        return None, None

    haystacks = [r.url or "", r.text or ""]
    for pat in COORD_PATTERNS:
        for h in haystacks:
            m = pat.search(h)
            if m:
                return float(m.group(1)), float(m.group(2))
    return None, None


# --- Output ---------------------------------------------------------------

def write_csv(records, path="places.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video_id", "name", "address", "maps_url", "lat", "lng"])
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    return path


def write_js(records, path, map_title):
    safe_title = map_title.replace('"', "'")
    with open(path, "w", encoding="utf-8") as f:
        f.write("// Generated by extract_places.py. Loaded before map.js.\n")
        f.write("// Entries with lat/lng null won't appear until coordinates resolve.\n\n")
        f.write('const MAP_TITLE = "%s";\n\n' % safe_title)
        f.write("const PLACES = [\n")
        for r in records:
            title = (r.get("name") or "").replace('"', "'")
            vid = r.get("video_id") or ""
            video = ("https://www.youtube.com/watch?v=" + vid) if vid else ""
            lat = r["lat"] if r.get("lat") is not None else "null"
            lng = r["lng"] if r.get("lng") is not None else "null"
            f.write('  { title: "%s", video: "%s", lat: %s, lng: %s },\n' % (title, video, lat, lng))
        f.write("];\n")
    return path


# --- Built-in demo data ---------------------------------------------------

DEMO = [
    'Shop Name　100-Year Shokudo Tanakaya \nMap　https://maps.app.goo.gl/3WNApAGxttutc[...](https://www.youtube.com/redirect?event=video_description&redir_token=ABC&q=https%3A%2F%2Fmaps.app.goo.gl%2F3WNApAGxttutcVUg7&v=CzTVxom0asE) Address　3-11-26 Ritsurincho, Takamatsu City, Kagawa',
    'Shop Name　Marutoma Shokudo Map　https://maps.app.goo.gl/HkJxPAsM5oZFo[...](https://www.youtube.com/redirect?event=video_description&redir_token=DEF&q=https%3A%2F%2Fmaps.app.goo.gl%2FHkJxPAsM5oZFox9x8&v=JtzB9KSB1Fk) Address　Tomakomai City Public Wholesale Market, 1-1-13 Shiomi-cho, Tomakomai City, Hokkaido',
    'Store Name: Don Mac Umi Store Map: https://maps.app.goo.gl/5cCALiGq1rn9f[...](https://www.youtube.com/redirect?event=video_description&redir_token=GHI&q=https%3A%2F%2Fmaps.app.goo.gl%2F5cCALiGq1rn9fgoR6&v=2PA7fok3TFs) Address: 1-3-48 Kōshōji, Umi-machi, Kasuya-gun, Fukuoka Prefecture',
]


def collect(records, resolve):
    """Optionally resolve coordinates for a list of records."""
    if not resolve:
        return records
    if requests is None:
        sys.exit("--resolve needs the requests library. Run:  pip install requests")
    session = requests.Session()
    for i, r in enumerate(records, 1):
        print("  resolving [%d/%d] %s" % (i, len(records), r.get("name") or r.get("maps_url")))
        lat, lng = resolve_coords(r.get("maps_url", ""), session)
        r["lat"], r["lng"] = lat, lng
        time.sleep(0.5)  # be polite
    return records


def main():
    ap = argparse.ArgumentParser(description="Extract shop names + coordinates from YouTube descriptions.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", action="store_true", help="Use the built-in example descriptions")
    src.add_argument("--text", help="A plain text file containing one or more descriptions")
    src.add_argument("--json", help="channel_videos.json from fetch_channel.py")
    ap.add_argument("--resolve", action="store_true", help="Follow maps links to get lat/lng (needs internet)")
    ap.add_argument("--js", help="Also write a map-ready PLACES data file to this path")
    ap.add_argument("--title", default="YouTube Map", help="MAP_TITLE for the --js output")
    args = ap.parse_args()

    records = []

    if args.demo:
        for desc in DEMO:
            records.extend(parse_description(desc))

    elif args.text:
        with open(args.text, encoding="utf-8") as f:
            text = f.read()
        records.extend(parse_description(text))

    elif args.json:
        with open(args.json, encoding="utf-8") as f:
            videos = json.load(f)
        for v in videos:
            vid = v.get("id", "")
            for rec in parse_description(v.get("description", ""), default_video_id=vid):
                records.append(rec)

    print("Found %d place record(s)." % len(records))
    records = collect(records, args.resolve)

    csv_path = write_csv(records)
    print("Wrote %s" % csv_path)
    if args.js:
        write_js(records, args.js, args.title)
        print("Wrote %s" % args.js)

    # Console preview
    for r in records:
        coords = ("%s, %s" % (r["lat"], r["lng"])) if r["lat"] is not None else "(not resolved)"
        print("  - %-40s %s" % ((r["name"] or "?")[:40], coords))


if __name__ == "__main__":
    main()
