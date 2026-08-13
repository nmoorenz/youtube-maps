#!/usr/bin/env python3
"""
wiki_episodes.py
----------------
Build a list of Time Team episodes from Wikipedia, including the dig location
and its coordinates (Wikipedia lists decimal coordinates for almost every
episode, so most rows come out already geocoded).

Source: https://en.wikipedia.org/wiki/List_of_Time_Team_episodes

Output (in the current folder):
    timeteam-episodes.json   list of {season, episode, title, location, lat, lng, year}

Uses only the Python standard library (no pip installs needed).

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python wiki_episodes.py
    python wiki_episodes.py --out timeteam-episodes   # change filename prefix
--------------------------------------------------------------------------
"""

import os
import re
import sys
import json
import html
import argparse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

URL = "https://en.wikipedia.org/wiki/List_of_Time_Team_episodes"

TAG_RE = re.compile(r"<[^>]+>")
# Decimal coordinate pair as Wikipedia renders it, e.g. "51.059011°N 2.936678°W".
COORD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*°\s*([NS]).{0,60}?(\d+(?:\.\d+)?)\s*°\s*([EW])", re.S)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "youtube-maps-timeteam/1.0 (personal project; contact via github)"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def strip_tags(s):
    return html.unescape(TAG_RE.sub("", s)).replace("​", "").strip()


def parse_coords(cell_html):
    """Return (lat, lng) from a Coordinates cell, or (None, None)."""
    text = strip_tags(cell_html)
    m = COORD_RE.search(text)
    if not m:
        return None, None
    lat = float(m.group(1)) * (-1 if m.group(2) == "S" else 1)
    lng = float(m.group(3)) * (-1 if m.group(4) == "W" else 1)
    return round(lat, 6), round(lng, 6)


def cells(row_html):
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)


def find_season_markers(page):
    """List of (position, season_label) for 'Series N' / Specials / Others headings.
    Wikipedia section ids often carry a year suffix (e.g. id="Series_1_(1994)"),
    so we match the 'Series_<n>' prefix without requiring a closing quote."""
    markers = []
    for m in re.finditer(r'id="Series[ _](\d+)', page):
        markers.append((m.start(), int(m.group(1))))
    for m in re.finditer(r'id="(Specials|Others)', page):
        markers.append((m.start(), m.group(1).lower()))
    markers.sort()
    return markers


def season_for(pos, markers):
    season = None
    for mpos, label in markers:
        if mpos <= pos:
            season = label
        else:
            break
    return season


def parse_episodes(page):
    markers = find_season_markers(page)
    episodes = []
    for tmatch in re.finditer(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', page, re.S | re.I):
        table_html = tmatch.group(1)
        season = season_for(tmatch.start(), markers)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
        # Which column is which? Find the header row to locate Title/Location/Coordinates.
        header = None
        for r in rows:
            cs = [strip_tags(c).lower() for c in cells(r)]
            if any("title" in c for c in cs) and any("location" in c for c in cs):
                header = cs
                break
        if not header:
            continue
        def col(name):
            for i, c in enumerate(header):
                if name in c:
                    return i
            return None
        i_ep = next((i for i, c in enumerate(header) if "in season" in c or "no. in" in c), None)
        i_date = next((i for i, c in enumerate(header) if "release" in c or "date" in c or "aired" in c), None)
        i_title, i_loc, i_coord = col("title"), col("location"), col("coordinates")

        for r in rows:
            raw = cells(r)
            if len(raw) < max(x for x in [i_title, i_loc] if x is not None) + 1:
                continue
            title = strip_tags(raw[i_title]).strip().strip('"').strip()
            if not title or title.lower() == "title":
                continue
            location = strip_tags(raw[i_loc]) if i_loc is not None and i_loc < len(raw) else ""
            lat = lng = None
            if i_coord is not None and i_coord < len(raw):
                lat, lng = parse_coords(raw[i_coord])
            # episode number within season (best effort)
            episode = ""
            if i_ep is not None and i_ep < len(raw):
                mnum = re.search(r"\d+", strip_tags(raw[i_ep]))
                episode = mnum.group(0) if mnum else ""
            # Year from the release-date cell (strip tags first — Wikipedia hides
            # the ISO date inside a <span>, so the raw HTML has no plain "(YYYY-...)").
            year = ""
            date_text = strip_tags(raw[i_date]) if i_date is not None and i_date < len(raw) else strip_tags(r)
            ym = YEAR_RE.search(date_text)
            if ym:
                year = ym.group(1)
            episodes.append({
                "season": season if season is not None else "",
                "episode": episode,
                "title": title,
                "location": location,
                "lat": lat,
                "lng": lng,
                "year": year,
            })
    return episodes


def main():
    ap = argparse.ArgumentParser(description="Parse the Wikipedia Time Team episode list.")
    ap.add_argument("--out", default=os.path.join(DATA, "timeteam-episodes"),
                    help="Output filename prefix (default: data/timeteam-episodes)")
    ap.add_argument("--url", default=URL, help="Override the source URL (e.g. a saved copy)")
    args = ap.parse_args()

    print("Fetching %s ..." % args.url)
    try:
        page = fetch(args.url)
    except Exception as exc:
        sys.exit("Couldn't fetch the page (%s)." % exc)

    episodes = parse_episodes(page)
    if not episodes:
        sys.exit("Parsed 0 episodes — the page layout may have changed.")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)

    with_xy = sum(1 for e in episodes if e["lat"] is not None)
    with_season = sum(1 for e in episodes if e["season"] != "")
    print("Parsed %d episodes, %d with coordinates, %d with a season." % (len(episodes), with_xy, with_season))
    print("Wrote %s.json" % args.out)


if __name__ == "__main__":
    main()
