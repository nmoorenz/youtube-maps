# YouTube Maps

Interactive maps built from YouTube channels. Each map places a video's
thumbnail as a marker at the location the video is about; clicking a thumbnail
opens the video on YouTube. A home page links to every channel map, and the
whole thing is a set of static files ready to deploy to Netlify.

## Folder layout

The **site** (everything served/deployed) lives at the root; the **tools** live
in `scripts/`; the **intermediate data** (fetched JSON, reports, working CSVs)
lives in `data/`.

```
youtube-maps/
  index.html                   Home page — lists every channel map
  style.css                    Shared styling for all map pages
  map.js                       Shared map renderer (Leaflet + OpenStreetMap)
  japanese-food-noodles.html   A channel page (thin: loads style.css + its data + map.js)
  japanese-food-noodles.js     That channel's data (MAP_TITLE + PLACES)
  japanese-food-noodles.png    That channel's home-page thumbnail
  timeteam-classics.{html,js,png}
  scripts/
    fetch_channel.py           Pulls video metadata from a channel
    extract_places.py          Pulls names + coordinates from video descriptions
    geocode.py                 Fills only the missing coordinates in a .js (non-destructive)
    parse_timeteam.py          Parses locations from Time Team titles into a CSV
    wiki_episodes.py           Builds a Time Team episode list (with coords) from Wikipedia
    match_channel.py           Matches channel videos to the episode list -> map data
    coverage_report.py         Reports which Time Team episodes have/haven't been found
    csv_to_map.py              Builds a map page from a curated CSV of places
    build_map.py               Builds a map page from a hand-picked list of links
    make_previews.py           Renders the home-page thumbnail images
  data/                        fetched JSON, episode list, reports, working CSVs
  README.md                    This file
```

Every channel is one `.html` page plus one `.js` data file at the root. The
heavy rendering logic lives once in `map.js`, so channel pages stay tiny and all
maps share a consistent look — change the design in `style.css` or `map.js`
and every map updates.

**Running the scripts:** run them from the `youtube-maps` folder as
`python scripts/<name>.py`. Each script reads/writes its intermediate data under
`data/` and writes the finished site files (`.js`, `.html`, `.png`, and the
`index.html` card) at the root, so you don't pass paths for the common case.
Only the web files at the root are deployed to Netlify; `scripts/` and `data/`
can stay in the repo but aren't needed by the live site.

## How a map page works

A channel page loads three scripts in order:

1. **Leaflet** — the mapping library (from CDN).
2. **The channel's data file** (e.g. `japanese-food-noodles.js`), which defines
   two globals: `MAP_TITLE` (a string) and `PLACES` (an array).
3. **`map.js`** — reads those globals and draws the map.

Each entry in `PLACES` looks like:

```js
{ title: "Shop name", video: "https://www.youtube.com/watch?v=VIDEO_ID", lat: 35.68, lng: 139.65 }
```

`video` can be a full YouTube URL or a bare 11-character video ID. The
thumbnail image is derived automatically from the video ID. Any entry whose
`lat` or `lng` is `null` is skipped, so you can build a map up gradually as you
fill in coordinates.

## Two ways to build a map's data

There are two starting points, depending on what you have:

- **A whole channel** — use `fetch_channel.py` (below). Best when you want every
  video from one channel.
- **A hand-picked list of links** — use `build_map.py` (further down). Best when
  you're collecting videos across different channels, or only want some of them.

Both produce the same `<slug>.js` data format, and in both cases you finish by
filling in `lat`/`lng` yourself (or, for the noodle-style channels, letting
`extract_places.py` resolve coordinates from the descriptions).

## Building a channel's data

The data files are generated from a channel in two steps.

### Prerequisites

```
pip install yt-dlp requests
```

### Step 1 — pull the videos

```
python scripts/fetch_channel.py "https://www.youtube.com/@Japanese_Food_Noodles" --out japanese-food-noodles
```

This writes two files into `data/`, sharing the `--out` prefix:

- `data/japanese-food-noodles.json` — full structured data including
  descriptions; the source of truth that the other scripts read
- `data/japanese-food-noodles.js` — a starter map data file (coords left `null`)

By default the script **resumes**: it lists the whole channel, then fetches only
the videos not already in `<out>.json`. Options: `--limit N` fetches at most N
*new* videos this run — because it resumes, running again grabs the next N, so
repeated runs accumulate the channel a batch at a time (useful for avoiding rate
limits); `--title "..."` sets the `MAP_TITLE`; `--sleep N` pauses N seconds
between videos (default 1.0); `--fresh` ignores any existing `<out>.json` and
re-fetches everything.

On large channels YouTube may rate-limit a fast run, which shows up as
`Video unavailable … rate-limited` warnings and causes those videos to be
skipped (the run finishes but is incomplete). If that happens, wait about an
hour for the limit to reset, then just run the same command again — because it
resumes by default, it fills in only the videos that were missed (increase
`--sleep` if it keeps happening).

### Step 2 — extract shops and coordinates

```
python scripts/extract_places.py --json data/japanese-food-noodles.json --resolve --js japanese-food-noodles.js --title "Japanese Food Noodles"
```

This reads each video's description, pulls out the shop name, Google Maps link,
video ID, and address, then follows each maps link to resolve latitude and
longitude. It writes `data/places.csv` (for review) and the site data file
`japanese-food-noodles.js` at the root — with the shop name, its **location**
(address, shown as a second line in the hover label), video link, and coords.

It's **non-destructive**: on a re-run it keeps every existing entry's title,
coordinates and order, only adding a `location` where missing and filling null
coords it manages to resolve. New shops are appended (obvious parse failures —
a "name" that's a paragraph or a URL — are skipped). So your hand-edited
titles/coords are safe, and you can re-run any time. Use `geocode.py` to top up
just the still-missing coordinates later.

The parser understands the common description format:

```
Shop Name  <name>   Map  <maps link>   Address  <address>
```

It handles the `Shop Name` / `Store Name` / `Name` label variants, full-width
or colon separators, YouTube redirect links (the real maps URL is taken from
the redirect's `q=` parameter, and the video ID from `v=`), and truncated
display links.

Run without `--resolve` first to confirm the names and links parse correctly,
then add `--resolve` to fetch coordinates. Resolution needs an internet
connection and pauses briefly between links.

#### Filling gaps later with geocode.py

`extract_places.py` rewrites the whole `.js`. Once you've started hand-editing
coordinates, use `geocode.py` instead to top up only what's missing — it's
non-destructive:

```
python scripts/geocode.py japanese-food-noodles.js --country jp
```

It scans the `.js` for entries whose `lat`/`lng` are still `null`, looks each one
up by title in the matching `.json` (using the description's maps link, then its
address), and writes coordinates back **only** for those entries — everything you
already set is left exactly as-is. It's safe to run repeatedly. Use `--dry-run`
to preview, `--country CC` to bias address lookups, and `--guess-from-title` as a
last resort (off by default, since a bare name can land on the wrong place).
Whatever it still can't resolve, fill in by hand in the `.js`.

**If a channel's descriptions don't use this format:** `extract_places.py`
keys off the `Shop Name` / `Store Name` / `Name` labels, so if a channel
doesn't include them (or has a maps link with no name label), it simply finds
nothing for those videos — it won't error, it just returns empty results. In
that case, skip Step 2 entirely: the starter `japanese-food-noodles.js` from
Step 1 already lists every video with its **video title** as the marker name
and `lat`/`lng` set to `null`, so you can just fill in coordinates by hand.
Note that `fetch_channel.py` itself never parses descriptions, so it works on
any channel regardless of format.

### Channel-specific parsers

Some channels put the location in the title rather than the description.
`parse_timeteam.py` is an example for the Time Team Classics channel: it reads
the `fetch_channel.py` JSON and parses each title for a bracketed location and a
season/episode marker (e.g. `S7 ep7`, `Series 3 Episode 4`), geocodes the
location via OpenStreetMap (UK-biased), and writes a CSV with columns
`video_url, title, location, lat, lng, season, episode` for you to curate.

```
python scripts/fetch_channel.py "https://www.youtube.com/@TimeTeamClassics" --out timeteam-classics
python scripts/parse_timeteam.py    # reads data/timeteam-classics.json -> data/timeteam-classics.csv
```

Options: `--no-geocode` to skip coordinate lookup, `--no-uk-bias` to search
worldwide, and `--demo` to see the title parsing on built-in examples.

#### Better route for Time Team: start from Wikipedia

Wikipedia's [List of Time Team episodes](https://en.wikipedia.org/wiki/List_of_Time_Team_episodes)
already lists the dig location **and decimal coordinates** for almost every
episode, which is far more reliable than parsing YouTube titles or geocoding.
The recommended flow:

```
# 1. Once (rare updates): build the episode list from Wikipedia
python scripts/wiki_episodes.py                                             # -> data/timeteam-episodes.json (coords + season)

# 2. Accumulate the channel's videos (resumes each run)
python scripts/fetch_channel.py "https://www.youtube.com/@TimeTeamClassics" --out timeteam-classics   # -> data/timeteam-classics.json

# 3. Match videos to episodes and build the map (no network — reads the two JSON files)
python scripts/match_channel.py --title "Time Team Classics"                # -> timeteam-classics.js (+ .html, index card)

# 4. Refresh the thumbnail (UK & Ireland frame)
python scripts/make_previews.py timeteam-classics.js --region uk

# (optional) see which episodes have / haven't been found
python scripts/coverage_report.py                                           # -> data/timeteam-coverage.html
```

The steps are independent: step 1 rarely changes, step 2 accumulates videos
over time, and steps 3-4 just re-read whatever's on disk.

**The map is based on the Wikipedia episode list, not the fetch.** Every episode
that has coordinates becomes a marker: a clickable video thumbnail where a
channel video matched, or a plain location pin where it hasn't (yet). The fetched
channel only supplies the video links. So the map is complete from day one and
fills in with thumbnails as you accumulate videos. Use `--matched-only` if you'd
rather show just the episodes that have a video.

`wiki_episodes.py` parses Wikipedia (standard library only). `fetch_channel.py`
pulls and accumulates the channel's videos into `timeteam-classics.json`.
`match_channel.py` reads that JSON plus the episode list (no network of its own),
attaches a `video_url` to each episode, and writes the map directly. It matches
on **season + episode first**
(reading the `S7 E7` marker from the video title, the most reliable signal for
Time Team) and falls back to title similarity when there's no marker. Not every
episode is on the channel, so unmatched ones keep a blank `video_url` (add
`--matched-only` to drop them, or `--threshold` to tune the title fallback).

If several videos share the same S/E (e.g. a full episode and a highlights clip),
it keeps the one whose title best matches the Wikipedia episode and prints the
duplicates so you can check. It also prints a "worth a check" list of matches
where the two titles differ (a `season/episode` match with a low title score, or
a title-only match); pass `--review` to dump those details to a CSV.

Note: for episodes that list several dig sites, only the **first** coordinate in
the Wikipedia cell is used.

Once you've reviewed and fixed the CSV, turn it into a map page with
`csv_to_map.py`:

```
python scripts/csv_to_map.py data/timeteam-classics.csv --title "Time Team Classics" --note "UK archaeology digs"
```

That writes `timeteam-classics.js` and `timeteam-classics.html`, and adds a card
to `index.html`. Each marker's hover label shows up to three lines — title, then
location, then `Sx Ey` — using whichever of those columns are present.
`csv_to_map.py` works for any curated CSV with `title`, `video_url`, `location`,
`lat`, `lng` (and optional `season`/`episode`) columns, not just Time Team.
Finish by running `make_previews.py` to generate the home-page thumbnail.

## Building a map from a list of links

Use this when your videos come from several channels, or you only want a
selection. Paste your links into a text file — one per line, blank lines and
`#` comments ignored — in any common format:

```
# my mixed list
https://www.youtube.com/watch?v=CzTVxom0asE
https://youtu.be/JtzB9KSB1Fk
https://www.youtube.com/shorts/2PA7fok3TFs
CzTVxom0asE
```

Then run:

```
python scripts/build_map.py my-links.txt --out tokyo-eats --title "Tokyo Eats" --note "Spots to try"
```

This extracts and de-duplicates the video IDs, looks up each video's title
(used as the marker name), and creates `tokyo-eats.html` and `tokyo-eats.js`.
It also adds a card for the new map to `index.html` automatically. Coordinates
are left as `null` for you to fill in by hand.

Title lookup uses YouTube's oEmbed endpoint (needs internet and `requests`; no
API key). Add `--no-titles` to skip it and use `Video <id>` placeholders you
can rename, or `--no-index` to leave `index.html` untouched.

## Adding a new map by hand

`build_map.py` creates the `.html`, the `.js`, and the `index.html` card for
you, so this manual process is only needed if you want to build one from
scratch:

1. Copy `japanese-food-noodles.html` to `<slug>.html` and update the two
   filenames inside it (the `<title>` and the `<script src>` pointing at the
   data file).
2. Create `<slug>.js` defining `MAP_TITLE` and `PLACES` (use an existing data
   file as a template).
3. Add one entry to the `CHANNELS` list near the top of the script block in
   `index.html`:

   ```js
   { file: "<slug>.html", name: "Map name", note: "Short description" },
   ```

## Home page thumbnails

Each card on `index.html` shows a small static map image of that channel's
area, named after the page (e.g. `japanese-food-noodles.png`). Generate or
refresh them with:

```
pip install staticmap
python scripts/make_previews.py
```

This reads every channel's coordinates, computes the bounding box, and renders
a no-marker PNG fitted to it (no API key — it uses OpenStreetMap tiles).
Options: `--width` / `--height` for image size, `--max-zoom` to limit how tight
a single-location map zooms in, and `--dry-run` to preview the numbers without
rendering. Re-run it whenever a channel's coordinates change, and commit the
PNGs alongside the pages. If a preview image is missing, the card simply hides
the thumbnail and shows the name and note.

To **force a fixed frame** instead of fitting to the markers — useful when a
channel has a few far-flung points that would zoom the thumbnail right out (e.g.
Time Team's overseas digs) — pass `--region` or `--bbox`, and name the specific
file so only that thumbnail is reframed:

```
python scripts/make_previews.py timeteam-classics.js --region uk
```

Named regions: `uk` / `uk-ireland` (main landmass), `uk-full` (adds Channel
Islands & Shetland), `gb`, `japan`. Or give your own box with
`--bbox "min_lat,min_lng,max_lat,max_lng"`.

## Running locally

Open any `.html` file in a browser by double-clicking it. The data files are
plain `.js` loaded via `<script>` tags, so everything works from the local file
system — no server required. (The map tiles and thumbnails load from the
internet, so you need a connection to see them.)

## Deploying to Netlify

Deploy the `youtube-maps` folder as the site root. `index.html` becomes the
landing page and each channel map is reachable at `/<slug>.html`. No build
command or configuration is needed — it's a static site.

To have Netlify redeploy automatically on changes, put the folder in a GitHub
repository and connect the repo to Netlify (leave the build command blank and
the publish directory as the root).

## Notes and limits

- Coordinate resolution follows short links (`maps.app.goo.gl`). Occasionally a
  link lands on a Google consent page instead of the map; those rows come back
  with blank coordinates in `places.csv`, and you can fill them in by opening
  the link in a browser and copying the numbers.
- `map.js`, `style.css`, and Leaflet are shared, so a visual change in one place
  applies to every channel map.
