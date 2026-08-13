#!/usr/bin/env python3
"""
update_timeteam.py
------------------
One command to bring the Time Team map up to date and report coverage.

It runs, in order:
  1. wiki_episodes.py     — refresh the released-episode list from Wikipedia
  2. fetch_channel.py     — pull any new uploads (resumes; only fetches new ones)
  3. match_channel.py     — rebuild the map data (timeteam-classics.js)
  4. make_previews.py     — refresh the home-page thumbnail (UK & Ireland frame)
  5. coverage_report.py   — write the found/missing comparison

The coverage summary (how many released, how many found/missing) prints last.

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python scripts/update_timeteam.py

Just want the numbers, not a map rebuild:
    python scripts/update_timeteam.py --coverage-only

Options:
    --coverage-only   skip the map/thumbnail rebuild (steps 3-4)
    --skip-fetch      don't pull new videos; use what's already fetched
    --limit N         fetch at most N new videos this run (passed to fetch_channel)
    --sleep N         seconds between video fetches (passed to fetch_channel)
    --channel URL     channel to fetch (default: @TimeTeamClassics)
    --out SLUG        data/map slug (default: timeteam-classics)
    --title TEXT      map heading (default: "Time Team Classics")
    --region NAME     thumbnail frame (default: uk)
    --dry-run         print the steps it would run, without running them
--------------------------------------------------------------------------
"""

import os
import sys
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))   # the scripts/ folder
ROOT = os.path.dirname(HERE)                         # repo root
PY = sys.executable


def main():
    ap = argparse.ArgumentParser(description="Update the Time Team map and coverage report.")
    ap.add_argument("--coverage-only", action="store_true", help="skip the map/thumbnail rebuild")
    ap.add_argument("--skip-fetch", action="store_true", help="don't pull new videos")
    ap.add_argument("--limit", type=int, default=None, help="max new videos to fetch this run")
    ap.add_argument("--sleep", type=float, default=None, help="seconds between video fetches")
    ap.add_argument("--channel", default="https://www.youtube.com/@TimeTeamClassics")
    ap.add_argument("--out", default="timeteam-classics")
    ap.add_argument("--title", default="Time Team Classics")
    ap.add_argument("--region", default="uk")
    ap.add_argument("--dry-run", action="store_true", help="print the steps without running them")
    args = ap.parse_args()

    def script(name):
        return os.path.join(HERE, name)

    # Build the ordered list of (description, argv) steps.
    steps = []
    steps.append(("Refresh episode list from Wikipedia", [script("wiki_episodes.py")]))

    if not args.skip_fetch:
        fetch = [script("fetch_channel.py"), args.channel, "--out", args.out]
        if args.limit is not None:
            fetch += ["--limit", str(args.limit)]
        if args.sleep is not None:
            fetch += ["--sleep", str(args.sleep)]
        steps.append(("Fetch new channel videos", fetch))

    if not args.coverage_only:
        steps.append(("Rebuild the map data", [script("match_channel.py"), "--title", args.title, "--out", args.out]))
        steps.append(("Refresh the thumbnail", [script("make_previews.py"), args.out + ".js", "--region", args.region]))

    steps.append(("Coverage comparison", [script("coverage_report.py")]))

    for i, (desc, argv) in enumerate(steps, 1):
        header = "[%d/%d] %s" % (i, len(steps), desc)
        if args.dry_run:
            print(header)
            print("      " + " ".join(os.path.basename(a) if a.startswith(HERE) else a for a in [PY] + argv))
            continue
        print("\n=== %s ===" % header, flush=True)
        result = subprocess.run([PY] + argv, cwd=ROOT)
        if result.returncode != 0:
            sys.exit("\nStopped: step '%s' failed (exit %d)." % (desc, result.returncode))

    if not args.dry_run:
        print("\nDone. Full table: data/timeteam-coverage.html")
        if not args.coverage_only:
            print("Updated site files: %s.js, %s.png (and index.html if new)." % (args.out, args.out))


if __name__ == "__main__":
    main()
