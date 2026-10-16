/* live-cars.js: shows published cars from the Saaz database on /cars/ and /car/?ref=...
   Reads only (public REST endpoint, anon key). Cars added in the admin appear here without a rebuild.
   When the database isn't configured, the page keeps whatever the build put there. */
(function () {
  var C = window.SAAZ || {};
  var base = C.base || "/";
  var idx = C.fileLinks ? "index.html" : "";  // review copies link to files, not folders
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function ugx(n) { return "UGX " + Number(n).toLocaleString("en-US"); }
  function day(iso) { if (!iso) return ""; var p = iso.split("-"); return +p[2] + " " + MONTHS[+p[1] - 1] + " " + p[0]; }
  function photo(c, cls, tag) {
    var inner = c.photos && c.photos.length
      ? "<img src='" + esc(C.supabaseUrl + "/storage/v1/object/public/car-photos/" + c.photos[0]) + "' alt='' loading='lazy' decoding='async'>"
      : "<svg class='ph' aria-hidden='true'><use href='#i-carside'/></svg><span class='phl'>Photo from the review</span>";
    var n = (c.findings || []).length;
    return "<div class='" + cls + "'>" + inner + (tag ? "<span class='car-tag'><i></i>" + esc(c.review_result) + " · " + n + " finding" + (n === 1 ? "" : "s") + "</span>" : "") + "</div>";
  }
  function name(c) { return c.year + " " + c.make + " " + c.model; }
  function meta(c) { return Number(c.km).toLocaleString("en-US") + " km · " + esc(c.fuel) + " · " + esc(c.gearbox) + " · " + esc(c.drive); }
  function card(c) {
    return "<a class='car' href='" + base + "car/" + idx + "?ref=" + encodeURIComponent(c.ref) + "' data-make='" + esc(c.make) + "' data-body='" + esc(c.body) +
      "' data-fuel='" + esc(c.fuel) + "' data-gearbox='" + esc(c.gearbox) + "' data-price='" + c.price_ugx + "' data-year='" + c.year +
      "' data-km='" + c.km + "' data-date='" + esc(c.review_date || "") + "'>" + photo(c, "car-photo", true) +
      "<div class='car-name'>" + esc(name(c)) + (c.source === "import" ? " <span class='src'>Saaz import</span>" : "") + "</div><div class='car-meta'>" + meta(c) +
      "</div><div class='car-price'><b>" + ugx(c.price_ugx) + "</b><small>" + esc(c.area) + "</small></div></a>";
  }
  function fetchCars(query) {
    return fetch(C.supabaseUrl + "/rest/v1/cars?" + query, { headers: { apikey: C.supabaseAnonKey, Authorization: "Bearer " + C.supabaseAnonKey } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function loadFilters() { var s = document.createElement("script"); s.src = base + "assets/cars.js"; document.body.appendChild(s); }
  function fillSelect(name, values) {
    var sel = document.querySelector("#carfilter select[name='" + name + "']"); if (!sel) return;
    var have = {}; Array.prototype.forEach.call(sel.options, function (o) { have[o.value] = 1; });
    values.forEach(function (v) { if (!have[v]) { var o = document.createElement("option"); o.value = v; o.textContent = v; sel.appendChild(o); } });
  }

  var list = document.getElementById("carlist");
  var detail = document.getElementById("cardetail");
  var configured = C.supabaseUrl && C.supabaseAnonKey;

  if (list) {
    if (!configured) { if (list.children.length) loadFilters(); return; }
    fetchCars("status=eq.published&select=*&order=review_date.desc").then(function (rows) {
      if (rows.length) {
        list.insertAdjacentHTML("afterbegin", rows.map(card).join(""));
        var empty = document.getElementById("carsempty"); if (empty) empty.hidden = true;
        ["make", "body", "fuel", "gearbox"].forEach(function (k) {
          fillSelect(k, rows.map(function (r) { return r[k]; }).filter(function (v, i, a) { return a.indexOf(v) === i; }).sort());
        });
      }
      if (list.children.length) loadFilters();
    }).catch(function () { if (list.children.length) loadFilters(); });
  }

  if (detail) {
    var ref = new URLSearchParams(location.search).get("ref");
    var box = document.getElementById("cardetail");
    if (!configured || !ref) { box.innerHTML = "<div class='empty'><b>Car not found</b><span><a href='" + base + "cars/" + idx + "'>See all reviewed cars</a></span></div>"; return; }
    fetchCars("status=eq.published&ref=eq." + encodeURIComponent(ref) + "&select=*").then(function (rows) {
      var c = rows[0];
      if (!c) { box.innerHTML = "<div class='empty'><b>Car not found</b><span>It may have been sold. <a href='" + base + "cars/" + idx + "'>See all reviewed cars</a></span></div>"; return; }
      document.title = name(c) + " | Saaz";
      var thumbs = (c.photos || []).slice(1, 5).map(function (p) { return photo({ photos: [p] }, "car-photo", false); }).join("");
      var specs = [["Year", c.year], ["Mileage", Number(c.km).toLocaleString("en-US") + " km"], ["Fuel", c.fuel], ["Gearbox", c.gearbox], ["Drive", c.drive],
        ["Engine", c.cc ? Number(c.cc).toLocaleString("en-US") + " cc" : ""], ["Body", c.body], ["Colour", c.colour], ["Chassis number", c.chassis], ["Saaz ref", c.ref]]
        .filter(function (s) { return s[1]; }).map(function (s) { return "<div><dt>" + esc(s[0]) + "</dt><dd" + (s[0] === "Chassis number" ? " class='mono'" : "") + ">" + esc(s[1]) + "</dd></div>"; }).join("");
      var f = (c.findings || []).map(function (x) { return "<li><span class='lvl " + (x.level === "attention" ? "attention" : "note") + "'>" + (x.level === "attention" ? "Attention" : "Note") + "</span><div><b>" + esc(x.area) + "</b><span>" + esc(x.note) + "</span></div></li>"; }).join("")
        || "<li><span class='lvl clear'>Clear</span><div><b>No findings</b><span>Every check on the list passed.</span></div></li>";
      var wa = /^\d{10,15}$/.test(C.whatsapp || "") ? "<a class='btn wide' href='https://wa.me/" + C.whatsapp + "?text=" + encodeURIComponent("Hello Saaz, I'm interested in " + name(c) + " (" + c.ref + ").") + "'>Ask about this car on WhatsApp</a>" : "";
      var n = (c.findings || []).length;
      box.innerHTML = "<div class='car-grid'><div class='gallery'>" + photo(c, "car-photo", false) + (thumbs ? "<div class='thumbs'>" + thumbs + "</div>" : "") +
        "</div><div class='buybox'><h1 class='car-title'>" + esc(name(c)) + "</h1><p class='car-sub'>" + meta(c) + "</p><p class='car-bigprice'>" + ugx(c.price_ugx) +
        "</p><p class='car-area'>" + esc(c.area) + " · " + esc(c.seller) + (c.source === "import" ? " · Saaz import" : "") + "</p><div class='insp-card'><div class='insp-head'><span class='result pass'>" + esc(c.review_result) +
        "</span><span>" + n + " finding" + (n === 1 ? "" : "s") + "</span></div><p>Reviewed " + day(c.review_date) + " at " + esc(c.review_garage) + "</p><a href='#report'>Read the review</a></div>" + wa +
        "<p class='note'>Saaz will never ask you to pay into a personal mobile money number.</p></div></div>" +
        "<div class='split' style='margin-top:48px'><div><div class='kicker'>Details</div><h2>The car.</h2><dl class='specs'>" + specs +
        "</dl></div><div id='report'><div class='kicker'>Review</div><h2>What the shop found.</h2><ul class='findings'>" + f + "</ul></div></div>";
    }).catch(function () { box.innerHTML = "<div class='empty'><b>Couldn't load this car</b><span>Check your connection and try again.</span></div>"; });
  }
})();
