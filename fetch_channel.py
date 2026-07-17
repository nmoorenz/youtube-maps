#!/usr/bin/env python3
"""
fetch_channel.py
----------------
Pull every video's metadata (title, description, upload date, URL) from a
YouTube channel using yt-dlp, and save it in three formats:

  1. <prefix>.csv   - spreadsheet: id, title, date, duration, url, description
  2. <prefix>.json  - full structured data
  3. <prefix>.js    - the map data file (defines MAP_TITLE + PLACES), in the
                      exact format the map pages load. lat/lng start as null
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
   --limit N     only fetch the N most recent videos (good for a first test)
   --out NAME    output filename prefix; use your channel's slug (default: channel_videos)
   --title TEXT  the MAP_TITLE shown on the map (default: derived from --out)

Example test run (fast, just 5 videos):
   python fetch_channel.py "https://www.youtube.com/@Japanese_Food_Noodles" --out japanese-food-noodles --limit 5
--------------------------------------------------------------------------
"""

import sys
import json
import csv
import argparse

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


def get_full_metadata(video_ids):
    """Second pass: fetch full info (incl. description) for each video."""
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
    return rows


def write_outputs(rows, prefix, map_title):
    # CSV
    csv_path = prefix + ".csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "title", "upload_date", "duration", "url", "description"]
        )
        writer.writeheader()
        writer.writerows(rows)

    # JSON
    json_path = prefix + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # <prefix>.js  (map data file: defines MAP_TITLE + PLACES)
    js_path = prefix + ".js"
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

    return csv_path, json_path, js_path


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube channel video metadata.")
    parser.add_argument("channel", help="Channel URL, e.g. https://www.youtube.com/@Japanese_Food_Noodles")
    parser.add_argument("--limit", type=int, default=None, help="Only fetch the N most recent videos")
    parser.add_argument("--out", default="channel_videos", help="Output filename prefix (use your channel slug)")
    parser.add_argument("--title", default=None, help="MAP_TITLE for the .js file (default: derived from --out)")
    args = parser.parse_args()

    # Default the map title to a readable version of the prefix.
    map_title = args.title or args.out.replace("-", " ").replace("_", " ").title()

    channel_url = normalize_channel_url(args.channel)
    print("Listing videos from: " + channel_url)
    ids = get_video_ids(channel_url, limit=args.limit)
    print("Found %d videos. Fetching descriptions...\n" % len(ids))

    if not ids:
        sys.exit("No videos found. Check the channel URL.")

    rows = get_full_metadata(ids)
    csv_path, json_path, js_path = write_outputs(rows, args.out, map_title)

    print("\nDone. %d videos saved:" % len(rows))
    print("  - %s   (open in Excel/Sheets to read descriptions)" % csv_path)
    print("  - %s" % json_path)
    print("  - %s   (rename to <channel>.js next to its .html, then add lat/lng)" % js_path)


if __name__ == "__main__":
    main()
