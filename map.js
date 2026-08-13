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

  // Title bar with a link back to the home page.
  const bar = document.getElementById("titlebar");
  if (bar) {
    bar.innerHTML =
      `<a href="index.html">&larr; All maps</a>` +
      `&nbsp;&nbsp;${title} ` +
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

  // Escape text before putting it into HTML (labels come from data).
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // Build the hover label. Up to three lines: title, location, "Sx Ey".
  // Points that only have a title (e.g. the noodle map) show a single line.
  function labelHTML(place) {
    const lines = [];
    if (place.title) lines.push('<strong>' + esc(place.title) + '</strong>');
    if (place.location) lines.push(esc(place.location));
    const s = place.season, e = place.episode;
    if (s !== undefined && s !== null && s !== "" &&
        e !== undefined && e !== null && e !== "") {
      lines.push("S" + esc(s) + " E" + esc(e));
    }
    return lines.join("<br>");
  }

  const map = L.map("map", { scrollWheelZoom: true });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const bounds = [];
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
  });

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [60, 60] });
  } else {
    map.setView([20, 0], 2);
  }

  if (unplaced > 0) {
    console.info(`${unplaced} video(s) have no coordinates yet and were not shown.`);
  }
})();
