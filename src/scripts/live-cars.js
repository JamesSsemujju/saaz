/* live-cars.js: shows live Saaz cars on the public /cars/ page, straight from the marketplace database.
   Each card opens the car in the Saaz app. /car/?ref=... forwards to the app too.
   When the database isn't configured, the page keeps whatever the build put there. */
(function () {
  var C = window.SAAZ || {};
  var base = C.base || "/";
  var idx = C.fileLinks ? "index.html" : "";
  var app = base + "app/" + idx;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function money(cur, n) { return cur + " " + Number(n).toLocaleString("en-US"); }

  var ref = new URLSearchParams(location.search).get("ref");
  if (document.getElementById("cardetail")) { location.replace(app + (ref ? "#/car/" + encodeURIComponent(ref) : "#/browse")); return; }

  var list = document.getElementById("carlist");
  if (!list) return;
  function loadFilters() { var s = document.createElement("script"); s.src = base + "assets/cars.js"; document.body.appendChild(s); }
  if (!(C.supabaseUrl && C.supabaseAnonKey)) { if (list.children.length) loadFilters(); return; }

  fetch(C.supabaseUrl + "/rest/v1/rpc/browse_listings", {
    method: "POST", headers: { apikey: C.supabaseAnonKey, Authorization: "Bearer " + C.supabaseAnonKey, "Content-Type": "application/json" },
    body: JSON.stringify({ p_country: null })
  }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (rows) {
    if (!rows.length) { if (list.children.length) loadFilters(); return; }
    list.insertAdjacentHTML("afterbegin", rows.map(function (l) {
      var rv = l.review || {}, photo = l.photos && l.photos[0] ? C.supabaseUrl + "/storage/v1/object/public/car-photos/" + l.photos[0] : "";
      return "<a class='car' href='" + app + "#/car/" + encodeURIComponent(l.ref) + "' data-make='" + esc(l.make) + "' data-body='" + esc(l.body) + "' data-fuel='" + esc(l.fuel) +
        "' data-gearbox='" + esc(l.gearbox) + "' data-price='" + (l.currency === "UGX" ? l.price : 0) + "' data-year='" + l.year + "' data-km='" + l.mileage + "' data-date='" + esc(l.live_at || "") + "'>" +
        "<div class='car-photo'>" + (photo ? "<img src='" + esc(photo) + "' alt='' loading='lazy' decoding='async'>" : "") +
        (rv.verdict ? "<span class='car-tag'><i></i>" + esc(rv.verdict.charAt(0).toUpperCase() + rv.verdict.slice(1)) + " · " + rv.score + "/100</span>" : "") + "</div>" +
        "<div class='car-name'>" + esc(l.year + " " + l.make + " " + l.model) + "</div><div class='car-meta'>" + Number(l.mileage).toLocaleString("en-US") + " km · " + esc(l.fuel) + " · " + esc(l.gearbox) + "</div>" +
        "<div class='car-price'><b>" + money(l.currency, l.price) + "</b><small>" + esc(l.region) + "</small></div>" +
        "<div class='demand'><span>" + l.views_7d + " views this week</span><span>" + l.saves + " saves</span><span>" + l.offers + " offers</span></div></a>";
    }).join(""));
    var empty = document.getElementById("carsempty"); if (empty) empty.hidden = true;
    ["make", "body", "fuel", "gearbox"].forEach(function (k) {
      var sel = document.querySelector("#carfilter select[name='" + k + "']"); if (!sel) return;
      var have = {}; Array.prototype.forEach.call(sel.options, function (o) { have[o.value] = 1; });
      rows.map(function (r) { return r[k]; }).filter(function (v, i, a) { return a.indexOf(v) === i; }).sort().forEach(function (v) {
        if (!have[v]) { var o = document.createElement("option"); o.value = v; o.textContent = v; sel.appendChild(o); }
      });
    });
    loadFilters();
  }).catch(function () { if (list.children.length) loadFilters(); });
})();
