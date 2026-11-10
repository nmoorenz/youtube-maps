/* =========================================================================
   Shared map renderer for all channel pages.
   -------------------------------------------------------------------------
   Each channel page loads (in this order):
     1. Leaflet
     2. its data file  (defines  MAP_TITLE  and  PLACES)
     3. this file (map.js)

   PLACES entries look like:
     { title, video, lat, lng }
   where `video` is a full YouTube URL or a bare 11-char video ID.
   Entries with null/missing lat or lng are skipped (and counted) so you can
   drop in raw script output and fill coordinates in gradually.
   ========================================================================= */

(function () {
  const places = (typeof PLACES !== "undefined") ? PLACES : [];
  const title = (typeof MAP_TITLE !== "undefined") ? MAP_TITLE : "YouTube Map";
  // Optional per-channel links, e.g. [{href,label}, ...], set by the page.
  const extraLinks = (typeof MAP_LINKS !== "undefined" && Array.isArray(MAP_LINKS)) ? MAP_LINKS : [];

  // Escape text before putting it into HTML (labels come from data).
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // Title bar with a link back to the home page, plus any per-channel links.
  const bar = document.getElementById("titlebar");
  if (bar) {
    const links = extraLinks
      .map((l) => ` &middot; <a href="${esc(l.href)}">${esc(l.label)}</a>`)
      .join("");
    bar.innerHTML =
      `<a href="index.html">&larr; All maps</a>` + links +
      `&nbsp;&nbsp;${esc(title)} ` +
      `<span class="hint">— click a thumbnail to watch on YouTube</span>`;
  }
  document.title = `${title} — Map`;

  // Extract an 11-char video ID from either a URL or a raw ID.
  function getVideoId(input) {
    if (!input) return null;
    input = String(input).trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(input)) return input;
    const m = input.match(/(?:v=|\/embed\/|youtu\.be\/|\/shorts\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }

  // Build the hover label. Up to three lines: title, location, "Sx Ey".
  // Points that only have a title (e.g. the noodle map) show a single line.
  function labelHTML(place) {
    const lines = [];
    if (place.title) lines.push('<strong>' + esc(place.title) + '</strong>');
    // Show the YouTube title too, when it differs from the episode title.
    if (place.video_title && place.video_title !== place.title) {
      lines.push('<span class="yt-sub">' + esc(place.video_title) + '</span>');
    }
    if (place.location) lines.push(esc(place.location));
    const s = place.season, e = place.episode;
    if (s !== undefined && s !== null && s !== "" &&
        e !== undefined && e !== null && e !== "") {
      lines.push("S" + esc(s) + " E" + esc(e));
    }
    return lines.join("<br>");
  }

  // Searchable text for a place: episode title, YouTube title, location,
  // and "s7 e7" / "s7e7" forms.
  function searchText(p) {
    let t = (p.title || "") + " " + (p.video_title || "") + " " + (p.location || "");
    const s = p.season, e = p.episode;
    if (s !== undefined && s !== null && s !== "" &&
        e !== undefined && e !== null && e !== "") {
      t += " s" + s + " e" + e + " s" + s + "e" + e;
    }
    return t.toLowerCase();
  }

  // A search box (top-right) that jumps the map to a matching marker.
  function buildSearch(entries) {
    if (!entries.length) return;
    entries.forEach((en) => (en._text = searchText(en.place)));

    const box = document.createElement("div");
    box.className = "map-search";
    box.innerHTML =
      '<input type="text" placeholder="Search&hellip;" aria-label="Search places" />' +
      '<div class="map-search-results" hidden></div>';
    document.body.appendChild(box);
    const input = box.querySelector("input");
    const list = box.querySelector(".map-search-results");
    let matches = [];

    function render(q) {
      if (!q) { list.hidden = true; list.innerHTML = ""; return; }
      matches = entries.filter((en) => en._text.indexOf(q) !== -1).slice(0, 15);
      if (!matches.length) {
        list.innerHTML = '<div class="map-search-empty">No match</div>';
      } else {
        list.innerHTML = matches.map((en, i) => {
          const p = en.place;
          const se = (p.season !== undefined && p.season !== null && p.season !== "" &&
                      p.episode !== undefined && p.episode !== null && p.episode !== "")
            ? " &middot; S" + esc(p.season) + " E" + esc(p.episode) : "";
          const loc = p.location ? '<span class="r-loc">' + esc(p.location) + "</span>" : "";
          const yt = (p.video_title && p.video_title !== p.title)
            ? '<span class="r-yt">' + esc(p.video_title) + "</span>" : "";
          return '<div class="map-search-item" data-i="' + i + '">' +
                 '<span class="r-title">' + esc(p.title || "") + se + "</span>" + yt + loc + "</div>";
        }).join("");
      }
      list.hidden = false;
    }

    function focus(en) {
      if (!en) return;
      map.setView([en.lat, en.lng], Math.max(map.getZoom(), 13));
      en.marker.openTooltip();
      list.hidden = true;
    }

    input.addEventListener("input", () => render(input.value.trim().toLowerCase()));
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") focus(matches[0]);
      else if (ev.key === "Escape") { input.value = ""; list.hidden = true; }
    });
    list.addEventListener("click", (ev) => {
      const item = ev.target.closest(".map-search-item");
      if (item) focus(matches[+item.dataset.i]);
    });
    document.addEventListener("click", (ev) => { if (!box.contains(ev.target)) list.hidden = true; });
  }

  const map = L.map("map", { scrollWheelZoom: true });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const bounds = [];
  const entries = [];   // { marker, lat, lng, place } for the search box
  let unplaced = 0;

  places.forEach((place) => {
    if (place.lat == null || place.lng == null) {
      unplaced++;
      return; // no coordinates yet — skip
    }
    const id = getVideoId(place.video);
    const tip = labelHTML(place);
    const safeTitle = esc(place.title);

    // No video (yet): show a plain location pin so the place still appears on the map.
    if (id === null) {
      const dot = L.divIcon({
        className: "",
        html: `<div class="loc-marker"></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      });
      const m = L.marker([place.lat, place.lng], { icon: dot }).addTo(map);
      m.bindTooltip(tip, { className: "yt-tip", direction: "top", offset: [0, -10] });
      bounds.push([place.lat, place.lng]);
      entries.push({ marker: m, lat: place.lat, lng: place.lng, place });
      return;
    }

    const thumb = `https://img.youtube.com/vi/${id}/hqdefault.jpg`;
    const watchUrl = `https://www.youtube.com/watch?v=${id}`;

    const html = `
      <div class="yt-marker" title="${safeTitle}">
        <img src="${thumb}" alt="${safeTitle}"
             onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
        <div class="fallback">${safeTitle}</div>
        <div class="play"></div>
      </div>`;

    const icon = L.divIcon({
      className: "",
      html: html,
      iconSize: [96, 64],
      iconAnchor: [48, 32],
    });

    const marker = L.marker([place.lat, place.lng], { icon }).addTo(map);
    marker.bindTooltip(tip, { className: "yt-tip", direction: "top", offset: [0, -34] });
    marker.on("click", () => window.open(watchUrl, "_blank", "noopener"));

    bounds.push([place.lat, place.lng]);
    entries.push({ marker, lat: place.lat, lng: place.lng, place });
  });

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [60, 60] });
  } else {
    map.setView([20, 0], 2);
  }

  buildSearch(entries);

  if (unplaced > 0) {
    console.info(`${unplaced} video(s) have no coordinates yet and were not shown.`);
  }
})();
