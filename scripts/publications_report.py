#!/usr/bin/env python3
"""
publications_report.py
----------------------
List every Time Team video on the channel, newest upload first, with how many
times that episode had already been published before it.

Time Team re-posts episodes (full version, clips, re-uploads). For each video we
look at its season/episode marker and count how many OTHER uploads of the same
episode went up earlier. So a brand-new episode shows "0 published before"; the
third re-upload of an old one shows "2". Handy for spotting, among the most
recent uploads, which are genuinely new vs re-releases.

Reads what fetch_channel.py already produced:
    data/timeteam-classics.json   fetched channel videos

Writes:
    timeteam-uploads.html   sortable list, newest first (at the site root)
    data/timeteam-uploads.csv    same data

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python scripts/publications_report.py
--------------------------------------------------------------------------
"""

import os
import sys
import csv
import json
import html
import argparse

import match_channel as mc  # parse_se

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def fmt_date(d):
    d = str(d or "")
    return "%s-%s-%s" % (d[0:4], d[4:6], d[6:8]) if len(d) == 8 and d.isdigit() else (d or "")


def build(videos):
    """Return one row per video, newest first, with a `before` count."""
    rows = []
    for v in videos:
        title = v.get("title", "") or ""
        vid = v.get("id", "")
        rows.append({
            "title": title,
            "url": v.get("url") or ("https://www.youtube.com/watch?v=" + vid if vid else ""),
            "date": v.get("upload_date", "") or "",
            "se": mc.parse_se(title),            # (season, episode) or None
        })

    # Group upload dates by episode so we can count earlier uploads.
    dates_by_se = {}
    for r in rows:
        if r["se"]:
            dates_by_se.setdefault(r["se"], []).append(r["date"])

    for r in rows:
        if r["se"]:
            r["before"] = sum(1 for d in dates_by_se[r["se"]] if d and r["date"] and d < r["date"])
        else:
            r["before"] = None                   # no marker -> can't tell

    rows.sort(key=lambda r: r["date"] or "", reverse=True)   # most recent first
    return rows


HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="icon" href="favicon.svg" type="image/svg+xml" />
<title>%(title)s</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #1a1a1a; }
  nav.nav { font-size: 13px; margin: 0 0 16px; }
  nav.nav a { margin-right: 2px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .summary { color: #444; margin-bottom: 16px; }
  table { border-collapse: collapse; width: 100%%; font-size: 13px; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
  th { position: sticky; top: 0; background: #f4f5f7; cursor: pointer; }
  td.num { text-align: center; font-variant-numeric: tabular-nums; }
  td.before { font-weight: 700; }
  tr.new td.before { color: #1a7f37; }
  tr.repost td.before { color: #b26a00; }
  .date { color: #666; font-variant-numeric: tabular-nums; white-space: nowrap; }
  a { color: #1976d2; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .muted { color: #bbb; }
</style></head><body>
"""

SORT_JS = """
<script>
document.querySelectorAll('th').forEach((th) => th.addEventListener('click', () => {
  const tb = th.closest('table').querySelector('tbody');
  const idx = [...th.parentNode.children].indexOf(th);
  const rows = [...tb.rows];
  const asc = !(th.dataset.asc === 'true'); th.dataset.asc = asc;
  rows.sort((a, b) => {
    const x = a.cells[idx].dataset.sort ?? a.cells[idx].innerText;
    const y = b.cells[idx].dataset.sort ?? b.cells[idx].innerText;
    const nx = parseFloat(x), ny = parseFloat(y);
    if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
    return asc ? String(x).localeCompare(y) : String(y).localeCompare(x);
  });
  rows.forEach(r => tb.appendChild(r));
}));
</script>
</body></html>"""


NAV = ('<nav class="nav"><a href="index.html">&larr; All maps</a> &middot; '
       '<a href="timeteam-classics.html">Map</a> &middot; '
       '<a href="timeteam-coverage.html">Coverage</a> &middot; '
       '<a href="timeteam-uploads.html">Uploads</a></nav>')


def se_label(se):
    return "S%d E%d" % se if se else ""


def write_html(rows, path, title):
    with_se = [r for r in rows if r["se"]]
    new_eps = sum(1 for r in with_se if r["before"] == 0)
    reposts = sum(1 for r in with_se if r["before"] and r["before"] > 0)
    parts = [HEAD % {"title": html.escape(title)}]
    parts.append(NAV)
    parts.append("<h1>%s</h1>" % html.escape(title))
    parts.append('<div class="summary">%d videos &middot; newest first &middot; '
                 '<strong>%d are the first upload of their episode</strong> &middot; '
                 '%d are re-uploads of an episode posted earlier</div>' % (len(rows), new_eps, reposts))

    parts.append('<table><thead><tr>'
                 '<th>Uploaded</th><th>S/E</th><th>YouTube title</th><th>Published before</th>'
                 '</tr></thead><tbody>')
    for r in rows:
        if r["before"] is None:
            cls, before_cell = "", '<span class="muted">-</span>'
            before_sort = -1
        else:
            cls = "new" if r["before"] == 0 else "repost"
            before_cell = str(r["before"])
            before_sort = r["before"]
        s, e = (r["se"] or (0, 0))
        se_sort = "%03d%03d" % (s, e) if r["se"] else ""
        title_cell = ('<a href="%s" target="_blank" rel="noopener">%s</a>'
                      % (html.escape(r["url"]), html.escape(r["title"]))) if r["url"] else html.escape(r["title"])
        parts.append('<tr class="%s">'
                     '<td class="date" data-sort="%s">%s</td>'
                     '<td data-sort="%s">%s</td>'
                     '<td>%s</td>'
                     '<td class="num before" data-sort="%d">%s</td></tr>'
                     % (cls, r["date"], html.escape(fmt_date(r["date"])),
                        se_sort, html.escape(se_label(r["se"])),
                        title_cell, before_sort, before_cell))
    parts.append('</tbody></table>')
    parts.append(SORT_JS)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["upload_date", "season", "episode", "title", "published_before", "url"])
        for r in rows:
            s, e = (r["se"] or ("", ""))
            w.writerow([fmt_date(r["date"]), s, e, r["title"],
                        "" if r["before"] is None else r["before"], r["url"]])


def main():
    ap = argparse.ArgumentParser(description="List Time Team videos newest-first with their republish count.")
    ap.add_argument("--videos", default=os.path.join(DATA, "timeteam-classics.json"))
    ap.add_argument("--slug", default="timeteam-uploads",
                    help="output basename: HTML goes to the site root, CSV to data/")
    args = ap.parse_args()

    try:
        with open(args.videos, encoding="utf-8") as f:
            videos = json.load(f)
    except FileNotFoundError:
        sys.exit("Couldn't find %s. Run fetch_channel.py first." % args.videos)

    rows = build(videos)
    html_path = os.path.join(ROOT, args.slug + ".html")
    csv_path = os.path.join(DATA, args.slug + ".csv")
    write_html(rows, html_path, "Time Team — videos by upload date")
    write_csv(rows, csv_path)

    new_eps = sum(1 for r in rows if r["se"] and r["before"] == 0)
    print("%d videos; %d are a first upload, %d are re-uploads." % (len(rows), new_eps, len(rows) - new_eps))
    print("Wrote %s and %s" % (html_path, csv_path))


if __name__ == "__main__":
    main()
