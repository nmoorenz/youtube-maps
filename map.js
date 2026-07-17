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
    if (id === null) {
      console.warn("Skipping (couldn't read a video ID):", place.title, place.video);
      return;
    }

    const thumb = `https://img.youtube.com/vi/${id}/hqdefault.jpg`;
    const watchUrl = `https://www.youtube.com/watch?v=${id}`;
    const safeTitle = (place.title || "").replace(/"/g, "&quot;");

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
    marker.bindTooltip(place.title || "", { className: "yt-tip", direction: "top", offset: [0, -34] });
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
