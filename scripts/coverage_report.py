#!/usr/bin/env python3
"""
coverage_report.py
------------------
Cross-reference the Wikipedia Time Team episode list against the videos found on
the channel, and produce a table of which episodes have and haven't turned up.

It uses the same matching as match_channel.py (season/episode first, then title),
but instead of building the map it writes a coverage report:

    timeteam-coverage.html   a sortable, readable table (open in a browser)
    timeteam-coverage.csv    the same data for a spreadsheet

Each row shows the episode (season, episode, title, location), whether it has
coordinates, whether a matching video was found, the YouTube title it matched,
and how it matched. A summary and a per-season breakdown sit at the top.

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python coverage_report.py
    python coverage_report.py --episodes timeteam-episodes.json --videos timeteam-classics.json

Options:
    --episodes FILE   wiki_episodes.py output (default timeteam-episodes.json)
    --videos FILE     fetch_channel.py output (default timeteam-classics.json)
    --out NAME        output filename prefix (default timeteam-coverage)
    --threshold N     title-fallback strictness 0-1 (default 0.6)
--------------------------------------------------------------------------
"""

import os
import sys
import csv
import json
import html
import argparse

import match_channel as mc  # reuse the matching logic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def season_key(ep):
    s = mc.to_int(ep.get("season"))
    e = mc.to_int(ep.get("episode"))
    return (s if s is not None else 999, e if e is not None else 999)


def build_rows(episodes):
    rows = []
    for ep in episodes:
        rows.append({
            "season": ep.get("season", ""),
            "episode": ep.get("episode", ""),
            "title": ep.get("title", ""),
            "location": ep.get("location", ""),
            "has_coords": ep.get("lat") is not None and ep.get("lng") is not None,
            "found": bool(ep.get("video_url")),
            "video_url": ep.get("video_url", ""),
            "video_title": ep.get("video_title", ""),
            "match_method": ep.get("match_method", ""),
            "match_score": ep.get("match_score", ""),
        })
    return rows


def write_csv(rows, path):
    fields = ["season", "episode", "title", "location", "has_coords", "found",
              "match_method", "match_score", "video_title", "video_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def per_season(rows):
    seasons = {}
    for r in rows:
        key = r["season"] if r["season"] != "" else "?"
        d = seasons.setdefault(key, {"total": 0, "found": 0})
        d["total"] += 1
        if r["found"]:
            d["found"] += 1
    return seasons


HTML_HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>%(title)s</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #1a1a1a; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .summary { color: #444; margin-bottom: 16px; }
  table { border-collapse: collapse; width: 100%%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
  th { position: sticky; top: 0; background: #f4f5f7; cursor: pointer; }
  tr.found td.status { color: #1a7f37; font-weight: 600; }
  tr.missing td.status { color: #b3261e; font-weight: 600; }
  tr.missing { background: #fff6f5; }
  .seasons { margin: 10px 0 22px; font-size: 13px; }
  .seasons span { display: inline-block; margin: 2px 10px 2px 0; }
  a { color: #1976d2; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .muted { color: #999; }
</style></head><body>
"""


def write_html(rows, path, title):
    total = len(rows)
    found = sum(1 for r in rows if r["found"])
    with_coords = sum(1 for r in rows if r["has_coords"])
    seasons = per_season(rows)

    def cell(s):
        return html.escape(str(s)) if s not in (None, "") else '<span class="muted">-</span>'

    parts = [HTML_HEAD % {"title": html.escape(title)}]
    parts.append("<h1>%s</h1>" % html.escape(title))
    pct = (100.0 * found / total) if total else 0
    parts.append('<div class="summary">%d episodes &middot; <strong>%d found</strong> (%.0f%%) &middot; '
                 '%d missing &middot; %d with coordinates</div>'
                 % (total, found, pct, total - found, with_coords))

    # Per-season breakdown
    parts.append('<div class="seasons"><strong>By series:</strong> ')
    for key in sorted(seasons, key=lambda k: (isinstance(k, str), k)):
        d = seasons[key]
        parts.append('<span>S%s: %d/%d</span>' % (html.escape(str(key)), d["found"], d["total"]))
    parts.append('</div>')

    # Table
    parts.append('<table><thead><tr>'
                 '<th>S</th><th>E</th><th>Episode title</th><th>Location</th>'
                 '<th>Coords</th><th>Status</th><th>Matched YouTube title</th><th>Match</th>'
                 '</tr></thead><tbody>')
    for r in rows:
        cls = "found" if r["found"] else "missing"
        status = "FOUND" if r["found"] else "missing"
        yt = cell(r["video_title"])
        if r["found"] and r["video_url"]:
            yt = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (
                html.escape(r["video_url"]), html.escape(r["video_title"] or "watch"))
        match = ""
        if r["found"]:
            match = "%s (%.2f)" % (r["match_method"], r["match_score"]) if r["match_score"] != "" else r["match_method"]
        parts.append('<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                     '<td>%s</td><td class="status">%s</td><td>%s</td><td>%s</td></tr>'
                     % (cls, cell(r["season"]), cell(r["episode"]), cell(r["title"]),
                        cell(r["location"]), "yes" if r["has_coords"] else "no",
                        status, yt, html.escape(match)))
    parts.append('</tbody></table>')

    # Tiny click-to-sort helper.
    parts.append("""
<script>
document.querySelectorAll('th').forEach((th, i) => th.addEventListener('click', () => {
  const tb = th.closest('table').querySelector('tbody');
  const rows = [...tb.rows];
  const asc = !(th.dataset.asc === 'true'); th.dataset.asc = asc;
  rows.sort((a, b) => {
    const x = a.cells[i].innerText, y = b.cells[i].innerText;
    const nx = parseFloat(x), ny = parseFloat(y);
    if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
    return asc ? x.localeCompare(y) : y.localeCompare(x);
  });
  rows.forEach(r => tb.appendChild(r));
}));
</script>
</body></html>""")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main():
    ap = argparse.ArgumentParser(description="Report which Time Team episodes have been found on the channel.")
    ap.add_argument("--episodes", default=os.path.join(DATA, "timeteam-episodes.json"))
    ap.add_argument("--videos", default=os.path.join(DATA, "timeteam-classics.json"))
    ap.add_argument("--out", default=os.path.join(DATA, "timeteam-coverage"))
    ap.add_argument("--threshold", type=float, default=0.6)
    args = ap.parse_args()

    try:
        with open(args.episodes, encoding="utf-8") as f:
            episodes = json.load(f)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run wiki_episodes.py first." % args.episodes)
    try:
        videos = mc.load_videos(args.videos)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run fetch_channel.py first." % args.videos)

    mc.match(episodes, videos, args.threshold)
    rows = build_rows(episodes)
    rows.sort(key=season_key)

    write_html(rows, args.out + ".html", "Time Team — episode coverage")
    write_csv(rows, args.out + ".csv")

    found = sum(1 for r in rows if r["found"])
    print("%d episodes, %d found, %d missing." % (len(rows), found, len(rows) - found))
    print("Wrote %s.html and %s.csv" % (args.out, args.out))


if __name__ == "__main__":
    main()
