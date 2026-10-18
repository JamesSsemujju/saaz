/* app-public.js: browse, car page with demand and offers, what's selling, verify, the inspection report document, how it works. */
(function () {
  var S = window.Saaz, esc = S.esc;

  // The one listing card, used by the listings page for buyers and for Saaz staff. opts: where it links, and the tag on the photo.
  function card(l, opts) {
    opts = opts || {};
    var r = l.review || {};
    return "<a class='car' href='" + esc(opts.href || "#/car/" + l.ref) + "'><div class='car-photo'>" +
      (l.photos && l.photos[0] ? "<img src='" + esc(S.photo(l.photos[0])) + "' alt='' loading='lazy' decoding='async'>" : "") +
      (r.verdict ? "<span class='car-tag'><i></i>" + esc(S.label(r.verdict)) + " · " + r.score + "/100</span>" : "") +
      (opts.badge || (l.status === "reserved" ? "<span class='car-tag right'>Reserved</span>" : "")) + "</div>" +
      "<div class='car-name'>" + esc(S.name(l)) + (l.saaz_owned ? " <span class='src'>Saaz car</span>" : "") + "</div>" +
      "<div class='car-meta'>" + S.km(l.mileage) + " · " + esc(l.fuel) + " · " + esc(l.gearbox) + " · " + esc(l.region) + "</div>" +
      "<div class='car-price'><b>" + S.money(l.currency, l.price) + "</b></div>" +
      "<div class='demand'><span>" + l.views_7d + " views this week</span><span>" + l.saves + " saves</span><span>" + l.offers + " offers</span></div></a>";
  }
  S.card = card;

  // The listings page. The marketplace (#/browse) and Admin, Cars (#/admin/cars) are this same page:
  // same heading, filters, cards and layout. Admin passes every car, a status filter, and links cards to the car's admin page.
  var PER_PAGE = 24;
  function opt(list, cur) { return list.map(function (x) { return "<option" + (x === cur ? " selected" : "") + ">" + esc(x) + "</option>"; }).join(""); }
  function distinct(rows, k) { var o = {}; rows.forEach(function (l) { if (l[k]) o[l[k]] = 1; }); return Object.keys(o).sort(); }
  // The search fields: the same three on the home page and on the results page
  function searchFields(rows, make, body, max) {
    return "<label>Make<select name='make'><option value=''>Any make</option>" + opt(distinct(rows, "make"), make) + "</select></label>" +
      "<label>Body<select name='body'><option value=''>Any body</option>" + opt(distinct(rows, "body"), body) + "</select></label>" +
      "<label>Max price (UGX)<input name='max' type='number' inputmode='numeric' min='0' step='1000000' placeholder='Any price' value='" + (max || "") + "'></label>";
  }
  function goSearch(form, route) {
    var f = S.form(form), p = new URLSearchParams();
    Object.keys(f).forEach(function (k) { if (f[k]) p.set(k, f[k]); });
    S.go(route + (p.toString() ? "?" + p.toString() : ""));
  }
  function pager(route, q, page, pages) {
    if (pages < 2) return "";
    function href(n) { var p = new URLSearchParams(q.toString()); if (n > 1) p.set("page", n); else p.delete("page"); return route + (p.toString() ? "?" + p.toString() : ""); }
    var out = [], last = 0;
    for (var n = 1; n <= pages; n++) {
      if (n === 1 || n === pages || Math.abs(n - page) <= 1) {
        if (n - last > 1) out.push("<span class='gap'>…</span>");
        out.push(n === page ? "<span aria-current='page'>" + n + "</span>" : "<a href='" + href(n) + "'>" + n + "</a>");
        last = n;
      }
    }
    return "<nav class='pager' aria-label='Pages'>" + (page > 1 ? "<a href='" + href(page - 1) + "' rel='prev'>Previous</a>" : "") + out.join("") +
      (page < pages ? "<a href='" + href(page + 1) + "' rel='next'>Next</a>" : "") + "</nav>";
  }

  // The results page. The marketplace (#/browse) and Admin, Cars (#/admin/cars) are this same page:
  // heading, one filter bar, the grid of cards, paging. Admin adds a status field and links cards to the car's admin page.
  S.listingsPage = function (rows, q, opts) {
    opts = opts || {};
    var route = opts.route || "#/browse";
    var make = q.get("make") || "", model = q.get("model") || "", body = q.get("body") || "", max = +(q.get("max") || 0), saved = q.get("saved") === "1";
    var shown = rows.filter(function (l) {
      return (!make || l.make === make) && (!model || l.model === model) && (!body || l.body === body) && (!max || l.price <= max) && (!saved || l.saved);
    });
    var pages = Math.max(1, Math.ceil(shown.length / PER_PAGE)), page = Math.min(pages, Math.max(1, +(q.get("page") || 1)));
    var slice = shown.slice((page - 1) * PER_PAGE, page * PER_PAGE);
    var html = "<div class='sechead'><h1>" + (saved ? "Saved cars" : "Cars with a Saaz inspection") + "</h1><p>Every car here was inspected in person by a certified garage, inside Saaz.</p></div>" +
      "<form id='flt' class='filters'>" + (opts.statusSelect ? "<label>Status" + opts.statusSelect + "</label>" : "") + searchFields(rows, make, body, max) +
      (S.signedIn() && !opts.admin ? "<label class='inline'><input type='checkbox' name='saved' value='1'" + (saved ? " checked" : "") + "> Saved only</label>" : "") +
      "<button class='btn'>Show cars</button></form>" +
      "<p class='count'>" + shown.length + " car" + (shown.length === 1 ? "" : "s") + (pages > 1 ? " · page " + page + " of " + pages : "") +
        (model ? " · " + esc(make + " " + model) + " <a href='" + route + "'>clear</a>" : "") + "</p>" +
      (slice.length ? "<div class='cars'>" + slice.map(function (l) { return card(l, opts.cardOpts ? opts.cardOpts(l) : null); }).join("") + "</div>" + pager(route, q, page, pages)
        : "<div class='empty'><b>" + (rows.length ? "No cars match these filters" : "No cars listed yet") + "</b><span>" +
          (rows.length ? "<a href='" + route + "'>Clear the filters</a>" : "Cars appear here once they pass a Saaz inspection. <a href='#/sell/new'>List your car</a>") + "</span></div>");
    return { html: html, wire: function () {
      S.$("#flt").onsubmit = function (e) { e.preventDefault(); goSearch(e.target, route); };
    } };
  };

  S.route("/browse", function (v, m, q) {
    return S.rpc("browse_listings", { p_country: "UG" }).then(function (rows) {
      var pg = S.listingsPage(rows || [], q);
      v.innerHTML = pg.html; pg.wire();
    });
  });

  // Home: headline, search under it, the latest cars, one trust section. The footer follows on every page.
  S.homePage = function (v) {
    v.className = "home";
    return S.rpc("browse_listings", { p_country: "UG" }).then(function (rows) {
      rows = rows || [];
      v.innerHTML = "<section class='hero'><div class='wrap'><div><h1 class='display'>Used cars in Uganda, inspected before you buy.</h1>" +
        "<form id='hs' class='homesearch' role='search' aria-label='Search cars'>" + searchFields(rows, "", "", 0) + "<button class='btn'>Search " + rows.length + " car" + (rows.length === 1 ? "" : "s") + "</button></form></div></div></section>" +
        "<section class='band'><div class='wrap'><div class='sechead'><h2>Latest inspected cars</h2></div>" +
        (rows.length ? "<div class='cars'>" + rows.slice(0, 8).map(function (l) { return card(l); }).join("") + "</div>" +
          (rows.length > 8 ? "<div class='more'><a class='btn ghost' href='#/browse'>See all " + rows.length + " cars</a></div>" : "")
          : "<div class='empty'><b>No cars listed yet</b><span>Cars appear here once they pass a Saaz inspection. <a href='#/sell/new'>List your car</a></span></div>") +
        "</div></section>" +
        "<section class='band white'><div class='wrap'><div class='sechead'><h2>Why you can trust a car on Saaz</h2></div><div class='trust'>" +
          "<div><b>Inspected in person</b><p>A certified garage checks every car inside Saaz before it is listed. The score and result are on the photo.</p></div>" +
          "<div><b>A report you can check</b><p>Each report has a code. Anyone can confirm it is real and unchanged.</p><a class='btn text' href='#/verify'>Verify a report</a></div>" +
          "<div><b>No money through Saaz</b><p>Make an offer here. Contact details are shared once you and the seller agree.</p><a class='btn text' href='#/track'>Track an inspection</a></div>" +
        "</div></div></section>";
      S.$("#hs").onsubmit = function (e) { e.preventDefault(); goSearch(e.target, "#/browse"); };
    });
  };

  S.route("/car/([A-Z0-9-]+)", function (v, m) {
    var ref = m[0];
    return S.q(S.db.from("listings").select("*").eq("ref", ref).limit(1)).then(function (rows) {
      var l = rows[0];
      if (!l) { v.innerHTML = "<div class='empty'><b>Car not found</b><span>It may have been withdrawn. <a href='#/browse'>Browse cars</a></span></div>"; return; }
      S.rpc("record_view", { p_listing: l.id, p_device: S.device() }).catch(function () {});
      return Promise.all([
        S.rpc("listing_stats", { p_listing: l.id }),
        l.current_review_id ? S.q(S.db.from("reviews").select("verdict,score,verify_code,valid_until,garage_name,issued_at,doc_no,status").eq("id", l.current_review_id)) : [],
        S.signedIn() ? S.q(S.db.from("saves").select("listing_id").eq("listing_id", l.id).eq("user_id", S.me().id)) : [],
        S.signedIn() ? S.q(S.db.from("deals").select("id,status,amount").eq("listing_id", l.id).eq("buyer_id", S.me().id).in("status", ["negotiating", "agreed", "on_hold"])) : []
      ]).then(function (res) {
        var st = res[0] || {}, r = res[1][0], saved = res[2].length > 0, open = res[3][0], mine = l.seller_id === S.me().id;
        var ph = (l.photos || []).map(function (p) { return S.photo(p); });
        var gallery = "<div class='gallery'><div class='main'>" + (ph[0] ? "<img id='mainphoto' src='" + esc(ph[0]) + "' alt='Photo 1 of " + ph.length + "' decoding='async'>" : "<div class='car-photo'></div>") + "</div>" +
          (ph.length > 1 ? "<div class='shots'>" + ph.map(function (u, i) { return "<button type='button' data-i='" + i + "'" + (i ? "" : " aria-current='true'") + " aria-label='Show photo " + (i + 1) + "'><img src='" + esc(u) + "' alt='' loading='lazy' decoding='async'></button>"; }).join("") + "</div>" : "") + "</div>";
        var buy = "";
        if (l.status === "live" && !mine) {
          if (!S.signedIn()) buy = "<a class='btn wide' href='#/signin' onclick='Saaz.after=location.hash'>Sign in to make an offer</a>";
          else if (open) buy = "<a class='btn wide' href='#/deals/" + open.id + "'>See your offer (" + S.label(open.status) + ")</a>";
          else buy = "<form id='offer' class='stack'><b>Make an offer</b><label>Your offer (" + l.currency + ")<input name='amount' type='number' inputmode='numeric' required min='1'></label>" +
            "<label class='inline'><input type='checkbox' name='trade_in' value='1'> Includes a trade-in car</label>" +
            "<label>Message (optional)<textarea name='message' rows='2' maxlength='500'></textarea></label><p class='err' id='oerr' role='alert'></p><button class='btn wide'>Send offer</button>" +
            "<p class='note'>No money moves through Saaz. Contact details are shared once you both agree.</p></form>";
        } else if (l.status === "reserved") buy = "<p class='box'>Reserved: a deal is agreed on this car.</p>";
        else if (l.status === "sold") buy = "<p class='box'>Sold.</p>";
        var isPublic = ["live", "reserved", "sold"].indexOf(l.status) >= 0;
        v.innerHTML = (isPublic ? "" : "<p class='box warn preview'><b>Preview: not on the marketplace.</b> Status: " + esc(S.label(l.status)) + ". Buyers can't find or open this car; you see it because you're " + (mine ? "the seller" : "Saaz staff") + "." +
            (S.isAdmin() ? " <a href='#/admin/car/" + l.id + "'>Manage it</a>" : "") + "</p>") +
          "<p class='crumbs'><a href='#/browse'>Cars</a> / " + esc(l.ref) + "</p>" +
          "<div class='listing'>" + gallery + "<aside class='buybox' aria-label='Price and contact'>" +
          "<h1 class='car-title'>" + esc(S.name(l)) + "</h1><p class='car-sub'>" + S.km(l.mileage) + " · " + esc(l.fuel) + " · " + esc(l.gearbox) + " · " + esc(l.body) + "</p>" +
          "<p class='car-bigprice'>" + S.money(l.currency, l.price) + "</p><p class='car-area'>" + esc(l.region) + ", " + S.COUNTRY[l.country] + (l.saaz_owned ? " · Sold by Saaz" : "") + "</p>" +
          (r ? "<div class='insp-card'><div class='insp-head'>" + S.chip(r.verdict) + "<span>" + r.score + "/100</span></div><p>Saaz inspection " + esc(r.doc_no) + " by " + esc(r.garage_name) + ", " + S.day(r.issued_at) + ". Valid until " + S.day(r.valid_until) + ".</p><a class='btn text' href='#/report/" + esc(r.verify_code) + "'>Read the inspection report</a></div>" : "") +
          buy +
          (S.signedIn() && !mine ? "<button class='btn ghost wide' id='save'>" + (saved ? "Saved" : "Save this car") + "</button>" : "") +
          (mine ? "<a class='btn ghost wide' href='#/my/cars/" + l.id + "'>Manage this car</a>" : "") +
          "<div class='demand'><span><b>" + st.views_7d + "</b> views this week</span><span><b>" + st.saves + "</b> saves</span><span><b>" + st.offers + "</b> offers so far</span></div></aside>" +
          "<div class='details'><div><h2>Details</h2><dl class='specs'>" + [["Year", l.year], ["Mileage", S.km(l.mileage)], ["Fuel", l.fuel], ["Gearbox", l.gearbox], ["Body", l.body], ["Colour", l.colour], ["Engine", l.engine], ["Plate", l.plate], ["Saaz ref", l.ref]]
            .filter(function (x) { return x[1]; }).map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd></div>"; }).join("") + "</dl></div>" +
          "<div><h2>From the seller</h2><p class='pre'>" + esc(l.description) + "</p></div></div></div>";
        S.$$(".shots button", v).forEach(function (b) {
          b.onclick = function () {
            var i = +b.dataset.i, mp = S.$("#mainphoto"); mp.src = ph[i]; mp.alt = "Photo " + (i + 1) + " of " + ph.length;
            S.$$(".shots button", v).forEach(function (x) { x.removeAttribute("aria-current"); }); b.setAttribute("aria-current", "true");
          };
        });
        var sv = S.$("#save"); if (sv) sv.onclick = function () { S.act(sv, function () { return S.rpc("toggle_save", { p_listing: l.id }); }, function (on) { return on ? "Saved." : "Removed from saved."; }); };
        var of = S.$("#offer");
        if (of) of.onsubmit = function (e) {
          e.preventDefault(); var f = S.form(of), b = of.querySelector("button"); b.disabled = true;
          S.rpc("make_offer", { p_listing: l.id, p_amount: +f.amount, p_trade_in: !!f.trade_in, p_message: f.message || "" }).then(function (res2) {
            if (res2.status === "auto_rejected") { S.$("#oerr").textContent = res2.message; b.disabled = false; return; }
            S.toast("Offer sent."); S.go("#/deals/" + res2.deal);
          }).catch(function (e2) { S.$("#oerr").textContent = S.friendly(e2); b.disabled = false; });
        };
      });
    });
  });

  S.sellingTable = function (rows, cur) {
    if (!rows.length) return "<div class='empty'><b>No sales yet</b><span>This fills in as cars sell on Saaz.</span></div>";
    return "<div class='tablewrap'><table class='tbl'><thead><tr><th>Model</th><th>Median days to sell</th><th>Sold, 90 days</th><th>Live now</th><th>Views a day per listing</th><th>Offers per listing</th><th>Typical agreed price</th></tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td><b>" + esc(r.make + " " + r.model) + "</b>" + (r.selling_fast ? " <span class='chip s-live'>Selling fast</span>" : "") + (r.hint_only ? " <small class='hint'>hint, not a trend</small>" : "") + "</td>" +
          "<td>" + (r.median_days == null ? "–" : r.median_days) + "</td><td>" + r.sold_90d + "</td><td>" + r.live_now + "</td><td>" + (r.views_per_day == null ? "–" : r.views_per_day) + "</td>" +
          "<td>" + (r.offers_per_listing == null ? "–" : r.offers_per_listing) + "</td><td>" + (r.typical_price ? S.money(r.currency, r.typical_price) : "–") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  };
  S.route("/selling", function (v, m, q) {
    var country = "UG";
    return S.rpc("whats_selling", { p_country: country }).then(function (rows) {
      v.innerHTML = "<div class='pagehead'><h1>What's selling</h1><p class='lead'>Sales on Saaz in Uganda in the last 90 days. Selling fast means 2 or more sold with a median of 14 days or less.</p></div>" +
        
        S.sellingTable(rows) + "<p class='note'>Models with fewer than 5 listings are marked as a hint, not a trend.</p>";
    });
  });

  S.route("/verify", function (v, m, q) {
    v.innerHTML = "<div class='narrow'><h1>Verify a Saaz inspection</h1><p class='lead'>Type the code printed on the report, or scan its QR code.</p>" +
      "<form id='f' class='check light'><label for='code'>Verification code</label><input id='code' name='code' placeholder='XXXX-XXXX-XXXX' autocapitalize='characters' required value='" + esc(q.get("code") || "") + "'><button>Verify</button></form><div id='out' aria-live='polite'></div></div>";
    function run(code) {
      S.rpc("verify_review", { p_code: code }).then(function (r) {
        var out = S.$("#out");
        if (!r.genuine) { out.innerHTML = "<div class='verdict bad'><b>Not genuine</b><span>" + esc(r.message) + "</span></div>"; return; }
        out.innerHTML = "<div class='verdict " + (r.intact ? "good" : "bad") + "'><b>" + (r.intact ? "Genuine Saaz inspection" : "Warning: this record was changed after it was issued") + "</b>" +
          "<span>Status: " + esc(S.label(r.status)) + "</span></div><p>This is what the report should say:</p><dl class='specs'>" +
          [["Inspection ID", r.doc_no + " v" + r.version], ["Car", r.year + " " + r.make + " " + r.model], ["VIN", r.vin], ["Plate", r.plate], ["Verdict", S.label(r.verdict) + ", " + r.score + "/100"],
           ["Odometer", S.km(r.odometer)], ["Issued", S.when(r.issued_at)], ["Valid until", S.day(r.valid_until)], ["Garage", r.garage], ["Inspected by", r.member]]
            .map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd></div>"; }).join("") + "</dl>" +
            (r.opinions && r.opinions.length ? "<h2>What Saaz said about this report</h2>" + S.opinionsHtml(r.opinions) : "") + "<a class='btn' href='#/report/" + esc(code.toUpperCase()) + "'>Open the report</a>";
      }).catch(function (e) { S.$("#out").innerHTML = "<p class='err'>" + esc(S.friendly(e)) + "</p>"; });
    }
    S.$("#f").onsubmit = function (e) { e.preventDefault(); run(S.form(e.target).code); };
    if (q.get("code")) run(q.get("code"));
  });

  // ----- The report document -----
  var CHECKS = [["engine", "Engine"], ["gearbox", "Gearbox and clutch"], ["brakes", "Brakes", 1], ["steering", "Steering and suspension", 1], ["tyres", "Tyres"], ["electrics", "Electrics and lights"],
    ["body", "Body and paint"], ["chassis", "Chassis and rust"], ["interior", "Interior and AC"], ["test_drive", "Test drive"], ["odometer", "Odometer consistent", 1], ["vin", "VIN matches logbook and car", 1]];
  var PANELS = [["front_bumper", "Front bumper"], ["bonnet", "Bonnet"], ["left_front", "Left front"], ["right_front", "Right front"], ["roof", "Roof"], ["left_rear", "Left rear"], ["right_rear", "Right rear"], ["boot", "Boot"], ["rear_bumper", "Rear bumper"]];
  var MARKS = ["none", "scratch", "dent", "repaint", "damage"];
  S.CHECKS = CHECKS; S.PANELS = PANELS; S.MARKS = MARKS;
  S.markColour = { none: "#E8F3EC", scratch: "#FFF4CC", dent: "#FFE0B8", repaint: "#DCE8FF", damage: "#FFD2D2" };

  // Top view of a car: 9 panels. Used by the report and the review editor.
  S.bodyMap = function (panels, editable) {
    var box = { front_bumper: [60, 6, 80, 22], bonnet: [52, 30, 96, 58], left_front: [20, 30, 30, 70], right_front: [150, 30, 30, 70], roof: [52, 92, 96, 92],
      left_rear: [20, 110, 30, 92], right_rear: [150, 110, 30, 92], boot: [52, 188, 96, 42], rear_bumper: [60, 236, 80, 22] };
    return "<svg class='bodymap' viewBox='0 0 200 264' role='group' aria-label='Body map, top view'>" +
      "<rect x='46' y='24' width='108' height='212' rx='30' fill='none' stroke='#9AA6B5' stroke-width='2'/>" +
      PANELS.map(function (p) {
        var b = box[p[0]], mk = (panels && panels[p[0]]) || "none";
        return "<g" + (editable ? " tabindex='0' role='button' data-panel='" + p[0] + "'" : "") + "><title>" + p[1] + ": " + S.label(mk) + "</title>" +
          "<rect x='" + b[0] + "' y='" + b[1] + "' width='" + b[2] + "' height='" + b[3] + "' rx='6' fill='" + S.markColour[mk] + "' stroke='#5B6675'/>" +
          (mk !== "none" ? "<text x='" + (b[0] + b[2] / 2) + "' y='" + (b[1] + b[3] / 2 + 4) + "' text-anchor='middle' font-size='10' fill='#111827'>" + mk.slice(0, 3).toUpperCase() + "</text>" : "") + "</g>";
      }).join("") + "</svg>";
  };

  // Security pattern from the fingerprint: no two reports look the same.
  function rosette(fp) {
    var n = function (i) { return parseInt(fp.substr(i * 2, 2), 16); };
    var petals = 7 + n(0) % 9, rings = 3 + n(1) % 3, out = "";
    for (var k = 0; k < rings; k++) {
      var r1 = 54 - k * 9, amp = 4 + n(2 + k) % 7, ph = n(6 + k) / 255 * Math.PI, d = "";
      for (var a = 0; a <= 360; a += 3) {
        var t = a * Math.PI / 180, r = r1 + amp * Math.sin(petals * t + ph);
        d += (a ? "L" : "M") + (60 + r * Math.cos(t)).toFixed(1) + " " + (60 + r * Math.sin(t)).toFixed(1);
      }
      out += "<path d='" + d + "Z' fill='none' stroke='hsl(" + (n(10 + k) * 1.4) + ",45%,42%)' stroke-width='.6' opacity='.8'/>";
    }
    return "<svg class='rosette' viewBox='0 0 120 120' aria-hidden='true'>" + out + "</svg>";
  }
  function waves(fp) {
    var out = "";
    for (var k = 0; k < 4; k++) {
      var f = 2 + parseInt(fp[k], 16) % 5, ph = parseInt(fp[k + 4], 16) / 16 * Math.PI * 2, d = "";
      for (var x = 0; x <= 600; x += 6) d += (x ? "L" : "M") + x + " " + (10 + 6 * Math.sin(x / 600 * Math.PI * 2 * f + ph)).toFixed(1);
      out += "<path d='" + d + "' fill='none' stroke='hsl(" + (parseInt(fp.substr(8 + k * 2, 2), 16) * 1.4) + ",40%,55%)' stroke-width='.7'/>";
    }
    return "<svg class='waves' viewBox='0 0 600 20' preserveAspectRatio='none' aria-hidden='true'>" + out + "</svg>";
  }
  function qr(el, text) { // QR code from cdnjs; the code is printed beside it either way
    function draw() { try { new window.QRCode(el, { text: text, width: 96, height: 96, correctLevel: window.QRCode.CorrectLevel.M }); } catch (e) {} }
    if (window.QRCode) return draw();
    var s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"; s.onload = draw; document.head.appendChild(s);
  }

  S.route("/report/([A-Za-z0-9-]+)", function (v, m) {
    return S.rpc("review_document", { p_code: m[0] }).then(function (d) {
      if (!d) { v.innerHTML = "<div class='empty'><b>No Saaz inspection has this code</b><span><a href='#/verify'>Verify a code</a></span></div>"; return; }
      var r = d.review, l = d.listing, veh = d.vehicle, fp = r.fingerprint || "0".repeat(64);
      var ribbon = { issued: "Valid until " + S.day(r.valid_until), superseded: "Superseded", void: "Void", expired: "Expired", draft: "Draft" }[d.status];
      var verifyUrl = location.origin + location.pathname + "#/verify?code=" + r.verify_code;
      var micro = ("SAAZ REVIEW " + r.doc_no + " " + fp + " ").repeat(6);
      v.innerHTML = "<div class='docbar noprint'><a href='#/verify?code=" + esc(r.verify_code) + "'>Verify this report</a><button class='btn small' onclick='print()'>Print or save as PDF</button></div>" +
        "<article class='report st-" + esc(d.status) + "'>" + (d.status !== "issued" ? "<div class='watermark' aria-hidden='true'>" + esc(ribbon.toUpperCase()) + "</div>" : "") +
        "<div class='ribbon r-" + esc(d.status) + "'>" + esc(ribbon) + "</div>" + waves(fp) +
        "<header class='rhead'><div><img class='replogo' src='" + S.site + "assets/img/brand/saaz-wordmark-black-240.webp' width='120' height='34' alt='Saaz'><h1>Saaz " + (d.scope && d.scope.key !== "general" ? esc(d.scope.name.toLowerCase()) + " " : "") + "inspection report</h1><p>Inspection ID " + esc(r.doc_no) + " · version " + r.version + "</p></div>" +
        "<div class='score'>" + rosette(fp) + "<b>" + r.score + "</b><small>/100</small><span class='stamp v-" + esc(r.verdict) + "'>" + esc(S.label(r.verdict)) + "</span></div></header>" +
        (d.intact ? "" : "<p class='verdict bad'><b>This record no longer matches its fingerprint.</b></p>") +
        "<section><h2>Vehicle and provenance</h2><dl class='specs four'>" + [["VIN", veh.vin], ["Make", l.make], ["Model", l.model], ["Year", l.year], ["Plate", l.plate], ["Colour", l.colour], ["Engine", l.engine], ["Fuel", l.fuel],
          ["Provenance", veh.source === "saaz_import" ? "Saaz import" : "Local, importer unknown"], ["First Saaz record", S.day(veh.first_record_date)], ["Odometer at inspection", S.km(r.odometer)], ["Saaz ref", l.ref]]
          .map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1] || "–") + "</dd></div>"; }).join("") + "</dl></section>" +
        "<section class='rgrid'><div><h2>" + (d.scope && d.scope.key !== "general" ? esc(d.scope.name) + ": " + d.scope.checks.length + " checks" : "12-point check") + "</h2><ul class='checks'>" + CHECKS.filter(function (c) { return !d.scope || d.scope.checks.indexOf(c[0]) >= 0; }).map(function (c) {
          var val = (r.checks || {})[c[0]] || "–";
          return "<li><span>" + esc(c[1]) + (c[2] ? " <small>safety</small>" : "") + "</span><b class='m-" + esc(val) + "'>" + esc(S.label(val)) + "</b></li>";
        }).join("") + "</ul></div>" + (d.scope && !d.scope.panels ? "<div><h2>Scope</h2><p>This report covers " + esc(d.scope.name.toLowerCase()) + " only. It is not a full Saaz inspection.</p></div>" : "<div><h2>Body, top view</h2>" + S.bodyMap(r.panels) +
        "<p class='legend'>" + MARKS.map(function (k) { return "<span><i style='background:" + S.markColour[k] + "'></i>" + S.label(k === "none" ? "no marks" : k) + "</span>"; }).join("") + "</p></div>") + "</section>" +
        (r.notes ? "<section><h2>Notes</h2><p class='pre'>" + esc(r.notes) + "</p></section>" : "") +
        "<section><h2>Odometer history</h2><table class='tbl'><thead><tr><th>Date</th><th>Reading</th><th>Source</th><th>Flag</th></tr></thead><tbody>" +
        (d.odometer || []).map(function (o) { return "<tr><td>" + S.day(o.at) + "</td><td>" + S.km(o.km) + "</td><td>" + esc(S.label(o.source)) + "</td><td>" + esc(o.flagged || "") + "</td></tr>"; }).join("") + "</tbody></table></section>" +
        "<section class='sigs'><div><h2>Signed</h2><p><b>" + esc(r.member_name) + "</b>, " + esc(S.label(r.member_role)) + "<br>Member id " + esc(String(r.member_id).slice(0, 8)) + "<br>" + esc(r.garage_name) +
        ", certified " + S.day(r.garage_certified_at) + "<br>Issued while signed in, " + S.when(r.issued_at) + "</p></div>" +
        "<div class='verify'><div id='qr'></div><p>Verification code<br><b class='mono'>" + esc(r.verify_code) + "</b><br><small>Check it at Saaz, Verify.</small></p></div></section>" +
        "<section class='opinions'><h2>What Saaz said about this report</h2><p class='small'>Saaz never changes a garage's report. It can support it or object to it, with a reason; the garage can reply.</p>" + S.opinionsHtml(d.opinions) +
          (d.saaz_stance && (S.state.roles || {}).garage ? "<form id='gr' class='stack noprint'><label>Reply as the garage<textarea name='t' rows='2' minlength='10' required></textarea></label><button class='btn small'>Send reply to Saaz</button></form>" : "") + "</section>" +
        "<footer><p class='mono fp'>Fingerprint " + esc(fp) + "</p><p class='micro' aria-hidden='true'>" + esc(micro) + "</p>" +
        "<p class='small'>A Saaz inspection is made inside the Saaz portal by a signed-in member of a certified garage, on a job arranged through Saaz. The fingerprint is a check value, not a cryptographic signature.</p></footer>" + waves(fp.split("").reverse().join("")) + "</article>";
      qr(S.$("#qr"), verifyUrl);
      var gr = S.$("#gr"); if (gr) gr.onsubmit = function (e) { e.preventDefault(); S.act(gr.querySelector("button"), function () { return S.rpc("garage_reply_opinion", { p_review: r.id, p_text: S.form(gr).t }); }, "Reply sent to Saaz."); };
    });
  });

  // ---------- Track an inspection: lookup, then sign in, then the database decides what this person may see ----------
  // Lookup says only "found" or "not found". Everything about the inspection comes from inspection_access, after sign-in.
  var ID_RE = /^SZR-\d{4}-\d{6}$/i;
  S.route("/track", function (v, m, q) {
    var pre = (q.get("id") || "").toUpperCase();
    v.innerHTML = "<div class='narrow'><h1>Track an inspection</h1><p class='lead'>Enter the inspection ID you were given, for example SZR-2026-000123.</p>" +
      "<form id='tf' class='stack'><label>Inspection ID<input name='id' value='" + esc(pre) + "' autocomplete='off' autocapitalize='characters' required></label><p class='err' id='terr' role='alert'></p><button class='btn wide'>Find the inspection</button></form><div id='tnext'></div></div>";
    var tf = S.$("#tf");
    tf.onsubmit = function (e) {
      e.preventDefault(); var id = S.form(tf).id.toUpperCase().replace(/\s+/g, ""), b = tf.querySelector("button"), err = S.$("#terr"); err.textContent = ""; S.$("#tnext").innerHTML = "";
      if (!ID_RE.test(id)) { err.textContent = "That doesn't look like an inspection ID. It looks like SZR-2026-000123."; return; }
      b.disabled = true;
      S.rpc("lookup_inspection", { p_id: id }).then(function (r) {
        b.disabled = false;
        if (!r || !r.found) { err.textContent = "No inspection has this ID. Check it and try again."; return; }
        if (S.signedIn()) return S.go("#/inspection/" + id);
        // Found: sign in as the seller or the garage member it belongs to
        S.$("#tnext").innerHTML = "<section><h2>Inspection found. Sign in to see it.</h2><p class='note'>Only the seller of the car, the garage doing it and Saaz can see an inspection.</p>" +
          "<form id='lf' class='stack'><fieldset class='seg'><legend>I'm the</legend><label><input type='radio' name='as' value='seller' checked><span>Seller</span></label><label><input type='radio' name='as' value='garage'><span>Garage team</span></label></fieldset>" +
          "<label>Email<input name='email' type='email' autocomplete='email' required></label><label>Password<input name='password' type='password' autocomplete='current-password' required></label>" +
          "<p class='err' id='lerr' role='alert'></p><button class='btn wide'>Sign in and open</button></form><p class='note'><a href='#/forgot'>Forgot your password?</a></p></section>";
        var lf = S.$("#lf");
        lf.onsubmit = function (e2) {
          e2.preventDefault(); var f = S.form(lf), lb = lf.querySelector("button"), le = S.$("#lerr"); lb.disabled = true; le.textContent = "";
          S.db.auth.signInWithPassword({ email: f.email, password: f.password }).then(function (x) {
            if (x.error) throw x.error;
            return S.loadRoles();
          }).then(function () {
            if (f.as === "garage") return S.rpc("garage_sign_in").then(function (g) { if (g.ok) S.mode("garage"); });
            S.mode("seller");
          }).then(function () { S.go("#/inspection/" + id); })
            .catch(function (e3) { lb.disabled = false; le.textContent = S.friendly(e3); });
        };
        S.$("#lf input[name=email]").focus();
      }).catch(function (e2) { b.disabled = false; err.textContent = S.friendly(e2); });
    };
    if (pre) tf.requestSubmit ? tf.requestSubmit() : tf.onsubmit(new Event("submit"));
  });

  S.route("/inspection/([A-Za-z0-9-]+)", function (v, m) {
    var id = m[0].toUpperCase();
    if (!S.signedIn()) return S.go("#/track?id=" + encodeURIComponent(id));
    return S.rpc("inspection_access", { p_id: id }).then(function (a) {
      var steps = [["requested", "Requested"], ["booked", "Garage booked"], ["draft", "In progress"], ["issued", "Completed"]];
      var at = a.status === "requested" ? (a.booking === "agreed" ? 1 : 0) : a.status === "draft" ? 2 : ["issued", "superseded"].indexOf(a.status) >= 0 ? 3 : -1;
      var acts = [];
      if (a.can_continue) acts.push("<a class='btn' href='#/garage/review/" + a.id + "'>Continue the inspection</a>");
      else if (a.can_start) acts.push("<button class='btn' id='startins'>Start this inspection</button>");
      else if (a.start_block && (a.relation === "inspector" || a.relation === "garage_owner")) acts.push("<p class='box warn'>" + esc(a.start_block) + "</p>");
      if (a.verify_code) acts.push("<a class='btn ghost' href='#/report/" + esc(a.verify_code) + "'>Open the report</a>");
      if (a.relation === "seller") acts.push("<a class='btn ghost' href='#/my/cars/" + esc(a.car.listing_id) + "'>Open my car</a>");
      v.innerHTML = "<p class='crumbs'><a href='#/track'>Track an inspection</a> / " + esc(a.inspection_id) + "</p>" +
        "<div class='pagehead'><h1>" + esc(a.scope_name) + "</h1>" + S.inspChip(a.status) + "</div>" +
        "<p class='lead'>Inspection ID <b class='mono'>" + esc(a.inspection_id) + "</b> · " + esc(a.car.year + " " + a.car.make + " " + a.car.model) + " · " + esc(a.car.ref) + "</p>" +
        (at >= 0 ? "<ol class='progress'>" + steps.map(function (s0, i) { return "<li class='" + (i < at ? "done" : i === at ? "now" : "") + "'>" + s0[1] + "</li>"; }).join("") + "</ol>" : "") +
        (a.status === "cancelled" ? "<p class='box warn'>Cancelled " + S.when(a.cancelled_at) + (a.cancel_reason ? ": " + esc(a.cancel_reason) : "") + "</p>" : "") +
        "<dl class='specs'>" + [["Requested", S.when(a.requested_at)], ["Garage", a.garage || "Saaz is finding a garage"], ["Inspection date", a.inspection_date ? S.day(a.inspection_date) : ""],
          ["Inspector", a.inspector || ""], ["Started", S.when(a.started_at)], ["Completed", S.when(a.issued_at)]]
          .filter(function (x) { return x[1]; }).map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd></div>"; }).join("") + "</dl>" +
        "<div class='row'>" + acts.join("") + "</div>";
      var sb = S.$("#startins"); if (sb) sb.onclick = function () {
        sb.disabled = true;
        // The database checks everything again at this moment, and only one person can start it
        S.rpc("start_inspection", { p_id: id }).then(function (rid) { S.toast("Inspection " + id + " started."); S.go("#/garage/review/" + rid); })
          .catch(function (e) { S.toast(S.friendly(e), true); S.render(); });
      };
    }).catch(function (e) {
      v.innerHTML = "<div class='empty'><b>" + esc(S.friendly(e)) + "</b><span>Signed in as " + esc(S.me().email) + ". <a href='#/track'>Try another ID</a></span></div>";
    });
  });

  S.route("/how", function (v) {
    v.innerHTML = "<div class='narrow prose'><h1>How Saaz works</h1><p class='lead'>No Saaz inspection, no listing.</p>" +
      "<h2>The rule</h2><p>A Saaz inspection is a report made inside Saaz, by a signed-in member of a certified garage, on a job arranged through Saaz. A garage's own job card, a paper report or an inspection done before the car was submitted doesn't count. There is no upload for outside reports.</p>" +
      "<h2>Selling</h2><ol><li>Start with the VIN. If Saaz has seen the car before, its history carries on.</li><li>Submit. Saaz puts one certified garage in play, nearest first. Only that garage can contact you, and only inside Saaz.</li>" +
      "<li>Agree with the garage, or pass and the next one comes in. After you agree, share whatever you like with them.</li><li>The garage inspects the car in person and issues the Saaz inspection report. Saaz checks it, and your car goes live.</li></ol>" +
      "<h2>Buying</h2><p>Make an offer on a live car. Sellers can set offer rules. Contact details are shared once you both agree. No money moves through Saaz.</p>" +
      "<h2>Checking a report</h2><p>Every report has a verification code. <a href='#/verify'>Verify one here</a>.</p></div>";
  });
})();
