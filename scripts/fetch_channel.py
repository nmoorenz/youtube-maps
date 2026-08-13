#!/usr/bin/env python3
"""
fetch_channel.py
----------------
Pull every video's metadata (title, description, upload date, URL) from a
YouTube channel using yt-dlp, and save it in two formats:

  1. <prefix>.json  - full structured data, including descriptions. This is the
                      source of truth, read by extract_places.py and
                      parse_timeteam.py.
  2. <prefix>.js    - a starter map data file (defines MAP_TITLE + PLACES), in
                      the exact format the map pages load. lat/lng start as null
                      for you to fill in per video. Rename it to match your
                      channel page, e.g. japanese-food-noodles.js

WHY: the descriptions on food/travel channels usually name the shop and city,
which is what you'll geocode to place each marker on the map.

--------------------------------------------------------------------------
SETUP (one time)
--------------------------------------------------------------------------
1. Install Python 3.9+ if you don't have it:  https://www.python.org/downloads/
2. Install yt-dlp:
       pip install yt-dlp
   (on Mac/Linux you may need:  pip3 install yt-dlp  )

--------------------------------------------------------------------------
RUN
--------------------------------------------------------------------------
   python fetch_channel.py "https://www.youtube.com/@Japanese_Food_Noodles" --out japanese-food-noodles

That produces japanese-food-noodles.js (among others) already matching the
map's data format - it drops straight in next to japanese-food-noodles.html.

Options:
   --limit N     fetch at most N NEW videos this run. Because it resumes, running
                 again fetches the NEXT N, so repeated runs accumulate the whole
                 channel a batch at a time (handy for avoiding rate limits).
                 Omit to fetch everything not yet fetched.
   --out NAME    output filename prefix; use your channel's slug (default: channel_videos)
   --title TEXT  the MAP_TITLE shown on the map (default: derived from --out)

Accumulate in batches (run repeatedly; each run grabs the next 50):
   python fetch_channel.py "https://www.youtube.com/@Japanese_Food_Noodles" --out japanese-food-noodles --limit 50
--------------------------------------------------------------------------
"""

import os
import sys
import json
import time
import argparse

# Repo root = parent of this scripts/ folder; intermediates live in data/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

try:
    from yt_dlp import YoutubeDL
except ImportError:
    sys.exit("yt-dlp is not installed. Run:  pip install yt-dlp")


def normalize_channel_url(url):
    """Make sure we point at the channel's video list."""
    url = url.rstrip("/")
    if url.endswith("/videos"):
        return url
    return url + "/videos"


def get_video_ids(channel_url, limit=None):
    """Fast pass: list video IDs without downloading full pages."""
    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "ignoreerrors": True,
    }
    if limit:
        opts["playlistend"] = limit

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    entries = info.get("entries") or []
    ids = []
    for e in entries:
        if not e:
            continue
        if e.get("_type") == "playlist" and e.get("entries"):
            for sub in e["entries"]:
                if sub and sub.get("id"):
                    ids.append(sub["id"])
        elif e.get("id"):
            ids.append(e["id"])
    return ids


def get_full_metadata(video_ids, sleep=1.0):
    """Second pass: fetch full info (incl. description) for each video.
    `sleep` is the pause (seconds) between videos, to avoid YouTube rate limits."""
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        # We only want text metadata (title/description/date), never the video
        # streams. Skipping the player JS avoids the "n challenge" / SABR work
        # that produces those format warnings, and makes each lookup faster.
        "extractor_args": {"youtube": {"player_skip": ["js"]}},
    }
    rows = []
    total = len(video_ids)
    with YoutubeDL(opts) as ydl:
        for i, vid in enumerate(video_ids, 1):
            print("  [%d/%d] %s" % (i, total, vid), flush=True)
            try:
                info = ydl.extract_info(
                    "https://www.youtube.com/watch?v=" + vid, download=False
                )
            except Exception as exc:
                print("      skipped (%s)" % exc)
                continue
            if not info:
                continue
            rows.append({
                "id": info.get("id"),
                "title": info.get("title", ""),
                "upload_date": info.get("upload_date", ""),
                "duration": info.get("duration"),
                "url": "https://www.youtube.com/watch?v=" + str(info.get("id")),
                "description": info.get("description", "") or "",
            })
            if sleep and i < total:
                time.sleep(sleep)
    return rows


def write_outputs(rows, prefix, map_title):
    os.makedirs(DATA, exist_ok=True)
    # JSON — the source of truth; read by extract_places.py / parse_timeteam.py.
    json_path = os.path.join(DATA, prefix + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # <prefix>.js  (starter map data file: defines MAP_TITLE + PLACES).
    # Kept in data/ too, so re-fetching never overwrites the real site .js at the root.
    js_path = os.path.join(DATA, prefix + ".js")
    safe_map_title = map_title.replace('"', "'")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// Map data file. Loaded by the channel's .html page before map.js.\n")
        f.write("// Fill in lat/lng for each video (right-click a spot in Google Maps to copy coords).\n")
        f.write("// Entries left with lat/lng null won't appear until you add coordinates.\n\n")
        f.write('const MAP_TITLE = "%s";\n\n' % safe_map_title)
        f.write("const PLACES = [\n")
        for r in rows:
            safe_title = r["title"].replace('"', "'")
            f.write(
                '  { title: "%s", video: "%s", lat: null, lng: null },\n'
                % (safe_title, r["url"])
            )
        f.write("];\n")

    return json_path, js_path


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube channel video metadata.")
    parser.add_argument("channel", help="Channel URL, e.g. https://www.youtube.com/@Japanese_Food_Noodles")
    parser.add_argument("--limit", type=int, default=None,
                        help="Fetch at most N NEW videos this run (accumulates across runs). Omit to fetch all remaining.")
    parser.add_argument("--out", default="channel_videos", help="Output filename prefix (use your channel slug)")
    parser.add_argument("--title", default=None, help="MAP_TITLE for the .js file (default: derived from --out)")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="Seconds to pause between videos, to avoid YouTube rate limits (default 1.0)")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore any existing <out>.json and re-fetch every video from scratch "
                             "(default is to resume: reuse what's there and fetch only the missing ones)")
    args = parser.parse_args()

    # Default the map title to a readable version of the prefix.
    map_title = args.title or args.out.replace("-", " ").replace("_", " ").title()

    channel_url = normalize_channel_url(args.channel)
    print("Listing videos from: " + channel_url)
    ids = get_video_ids(channel_url)      # list the whole channel (cheap, one pass)
    print("Found %d videos on the channel." % len(ids))

    if not ids:
        sys.exit("No videos found. Check the channel URL.")

    # Resume by default: reuse anything already fetched so we don't re-request it.
    # Use --fresh to ignore existing data and fetch everything again.
    existing = {}
    if args.fresh:
        print("Fresh run: ignoring any existing data.")
    else:
        json_existing = os.path.join(DATA, args.out + ".json")
        try:
            with open(json_existing, encoding="utf-8") as f:
                for row in json.load(f):
                    if row.get("id"):
                        existing[row["id"]] = row
            print("Resuming: %d already fetched." % len(existing))
        except FileNotFoundError:
            pass  # nothing to resume from — just fetch everything

    to_fetch = [v for v in ids if v not in existing]
    remaining = len(to_fetch)
    # --limit caps how many NEW videos to fetch this run, so repeated runs
    # accumulate (fetch the next batch each time) instead of redoing the same ones.
    if args.limit:
        to_fetch = to_fetch[:args.limit]
    print("%d not yet fetched; fetching %d this run...\n" % (remaining, len(to_fetch)))

    fetched = get_full_metadata(to_fetch, sleep=args.sleep)
    for row in fetched:
        if row.get("id"):
            existing[row["id"]] = row

    # Preserve the channel's video order, keeping only ids we actually have data for.
    rows = [existing[v] for v in ids if v in existing]

    json_path, js_path = write_outputs(rows, args.out, map_title)

    print("\nDone. %d videos saved:" % len(rows))
    print("  - %s   (structured data, incl. descriptions)" % json_path)
    print("  - %s   (starter map data file; add lat/lng, or feed into a parser)" % js_path)


if __name__ == "__main__":
    main()
