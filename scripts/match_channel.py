#!/usr/bin/env python3
"""
match_channel.py
----------------
Match already-fetched channel videos against the Wikipedia episode list (from
wiki_episodes.py) and produce a map-ready CSV.

This does no network access — it reads the video data that fetch_channel.py has
already accumulated, so you can re-fetch/accumulate videos independently and
just re-run this whenever you want to refresh the matches.

For each episode it looks for a video whose season/episode marker (then title)
matches, and attaches that video's URL. Episodes with no matching video are kept
with a blank video_url — not every episode exists on the channel.

It writes the map data file (<slug>.js) directly and, on first run, the page
(<slug>.html) and a card in index.html — so there's no separate build step.

--------------------------------------------------------------------------
THE PIPELINE
--------------------------------------------------------------------------
    1. python wiki_episodes.py                                   # once; -> timeteam-episodes.json
    2. python fetch_channel.py "https://www.youtube.com/@TimeTeamClassics" --out timeteam-classics
                                                                 # accumulates -> timeteam-classics.json
    3. python match_channel.py                                   # -> timeteam-classics.js (+ .html, index card)
    4. python make_previews.py                                   # refresh the home-page thumbnail

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python match_channel.py --title "Time Team Classics" --note "UK archaeology digs"

Options:
    --episodes FILE       episode list from wiki_episodes.py (default timeteam-episodes.json)
    --videos FILE         accumulated videos from fetch_channel.py (default timeteam-classics.json)
    --out SLUG            output slug (default timeteam-classics -> .js and .html)
    --title TEXT          map heading (default: derived from --out)
    --note TEXT           description for the index.html card
    --threshold N         title-fallback strictness 0-1 (default 0.6; higher = stricter)
    --matched-only        only map episodes that matched a video (default: every episode with coords)
    --no-html / --no-index   skip creating the page / touching index.html
    --review              also write <slug>-review.csv with the full match detail
--------------------------------------------------------------------------
"""

import re
import os
import csv
import sys
import json
import argparse
import difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# Season/episode marker in a video title: "S7 E7", "S7 ep7", "Series 3 Episode 4".
SE_RE = re.compile(
    r"(?:S|Series|Season)\s*\.?\s*(\d{1,2})\s*[,\-]?\s*(?:E|Ep|Episode)\s*\.?\s*(\d{1,3})",
    re.I,
)


def norm(s):
    """Lowercase, drop punctuation, collapse spaces — for comparing titles."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def parse_se(title):
    """Return (season, episode) as ints from a video title, or None."""
    m = SE_RE.search(title or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def score(ep_title, video_title):
    """0-1 similarity. Substring match (episode title inside the video title) scores 1."""
    et, vt = norm(ep_title), norm(video_title)
    if not et:
        return 0.0
    if et in vt:
        return 1.0
    return difflib.SequenceMatcher(None, et, vt).ratio()


def match(episodes, videos, threshold):
    """Attach the best-matching video to each episode.

    Priority: match on season+episode (most reliable for Time Team), then fall
    back to title similarity. A title-similarity score is always recorded too,
    so a season/episode match with an unrelated-looking title stands out."""
    # Group videos by the (season, episode) in their titles — there can be more
    # than one (e.g. a full episode plus a highlights clip).
    se_index = {}
    for v in videos:
        se = parse_se(v.get("title", ""))
        if se:
            se_index.setdefault(se, []).append(v)

    for ep in episodes:
        s, e = to_int(ep.get("season")), to_int(ep.get("episode"))
        chosen, method = None, ""
        ep["se_candidates"] = 0

        if s is not None and e is not None and (s, e) in se_index:
            candidates = se_index[(s, e)]
            ep["se_candidates"] = len(candidates)
            # If several videos share this S/E, keep the one whose title best
            # matches the episode (rather than an arbitrary first).
            chosen = max(candidates, key=lambda v: score(ep["title"], v.get("title", "")))
            method = "season/episode"

        if not chosen:
            best, best_score = None, 0.0
            for v in videos:
                sc = score(ep["title"], v.get("title", ""))
                if sc > best_score:
                    best, best_score = v, sc
            if best and best_score >= threshold:
                chosen, method = best, "title"

        # Title similarity for display (of the chosen video, or the best available).
        if chosen:
            title_score = score(ep["title"], chosen.get("title", ""))
        else:
            title_score = max((score(ep["title"], v.get("title", "")) for v in videos), default=0.0)

        ep["video_url"] = ("https://www.youtube.com/watch?v=" + chosen["id"]) if chosen else ""
        ep["video_title"] = chosen.get("title", "") if chosen else ""
        ep["match_method"] = method
        ep["match_score"] = round(title_score, 3)
    return episodes


def load_videos(path):
    """Load the accumulated videos from fetch_channel.py's JSON: [{id, title, ...}]."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [{"id": v.get("id", ""), "title": v.get("title", "")} for v in data if v.get("id")]


def write_js(episodes, path, map_title, matched_only):
    """The map is based on the Wikipedia episode list: every episode that has
    coordinates becomes a marker (a clickable thumbnail if a video matched, or a
    plain location pin if not). The fetched channel only supplies the video links.
    With matched_only, restrict to episodes that have a matched video."""
    safe_title = map_title.replace('"', "'")
    with open(path, "w", encoding="utf-8") as f:
        f.write("// Generated by match_channel.py. Based on the Wikipedia episode list;\n")
        f.write("// video links come from the fetched channel. Loaded before map.js.\n\n")
        f.write('const MAP_TITLE = "%s";\n\n' % safe_title)
        f.write("const PLACES = [\n")
        n = 0
        for ep in episodes:
            has_coords = ep.get("lat") is not None and ep.get("lng") is not None
            has_video = bool(ep.get("video_url"))
            if matched_only and not has_video:
                continue
            if not has_coords:
                continue  # can't place it on the map without coordinates
            title = (ep.get("title") or "").replace('"', "'")
            location = (ep.get("location") or "").replace('"', "'")
            s, e = to_int(ep.get("season")), to_int(ep.get("episode"))
            f.write('  { title: "%s", location: "%s", season: %s, episode: %s, video: "%s", lat: %s, lng: %s },\n'
                    % (title, location,
                       s if s is not None else "null",
                       e if e is not None else "null",
                       ep.get("video_url", ""), ep["lat"], ep["lng"]))
            n += 1
        f.write("];\n")
    return n


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="icon" href="favicon.svg" type="image/svg+xml" />
<title>%(title)s &mdash; Map</title>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
<link rel="stylesheet" href="style.css" />
</head>
<body>
  <div class="titlebar" id="titlebar"></div>
  <div id="map"></div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
  <script src="%(datafile)s"></script>
  <script src="map.js"></script>
</body>
</html>
"""


def write_html_if_missing(path, map_title, datafile):
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(HTML_TEMPLATE % {"title": map_title, "datafile": datafile})
    return True


def add_to_index(html_file, name, note, index_path="index.html"):
    if not os.path.exists(index_path):
        return
    with open(index_path, encoding="utf-8") as f:
        text = f.read()
    if ('file: "%s"' % html_file) in text:
        return
    marker = "const CHANNELS = ["
    i = text.find(marker)
    if i == -1:
        print("(!) Couldn't find the CHANNELS list in index.html — add the card manually.")
        return
    at = i + len(marker)
    entry = '\n  { file: "%s", name: "%s", note: "%s" },' % (
        html_file, name.replace('"', "'"), (note or "").replace('"', "'"))
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(text[:at] + entry + text[at:])
    print("Added a card to index.html.")


def write_review_csv(episodes, path):
    fields = ["season", "episode", "title", "video_title", "location", "lat", "lng",
              "video_url", "match_method", "match_score"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for ep in episodes:
            w.writerow({k: (ep.get(k) if ep.get(k) is not None else "") for k in fields})


def main():
    ap = argparse.ArgumentParser(description="Match fetched channel videos to Wikipedia episodes and build the map data.")
    ap.add_argument("--episodes", default=os.path.join(DATA, "timeteam-episodes.json"), help="wiki_episodes.py output")
    ap.add_argument("--videos", default=os.path.join(DATA, "timeteam-classics.json"), help="fetch_channel.py output (accumulated videos)")
    ap.add_argument("--out", default="timeteam-classics", help="output slug (creates <slug>.js and <slug>.html at the site root)")
    ap.add_argument("--title", default=None, help="map heading (default: derived from --out)")
    ap.add_argument("--note", default="", help="description for the index.html card")
    ap.add_argument("--threshold", type=float, default=0.6, help="title-fallback strictness 0-1 (default 0.6)")
    ap.add_argument("--matched-only", action="store_true",
                    help="only map episodes that matched a video (default: every episode with coordinates)")
    ap.add_argument("--no-html", action="store_true", help="don't create the .html page")
    ap.add_argument("--no-index", action="store_true", help="don't touch index.html")
    ap.add_argument("--review", action="store_true", help="also write <slug>-review.csv with match details")
    args = ap.parse_args()

    try:
        with open(args.episodes, encoding="utf-8") as f:
            episodes = json.load(f)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run wiki_episodes.py first." % args.episodes)

    try:
        videos = load_videos(args.videos)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run fetch_channel.py --out %s first."
                 % (args.videos, args.videos[:-5] if args.videos.endswith(".json") else args.videos))

    slug = args.out[:-3] if args.out.endswith(".js") else args.out
    map_title = args.title or slug.replace("-", " ").replace("_", " ").title()

    print("Loaded %d videos; matching against %d episodes." % (len(videos), len(episodes)))
    match(episodes, videos, args.threshold)

    by_se = sum(1 for e in episodes if e.get("match_method") == "season/episode")
    by_title = sum(1 for e in episodes if e.get("match_method") == "title")

    # Site files (data file, page) live at the repo root; the .html/.js are siblings
    # so the page references the .js by its bare filename.
    js_name = slug + ".js"
    html_name = slug + ".html"
    n = write_js(episodes, os.path.join(ROOT, js_name), map_title, args.matched_only)
    print("\n%d of %d episodes matched a video (%d by season/episode, %d by title)."
          % (by_se + by_title, len(episodes), by_se, by_title))
    print("Wrote %s (%d markers — thumbnails where a video matched, pins otherwise)." % (js_name, n))

    if not args.no_html:
        if write_html_if_missing(os.path.join(ROOT, html_name), map_title, js_name):
            print("Created %s" % html_name)
    if not args.no_index:
        add_to_index(html_name, map_title, args.note, index_path=os.path.join(ROOT, "index.html"))
    if args.review:
        write_review_csv(episodes, os.path.join(DATA, slug + "-review.csv"))
        print("Wrote %s-review.csv" % slug)

    # Heads-up on episodes where more than one video shared the same S/E.
    dupes = [e for e in episodes if e.get("se_candidates", 0) > 1]
    if dupes:
        print("\n%d episode(s) had multiple videos with the same S/E (kept the closest title match):" % len(dupes))
        for e in dupes[:15]:
            print("  S%s E%s  %d videos -> chose: %s" % (e.get("season"), e.get("episode"),
                                                          e["se_candidates"], e["video_title"]))

    # Heads-up on the matches most likely to be wrong.
    shaky = [e for e in episodes if e.get("video_url") and
             (e["match_method"] == "title" or e["match_score"] < 0.5)]
    if shaky:
        print("\nWorth a check (%d) — matched but titles differ:" % len(shaky))
        for e in shaky[:15]:
            print("  [%s %.2f] wiki: %s" % (e["match_method"], e["match_score"], e["title"]))
            print("             yt:   %s" % e["video_title"])
        if len(shaky) > 15:
            print("  ... and %d more (use --review to see them all in a CSV)." % (len(shaky) - 15))

    print("\nNext: python make_previews.py")


if __name__ == "__main__":
    main()
