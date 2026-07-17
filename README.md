# YouTube Maps

Interactive maps built from YouTube channels. Each map places a video's
thumbnail as a marker at the location the video is about; clicking a thumbnail
opens the video on YouTube. A home page links to every channel map, and the
whole thing is a set of static files ready to deploy to Netlify.

## Folder layout

```
youtube-maps/
  index.html                   Home page — lists every channel map
  style.css                    Shared styling for all map pages
  map.js                       Shared map renderer (Leaflet + OpenStreetMap)
  japanese-food-noodles.html   A channel page (thin: loads style.css + its data + map.js)
  japanese-food-noodles.js     That channel's data (MAP_TITLE + PLACES)
  fetch_channel.py             Pulls video metadata from a channel
  extract_places.py            Pulls names + coordinates from video descriptions
  build_map.py                 Builds a map page from a hand-picked list of links
  README.md                    This file
```

Every channel is one `.html` page plus one `.js` data file. The heavy
rendering logic lives once in `map.js`, so channel pages stay tiny and all
maps share a consistent look — change the design in `style.css` or `map.js`
and every map updates.

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
python fetch_channel.py "https://www.youtube.com/@Japanese_Food_Noodles" --out japanese-food-noodles
```

This writes three files sharing the `--out` prefix:

- `japanese-food-noodles.csv` — every video's title, date, URL, and description
- `japanese-food-noodles.json` — the same data, structured
- `japanese-food-noodles.js` — a starter map data file (coordinates left `null`)

Options: `--limit N` fetches only the N most recent videos (useful for a quick
test); `--title "..."` sets the `MAP_TITLE`.

### Step 2 — extract shops and coordinates

```
python extract_places.py --json japanese-food-noodles.json --resolve --js japanese-food-noodles.js --title "Japanese Food Noodles"
```

This reads each video's description, pulls out the shop name, Google Maps link,
video ID, and address, then follows each maps link to resolve latitude and
longitude. It writes `places.csv` (for review) and overwrites
`japanese-food-noodles.js` with real names, video links, and coordinates.

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

**If a channel's descriptions don't use this format:** `extract_places.py`
keys off the `Shop Name` / `Store Name` / `Name` labels, so if a channel
doesn't include them (or has a maps link with no name label), it simply finds
nothing for those videos — it won't error, it just returns empty results. In
that case, skip Step 2 entirely: the starter `japanese-food-noodles.js` from
Step 1 already lists every video with its **video title** as the marker name
and `lat`/`lng` set to `null`, so you can just fill in coordinates by hand.
Note that `fetch_channel.py` itself never parses descriptions, so it works on
any channel regardless of format.

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
python build_map.py my-links.txt --out tokyo-eats --title "Tokyo Eats" --note "Spots to try"
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
