/* app-seller.js: list a car (VIN first), my cars, one car (garage line, offer rules, demand, offers, history), deals. */
(function () {
  var S = window.Saaz, esc = S.esc;

  // Partial decode, starter tables only (assumption): 17-character VIN gives make and model year; Japanese chassis prefix gives make and model.
  var WMI = { JT: "Toyota", JN: "Nissan", JH: "Honda", JM: "Mazda", JF: "Subaru", JS: "Suzuki", JA: "Mitsubishi", WDB: "Mercedes-Benz", WDD: "Mercedes-Benz", WBA: "BMW",
    WAU: "Audi", WVW: "Volkswagen", WV1: "Volkswagen", SAL: "Land Rover", KMH: "Hyundai", KNA: "Kia", MA3: "Suzuki", MAL: "Hyundai", MR0: "Toyota", AHT: "Toyota" };
  var YEAR = "ABCDEFGHJKLMNPRSTVWXY123456789";
  var CHASSIS = { ZSU60: ["Toyota", "Harrier"], ACU30: ["Toyota", "Harrier"], NZE161: ["Toyota", "Corolla Axio"], NZE141: ["Toyota", "Corolla"], ZRE142: ["Toyota", "Corolla"],
    GRJ150: ["Toyota", "Land Cruiser Prado"], TRJ150: ["Toyota", "Land Cruiser Prado"], ACA31: ["Toyota", "RAV4"], ZRR70: ["Toyota", "Noah"], AZR60: ["Toyota", "Noah"],
    NCP100: ["Toyota", "Ractis"], SCP10: ["Toyota", "Vitz"], KSP90: ["Toyota", "Vitz"], GX110: ["Toyota", "Mark II"], AT212: ["Toyota", "Carina"], ST246: ["Toyota", "Caldina"],
    E12: ["Nissan", "Note"], T31: ["Nissan", "X-Trail"], NT31: ["Nissan", "X-Trail"], GD1: ["Honda", "Fit"], GP5: ["Honda", "Fit Hybrid"], RU1: ["Honda", "Vezel"],
    SH5: ["Subaru", "Forester"], SJ5: ["Subaru", "Forester"], BM9: ["Subaru", "Legacy"], CV1W: ["Mitsubishi", "Delica D5"] };
  S.decode = function (vin) {
    vin = vin.toUpperCase().replace(/\s/g, "");
    if (/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) {
      var mk = WMI[vin.slice(0, 3)] || WMI[vin.slice(0, 2)], ch = vin[9], i = YEAR.indexOf(ch), yr = null;
      if (i >= 0) { yr = 2010 + i; if (yr > new Date().getFullYear() + 1) yr -= 30; }
      return { make: mk || "", year: yr, how: "17-character VIN" };
    }
    var prefix = vin.split("-")[0], hit = CHASSIS[prefix] || CHASSIS[prefix.replace(/[A-Z]$/, "")];
    return hit ? { make: hit[0], model: hit[1], how: "Japanese chassis number" } : { how: "not in the starter tables" };
  };

  // Shrink photos to about 30 KB WebP before upload (slow data)
  function shrink(file) {
    return new Promise(function (res, rej) {
      var img = new Image(); img.onload = function () {
        var w = Math.min(960, img.width), h = Math.round(img.height * w / img.width), c = document.createElement("canvas"); c.width = w; c.height = h;
        c.getContext("2d").drawImage(img, 0, 0, w, h); URL.revokeObjectURL(img.src);
        var q = 0.62; (function tryq() { c.toBlob(function (b) { if (b.size > 40000 && q > 0.3) { q -= 0.1; tryq(); } else res(b); }, "image/webp", q); })();
      }; img.onerror = rej; img.src = URL.createObjectURL(file);
    });
  }

  var PROGRESS = [["Listed", ["draft", "changes_requested"]], ["Saaz inspection", ["awaiting_review", "review_booked"]], ["Approved", ["awaiting_approval", "live", "re_review_due"]], ["Deal agreed", ["reserved"]], ["Sold", ["sold"]]];
  function progress(status) {
    var at = PROGRESS.findIndex(function (p) { return p[1].indexOf(status) >= 0; });
    return "<ol class='progress'>" + PROGRESS.map(function (p, i) { return "<li class='" + (i < at ? "done" : i === at ? "now" : "") + "'>" + p[0] + "</li>"; }).join("") + "</ol>";
  }
  var STATUS_TEXT = { draft: "Draft. Only you can see it.", awaiting_review: "Waiting for a garage. Saaz puts one certified garage in play at a time.", review_booked: "Booked with a garage for its Saaz inspection.",
    awaiting_approval: "Saaz inspection issued. Saaz is checking it.", changes_requested: "Saaz asked for changes.", live: "Live on Saaz.", reserved: "Reserved: a deal is agreed.", sold: "Sold.",
    rejected: "Not approved.", withdrawn: "Withdrawn.", re_review_due: "The Saaz inspection expired. Submit again for a new review." };
  // What the seller can do next, by status (only steps the product really has)
  var NEXT_TEXT = { draft: "Next: submit it for a Saaz inspection. Saaz then offers your car to the nearest certified garage.",
    changes_requested: "Next: make the changes Saaz asked for, then submit again.",
    awaiting_review: "Next: when a garage messages you, agree to book the inspection or pass to the next garage.",
    review_booked: "Next: take the car to the garage on the date it sets.",
    live: "Buyers can find your car. Set offer rules below so offers under your floor are handled for you." };

  // ---------- Facts the seller pages show, read from the database (one place) ----------
  // settings and inspection_scopes are readable by visitors (marketplace_4_access.sql, marketplace_14). Fallbacks are the values in those files.
  S.sellFacts = function () {
    if (S._sellFacts) return Promise.resolve(S._sellFacts);
    var fb = { minPrice: 1000000, validDays: 60, scopes: null };
    if (!S.db) return Promise.resolve(fb);
    return Promise.all([
      S.q(S.db.from("settings").select("key,value").in("key", ["min_price_ugx", "review_valid_days"])).catch(function () { return []; }),
      S.scopes().catch(function () { return null; })
    ]).then(function (r) {
      var f = Object.assign({}, fb);
      (r[0] || []).forEach(function (x) { if (x.key === "min_price_ugx") f.minPrice = +x.value || fb.minPrice; if (x.key === "review_valid_days") f.validDays = +x.value || fb.validDays; });
      f.scopes = r[1]; S._sellFacts = f; return f;
    });
  };
  // Sale prices by model from What's selling (public). Only rows that are a trend, not a hint, are used.
  S.soldPrices = function () {
    if (S._soldPrices) return Promise.resolve(S._soldPrices);
    return S.rpc("whats_selling", { p_country: "UG" }).then(function (rows) { S._soldPrices = (rows || []).filter(function (r) { return !r.hint_only && r.typical_price; }); return S._soldPrices; }).catch(function () { return []; });
  };
  S.soldPriceFor = function (rows, make, model) {
    var mk = String(make || "").trim().toLowerCase(), md = String(model || "").trim().toLowerCase();
    return mk && md ? rows.filter(function (r) { return r.make.toLowerCase() === mk && r.model.toLowerCase() === md; })[0] : null;
  };
  // Check names for people
  var CHECK_NAMES = { engine: "Engine", gearbox: "Gearbox", brakes: "Brakes", steering: "Steering", tyres: "Tyres", electrics: "Electrics", body: "Body and paint",
    chassis: "Chassis", interior: "Interior", test_drive: "Test drive", odometer: "Odometer reading", vin: "VIN or chassis number" };
  S.checkName = function (k) { return CHECK_NAMES[k] || S.label(k); };
  // Local copy of an unsaved listing form, so a closed tab, an ended session or a sign-in doesn't lose it. Cleared on save and on sign-out.
  var DRAFT_KEY = function () { return "saaz-selldraft-" + (S.me().id || "anon"); }, START_KEY = "saaz-sellstart";
  function readLocal(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  function writeLocal(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  // ---------- List a car ----------
  function sellForm(v, existing, saaz, preVin, facts, sold) {
    var l = existing || {}, look = null, photos = (l.photos || []).slice(), minPrice = facts.minPrice;
    var lockedMsg = "", restored = null, saved = existing ? null : readLocal(DRAFT_KEY());
    if (saved && !preVin) preVin = saved.vin;
    function fieldsHtml(locked) {
      var dis = locked ? " readonly" : "";
      return "<div class='grid2'><label>Make<input name='make' required value='" + esc(l.make || "") + "'" + dis + "></label><label>Model<input name='model' required value='" + esc(l.model || "") + "'" + dis + "></label>" +
        "<label>Year<input name='year' type='number' min='1980' max='" + (new Date().getFullYear() + 1) + "' required value='" + esc(l.year || "") + "'" + dis + "></label>" +
        "<label>Fuel<select name='fuel' required" + (locked ? " disabled" : "") + ">" + ["Petrol", "Diesel", "Hybrid", "Electric"].map(function (x) { return "<option" + (l.fuel === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Gearbox<select name='gearbox' required" + (locked ? " disabled" : "") + ">" + ["Automatic", "Manual"].map(function (x) { return "<option" + (l.gearbox === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Body<select name='body' required" + (locked ? " disabled" : "") + ">" + ["Saloon", "Hatchback", "SUV", "Station wagon", "Pickup", "Van", "Minibus", "Coupe"].map(function (x) { return "<option" + (l.body === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Engine<input name='engine' placeholder='2.0' value='" + esc(l.engine || "") + "'" + dis + "></label><label>Colour<input name='colour' required value='" + esc(l.colour || "") + "'></label>" +
        "<label>Mileage (km)<input name='mileage' type='number' inputmode='numeric' min='0' max='1000000' required value='" + esc(l.mileage == null ? "" : l.mileage) + "'><small class='fieldhint'>The garage reads the odometer at the inspection, and the reading stays in this car's Saaz history.</small></label>" +
        "<input type='hidden' name='country' id='ctry' value='UG'>" +
        "<label>Region<select name='region' id='reg' required></select></label><label>Number plate (Uganda)<input name='plate' required placeholder='UBA 123X' value='" + esc(l.plate || "") + "' autocapitalize='characters'></label>" +
        "<label>Asking price (UGX)<input name='price' type='number' inputmode='numeric' required min='" + minPrice + "' step='1000' value='" + esc(l.price || "") + "'><small class='fieldhint' id='h-price' aria-live='polite'></small></label></div>" +
        "<label>Description<textarea name='description' rows='4' minlength='30' required placeholder='Service history, recent work, anything a buyer should know'>" + esc(l.description || "") + "</textarea><small class='fieldhint' id='h-desc' aria-live='polite'></small></label>" +
        "<div><b>Photos<span class='req' aria-hidden='true'> *</span></b> <small>4 to 12. The first one is the photo on your card. Shrunk to about 30 KB each.</small><div id='thumbs' class='thumbs'></div><input type='file' id='files' accept='image/*' multiple><small class='fieldhint' id='h-photos' aria-live='polite'></small></div>" +
        (saaz ? "" : "<p class='note'>Tick one of these two<span class='req' aria-hidden='true'> *</span></p><label class='inline'><input type='checkbox' name='logbook_name_matches' value='1'" + (l.logbook_name_matches ? " checked" : "") + "> The logbook is in my name</label>" +
          "<label class='inline'><input type='checkbox' name='owner_authorised' value='1'" + (l.owner_authorised ? " checked" : "") + "> The owner authorised me to sell</label>") +
        "<p class='err' id='err' role='alert'></p><div class='row'><button class='btn ghost' name='go' value='save'>Save draft</button><button class='btn' name='go' value='submit'>Save and submit for a Saaz inspection</button></div>" +
        "<p class='note'>Submitting asks Saaz to offer your car to the nearest certified garage. The garage sets the inspection price and you pay it there. Your car stays private until the inspection is issued and Saaz approves it.</p>";
    }
    function drawThumbs() {
      S.$("#thumbs").innerHTML = photos.map(function (p, i) { return "<figure><img src='" + esc(S.photo(p)) + "' alt=''><button type='button' data-i='" + i + "' aria-label='Remove photo'>×</button></figure>"; }).join("");
      S.$$("#thumbs button").forEach(function (b) { b.onclick = function () { photos.splice(+b.dataset.i, 1); drawThumbs(); keep(); }; });
      var n = photos.length, h = S.$("#h-photos");
      if (h) h.textContent = n >= 4 ? n + " photos added." + (n < 12 ? " You can add " + (12 - n) + " more." : "") : n + " of at least 4 photos. Buyers look at the photos first.";
      preview();
    }
    // The card buyers will see, drawn by the marketplace's own card (S.card) as the seller types
    function formState() {
      var fm = S.$("#f"); if (!fm) return null; var f = S.form(fm);
      S.$$("select[disabled]", fm).forEach(function (x) { f[x.name] = x.value; });
      S.$$("input[type=checkbox]", fm).forEach(function (x) { f[x.name] = x.checked; });
      return f;
    }
    function preview() {
      var f = formState(), box = S.$("#pv"); if (!f || !box) return;
      box.innerHTML = S.card({ year: f.year, make: f.make, model: f.model, mileage: f.mileage === "" ? null : f.mileage, fuel: f.fuel, gearbox: f.gearbox, region: f.region,
        price: f.price === "" ? null : f.price, currency: "UGX", photos: photos, saaz_owned: !!saaz }, { preview: true, tag: "<span class='car-tag pending'>Inspection result goes here</span>" });
      var d = S.$("#h-desc"), len = String(f.description || "").trim().length;
      if (d) d.textContent = len >= 30 ? "" : len + " of at least 30 characters.";
    }
    function priceHint() {
      var f = formState(), h = S.$("#h-price"); if (!f || !h) return;
      var p = +f.price;
      if (f.price !== "" && p < minPrice) { h.textContent = "The lowest asking price on Saaz is " + S.money("UGX", minPrice) + "."; return; }
      var row = S.soldPriceFor(sold, f.make, f.model);
      h.textContent = row ? "Typical agreed price for a " + row.make + " " + row.model + " on Saaz, last 90 days: " + S.money("UGX", Math.round(row.typical_price)) + " (" + row.sold_90d + " sold). You set your own price."
        : "You can change the price until a deal is agreed.";
    }
    // Keep a local copy of new, unsaved listings only (an edit is already saved in Saaz)
    function keep() {
      if (existing) return; var f = formState(); if (!f) return;
      writeLocal(DRAFT_KEY(), { vin: S.$("#vin").value, f: f, photos: photos, at: Date.now() });
    }
    function restore(d) {
      var fm = S.$("#f"); if (!fm || !d || !d.f) return;
      Object.keys(d.f).forEach(function (k) {
        var el = fm.elements[k]; if (!el || el.readOnly || el.disabled || el.type === "hidden") return;
        if (el.type === "checkbox") el.checked = !!d.f[k]; else el.value = d.f[k];
      });
      photos = (d.photos || []).slice(0, 12);
    }
    function regions() {
      var c = S.$("#ctry").value, sel = S.$("#reg");
      sel.innerHTML = S.REGIONS[c].map(function (r) { return "<option" + (r === l.region ? " selected" : "") + ">" + r + "</option>"; }).join("");
    }
    function showForm(locked) {
      S.$("#rest").innerHTML = lockedMsg + (restored ? "<p class='box' id='restored'>Your unsaved details for this car are back. <button type='button' class='btn text' id='startover'>Start again</button></p>" : "") +
        "<div class='sellgrid'><form id='f' class='stack'>" + fieldsHtml(locked) + "</form>" +
        "<aside class='sellpreview' aria-label='How buyers will see your car'><h2>How buyers will see it</h2><div id='pv'></div>" +
        "<p class='note'>This is the card on the Saaz car list. Buyers see it once the inspection is issued and Saaz approves your car." + (l.ref ? " <a href='#/car/" + esc(l.ref) + "'>Open the full car page</a>" : "") + "</p></aside></div>";
      regions();
      if (restored) restore(restored);
      drawThumbs(); priceHint();
      var so = S.$("#startover"); if (so) so.onclick = function () { writeLocal(DRAFT_KEY(), null); S.render(); };
      S.$("#f").addEventListener("input", function (e) { preview(); keep(); if (/^(price|make|model)$/.test(e.target.name)) priceHint(); });
      S.$("#f").addEventListener("change", function () { preview(); keep(); });
      S.$("#files").onchange = function (e) {
        var files = Array.prototype.slice.call(e.target.files, 0, 12 - photos.length), failed = [];
        S.toast("Uploading " + files.length + " photo" + (files.length === 1 ? "" : "s") + "…");
        Promise.all(files.map(function (file) {
          return shrink(file).then(function (blob) {
            var path = S.me().id + "/" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7) + ".webp";
            return S.db.storage.from("car-photos").upload(path, blob, { contentType: "image/webp" }).then(function (r) { if (r.error) throw r.error; photos.push(path); });
          }).then(function () { return true; }, function (e3) { failed.push(e3); return false; });
        })).then(function () {
          drawThumbs(); keep();
          if (failed.length) S.toast(failed.length + " of " + files.length + " photo" + (files.length === 1 ? "" : "s") + " didn't upload. " + S.friendly(failed[0]) + " Add " + (failed.length === 1 ? "it" : "them") + " again.", true);
          else S.toast("Photos added.");
        });
        e.target.value = "";
      };
      S.$("#f").onsubmit = function (e) {
        e.preventDefault(); var f = S.form(e.target), go = e.submitter ? e.submitter.value : "save", err = S.$("#err");
        S.$$("select[disabled]", e.target).forEach(function (s) { f[s.name] = s.value; });
        var p = { id: l.id || "", vin: S.$("#vin").value, make: f.make, model: f.model, year: f.year, fuel: f.fuel, gearbox: f.gearbox, body: f.body, engine: f.engine, colour: f.colour,
          mileage: f.mileage, country: f.country, region: f.region, plate: f.plate, price: f.price, description: f.description, photos: photos,
          logbook_name_matches: !!f.logbook_name_matches, owner_authorised: !!f.owner_authorised, saaz_owned: !!saaz };
        S.$$("button", e.target).forEach(function (b) { b.disabled = true; }); err.textContent = "";
        S.rpc("save_listing", { p: p }).then(function (id) {
          l.id = id;
          return go === "submit" ? S.rpc("submit_listing", { p_listing: id }).then(function () { return id; }) : id;
        }).then(function (id) { writeLocal(DRAFT_KEY(), null); writeLocal(START_KEY, null); S.toast(go === "submit" ? "Submitted. Saaz is putting a garage in play." : "Draft saved."); S.go("#/my/cars/" + id); })
          .catch(function (e2) { err.textContent = S.friendly(e2); S.$$("button", e.target).forEach(function (b) { b.disabled = false; }); if (l.id) history.replaceState(null, "", "#/my/edit/" + l.id); });
      };
    }
    v.innerHTML = "<div class='sellform'><h1>" + (existing ? "Edit " + esc(l.ref) : saaz ? "New Saaz car" : "List a car") + "</h1>" +
      // BA-0004: an admin on the private-seller form is pointed to the Saaz car form, which doesn't ask about the logbook
      (S.isAdmin() && !existing && !saaz ? "<p class='box spaced' data-ref='saaz-car-hint'>Is this a car Saaz owns, for example one Saaz imported? <a href='#/sell/new?saaz=1" + (preVin ? "&vin=" + encodeURIComponent(preVin) : "") + "'>List it as a Saaz car</a> instead. Saaz cars don't need the logbook or the owner's authorisation.</p>" : "") +
      "<p class='lead'>Start with the VIN or chassis number. The listing stays private until a Saaz inspection is issued and approved.</p>" +
      "<form id='vf' class='check light'><label for='vin'>VIN or chassis number</label><input id='vin' name='vin' required autocapitalize='characters' value='" + esc(preVin || "") + "'" + (existing ? " readonly" : "") + "><button>" + (existing ? "VIN locked" : "Look up") + "</button></form>" +
      "<div id='look' aria-live='polite'></div><div id='rest'></div></div>";
    if (existing) {
      S.rpc("vin_lookup", { p_vin: preVin }).then(function (r) { look = r; showForm(r.found === "saaz_import"); });
      return;
    }
    S.$("#vf").onsubmit = function (e) {
      e.preventDefault(); var vin = S.$("#vin").value.toUpperCase().replace(/\s/g, ""); S.$("#vin").value = vin;
      S.rpc("vin_lookup", { p_vin: vin }).then(function (r) {
        look = r; var box = S.$("#look");
        restored = saved && saved.vin === vin ? saved : null;
        // What a visitor typed on #/sell fills only fields the lookup left empty
        var start = restored ? null : readLocal(START_KEY);
        var fillStart = function () { if (start) ["make", "model", "year", "mileage", "price"].forEach(function (k) { if ((l[k] === "" || l[k] == null) && start[k]) l[k] = start[k]; }); };
        if (r.active_listing) { box.innerHTML = "<p class='err'>This car already has an active listing on Saaz.</p>"; S.$("#rest").innerHTML = ""; return; }
        if (r.found === "saaz_import") {
          var veh = r.vehicle; l = Object.assign(l, { make: veh.make, model: veh.model, year: veh.year, fuel: veh.fuel, gearbox: veh.gearbox, body: veh.body, engine: veh.engine, mileage: r.highest_km });
          lockedMsg = "<p class='box good'>Saaz import record found. Make, model, year, fuel, gearbox, body and engine are filled in and locked. Import mileage: " + S.km(veh.import_mileage) + ".</p>";
          fillStart(); box.innerHTML = ""; showForm(true);
        } else if (r.found === "earlier") {
          var v2 = r.vehicle; l = Object.assign(l, { make: v2.make, model: v2.model, year: v2.year, fuel: v2.fuel, gearbox: v2.gearbox, body: v2.body, engine: v2.engine });
          lockedMsg = "<p class='box'>Saaz has seen this car before. Its history carries on with this listing. Mileage can't be lower than " + S.km(r.highest_km) + ".</p>";
          fillStart(); box.innerHTML = ""; showForm(false);
        } else {
          var d = S.decode(vin); l = Object.assign(l, { make: d.make || "", model: d.model || "", year: d.year || "" });
          lockedMsg = "<p class='box'>New to Saaz. " + (d.make ? "Partial decode from the " + esc(d.how) + ": " + esc([d.make, d.model, d.year].filter(Boolean).join(" ")) + ". Check it." : "The " + esc(d.how) + " gave nothing. Fill in the details.") +
            " Importer unknown. This listing starts the car's Saaz record.</p>";
          fillStart(); box.innerHTML = ""; showForm(false);
        }
      }).catch(function (e2) { S.$("#look").innerHTML = "<p class='err'>" + esc(S.friendly(e2)) + "</p>"; });
    };
    if (preVin) S.$("#vf").requestSubmit();
  }
  S.route("/sell/new", function (v, m, q) {
    var saaz = q.get("saaz") === "1";
    if (saaz && !S.isAdmin()) { v.innerHTML = "<div class='empty'><b>Admins only</b></div>"; return; }
    return Promise.all([S.sellFacts(), S.soldPrices()]).then(function (r) { sellForm(v, null, saaz, q.get("vin"), r[0], r[1]); });
  }, "user");
  S.route("/my/edit/([0-9a-f-]+)", function (v, m) {
    return S.q(S.db.from("listings").select("*, vehicles(vin)").eq("id", m[0])).then(function (rows) {
      var l = rows[0]; if (!l) throw new Error("Listing not found.");
      return Promise.all([S.sellFacts(), S.soldPrices()]).then(function (r) { sellForm(v, l, l.saaz_owned, l.vehicles.vin, r[0], r[1]); });
    });
  }, "user");

  // ---------- The seller page (#/sell): public, no account needed to read it ----------
  // Every claim here is a rule the product enforces. Sources: README ("no Saaz review, no listing"; payments and the platform fee left out),
  // help.html (the garage sets the inspection price, paid to the garage), settings (lowest price, report valid days), inspection_scopes (the checks).
  S.route("/sell", function (v) {
    v.className = "sellpage";
    var start = readLocal(START_KEY) || {}, signed = S.signedIn();
    var go = signed ? "#/sell/new" : "#/signup";
    var cta = function (label, cls) { return "<a class='btn " + (cls || "") + "' data-start href='" + go + "'>" + label + "</a>"; };
    var field = function (k, label, type, ph) {
      return "<label>" + label + "<input name='" + k + "' " + (type === "number" ? "type='number' inputmode='numeric' min='0'" : "autocapitalize='words'") +
        " placeholder='" + ph + "' value='" + esc(start[k] == null ? "" : start[k]) + "'></label>";
    };
    v.innerHTML =
      "<section class='hero sellhero' data-ref='sell-hero'><div class='wrap'>" +
        "<div class='sellcopy'><h1 class='display'>Your car deserves the right buyer.</h1>" +
        "<p class='sub'>Free to list. A certified garage inspects your car, buyers see the report, and you decide which offers to take.</p>" +
        "<div class='row heroact'>" + cta("Start selling your car") + "<button type='button' class='btn ghost' id='tohow'>How it works</button></div></div>" +
        "<div class='tryit' data-ref='sell-try'><h2>Your car, the way buyers will see it</h2>" +
          "<form id='tf' class='tryfields' autocomplete='off'>" + field("make", "Make", "", "Toyota") + field("model", "Model", "", "Harrier") +
            field("year", "Year", "number", "2015") + field("mileage", "Mileage (km)", "number", "78000") +
            "<label class='full'>Asking price (UGX)<input name='price' type='number' inputmode='numeric' min='0' step='100000' placeholder='72000000' value='" + esc(start.price || "") + "'></label></form>" +
          "<div id='tpv' aria-live='polite'></div>" +
          "<p class='note'>Kept on this phone only. It fills in the listing form when you start.</p></div>" +
      "</div></section>" +

      "<section class='band white' id='inspection' data-ref='sell-inspection'><div class='wrap'><div class='split'>" +
        "<div><h2>Every car on Saaz is inspected first</h2>" +
          "<p class='lead'>No inspection, no listing. A certified garage checks your car in person, and the report goes on your listing so buyers don't have to guess.</p>" +
          "<h3 class='minihead'>What the garage checks</h3><ul class='checkgrid' id='checks'><li>Engine</li><li>Gearbox</li><li>Brakes</li><li>Steering</li><li>Tyres</li><li>Electrics</li></ul>" +
          "<p class='note' id='limits'>The report records the car on the day of the inspection. It is not a guarantee.</p></div>" +
        "<figure class='samplereport' aria-label='Sample inspection report'><span class='sample'>Sample</span>" +
          "<div class='insp-card'><div class='insp-head'>" + S.chip("pass") + "<span>84/100</span><span>Report SZR-SAMPLE</span></div>" +
          "<ul class='findings'><li><span class='lvl attention'>Attention</span><div><b>Tyres</b><span>Front tyres at about 30% tread.</span></div></li><li><span class='lvl note'>Note</span><div><b>Body and paint</b><span>Small scratch on the rear bumper.</span></div></li></ul>" +
          "<p class='note'>Each real report has a number, a score out of 100, the garage's notes, and a code anyone can use to <a href='#/verify'>check it is real and unchanged</a>.</p></div></figure>" +
      "</div></div></section>" +

      "<section class='band soft' data-ref='sell-costs'><div class='wrap'><div class='sechead'><h2>What it costs</h2></div><dl class='costs'>" +
        "<div><dt>Listing your car</dt><dd>Free. Saaz charges no listing fee and no commission.</dd></div>" +
        "<div><dt>The inspection</dt><dd>Required before your car goes live. The garage sets the price and you pay the garage.</dd></div>" +
        "<div><dt>Extra checks</dt><dd id='extras'>Optional. Ask for a closer look at one area, with its own report.</dd></div>" +
        "<div><dt>Money through Saaz</dt><dd>None. You and the buyer settle payment yourselves once you agree a deal.</dd></div>" +
      "</dl></div></section>" +

      "<section class='band white' data-ref='sell-price'><div class='wrap'><div class='sechead'><h2>You set the price</h2><p>Buyers see the report next to your price, so they can see what they are paying for.</p></div>" +
        "<div class='features three'>" +
          "<div><div><b>Your number</b><span id='pricerule'>You choose the asking price and can change it until a deal is agreed. A live car keeps its inspection when only the price changes.</span></div></div>" +
          "<div><div><b>Offer rules</b><span>Set a minimum offer. Offers below it are turned down for you, or flagged for you to decide. Buyers never see your minimum.</span></div></div>" +
          "<div><div><b>Your phone stays private</b><span>Buyers make offers inside Saaz. Phone numbers and emails are shared only after you both agree.</span></div></div>" +
        "</div><div id='market'></div></div></section>" +

      "<section class='band soft' id='how' data-ref='sell-steps'><div class='wrap'><div class='sechead'><h2>How selling works</h2></div><ol class='steps sellsteps'>" +
        "<li><span class='n'>1</span><div><b>Add your car</b><span>Start with the VIN or chassis number, then the details and 4 to 12 photos. It saves as a draft only you can see.</span></div></li>" +
        "<li><span class='n'>2</span><div><b>A certified garage inspects it</b><span>Saaz offers your car to the nearest certified garage. You agree, they set a date, and they inspect it in person.</span></div></li>" +
        "<li><span class='n'>3</span><div><b>Saaz approves it and it goes live</b><span>Saaz checks the report. Your car appears on Saaz with the report attached.</span></div></li>" +
        "<li><span class='n'>4</span><div><b>Buyers make offers</b><span>Accept, counter or decline. Contact details are shared once you agree.</span></div></li>" +
      "</ol></div></section>" +

      "<section class='band white' data-ref='sell-faq'><div class='wrap'><div class='sechead'><h2>Questions sellers ask</h2></div><div class='faq flush'>" +
        "<details><summary>Is listing my car free?</summary><p>Yes. Saaz charges nothing to list or to sell. You pay the garage for the inspection.</p></details>" +
        "<details><summary>Can I list without an inspection?</summary><p>No. A car goes live only after a Saaz inspection is issued and Saaz approves it. Until then it is a private draft.</p></details>" +
        "<details><summary>What does the inspection cost?</summary><p>Each certified garage sets its own price, and you pay the garage directly. No money moves through Saaz.</p></details>" +
        "<details><summary>Can I change my listing later?</summary><p>You can change the price until a deal is agreed. To change anything else on a live car, it goes back to draft, and submitting again books a new inspection.</p></details>" +
        "<details><summary>What happens when a buyer is interested?</summary><p>They make an offer in Saaz. You accept, counter or decline, or let your offer rules handle low offers. Contacts are shared once you both agree.</p></details>" +
        "<details><summary>How do I know my car is live?</summary><p>My cars shows each car's stage, from draft to sold. Saaz also sends a notice to your Saaz inbox when your car is approved.</p></details>" +
        "<details><summary>How long does a report last?</summary><p id='validfaq'>A report is valid for 60 days. After that you submit the car again for a new inspection.</p></details>" +
      "</div></div></section>" +

      "<section class='band dark sellclose' data-ref='sell-close'><div class='wrap'><h2>Ready to put your car on the market?</h2>" +
        "<p class='sub'>Start with your VIN or chassis number. Save a draft and finish when you're ready.</p><div class='row heroact'>" + cta("List your car for free") + "</div></div></section>";

    // Starting: what was typed above is kept for the form; signed-out sellers come back to the form after creating an account or signing in
    S.$$("[data-start]", v).forEach(function (a) { a.onclick = function () { if (!signed) S.after = "#/sell/new"; }; });
    S.$("#tohow").onclick = function () { S.$("#how").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); };
    var tf = S.$("#tf");
    function tryCard() {
      var f = S.form(tf), has = ["make", "model", "year", "mileage", "price"].some(function (k) { return f[k] !== ""; });
      S.$("#tpv").innerHTML = S.card({ make: f.make, model: f.model, year: f.year, mileage: f.mileage === "" ? null : f.mileage, price: f.price === "" ? null : f.price, currency: "UGX", photos: [] },
        { preview: true, tag: "<span class='car-tag pending'>Inspection result goes here</span>" });
      writeLocal(START_KEY, has ? f : null);
    }
    tf.addEventListener("input", tryCard); tf.onsubmit = function (e) { e.preventDefault(); };
    tryCard();

    // Filled in from the database after first paint; a slow phone sees the page straight away
    var here = location.hash;
    S.sellFacts().then(function (facts) {
      if (location.hash !== here) return;
      var gen = facts.scopes && facts.scopes.by.general;
      if (gen) S.$("#checks").innerHTML = gen.checks.map(function (k) { return "<li>" + esc(S.checkName(k)) + "</li>"; }).join("");
      var extra = facts.scopes ? facts.scopes.list.filter(function (x) { return x.key !== "general"; }).map(function (x) { return x.name; }) : [];
      if (extra.length) S.$("#extras").textContent = "Optional: " + extra.join(", ") + ". Each has its own report, and the garage sets its price.";
      S.$("#limits").textContent = "The report records the car on the day of the inspection. It is not a guarantee. It is valid for " + facts.validDays + " days.";
      S.$("#validfaq").textContent = "A report is valid for " + facts.validDays + " days. After that you submit the car again for a new inspection.";
      S.$("#pricerule").textContent = "You choose the asking price, from " + S.money("UGX", facts.minPrice) + ", and can change it until a deal is agreed. A live car keeps its inspection when only the price changes.";
    });
    S.soldPrices().then(function (rows) {
      if (location.hash !== here) return;
      S.$("#market").innerHTML = rows.length
        ? "<h3 class='minihead'>Agreed prices on Saaz, last 90 days</h3>" + S.sellingTable(rows.slice(0, 5)) + "<p class='note'><a href='#/selling'>See every model on What's selling</a></p>"
        : "<p class='note'>Agreed prices by model will show on <a href='#/selling'>What's selling</a> as cars sell on Saaz.</p>";
    });
  });

  // ---------- My cars ----------
  S.carRows = function (rows, saaz) {
    if (!rows.length) return "<div class='empty'><b>No cars yet</b><span><a href='#/sell/new" + (saaz ? "?saaz=1" : "") + "'>List a car</a></span></div>";
    return "<ul class='rows'>" + rows.map(function (l) {
      var c = l.conversation;
      return "<li><a href='#/my/cars/" + l.id + "'><div class='thumb'>" + (l.photos[0] ? "<img src='" + esc(S.photo(l.photos[0])) + "' alt='' loading='lazy'>" : "") + "</div><div class='grow'>" +
        "<b>" + esc(S.name(l)) + "</b> " + S.chip(l.status) + "<small>" + esc(l.ref) + " · " + S.money(l.currency, l.price) +
        (c ? " · " + (c.status === "agreed" ? "Booked with " : "In play: ") + esc(c.garage) : l.line_empty ? " · Saaz is finding a garage" : "") + "</small>" +
        "<div class='demand'><span>" + l.views_7d + " views this week</span><span>" + l.saves + " saves</span><span>" + l.offers + " offers</span>" + (l.open_offers ? "<span class='hot'>" + l.open_offers + " open</span>" : "") + "</div></div></a></li>";
    }).join("") + "</ul>";
  };
  S.route("/my/cars", function (v) {
    return S.rpc("my_listings", { p_saaz: false }).then(function (rows) {
      v.innerHTML = "<div class='pagehead row'><h1>My cars</h1><a class='btn' href='#/sell/new'>List a car</a></div>" + S.carRows(rows) +
        "<p class='note'><a href='#/selling'>See what's selling</a> · <a href='#/offers'>Offers I made</a> · <a href='#/account'>My account</a></p>";
    });
  }, "user");

  // ---------- One car (seller, or admin for Saaz cars) ----------
  function convoHtml(c, msgs, sellerSide) {
    var closed = ["in_play", "agreed"].indexOf(c.status) < 0;
    return "<div class='chat'><div class='chathead'><b>" + esc(c.garages ? c.garages.name : "Garage") + "</b> " + S.chip(c.status) +
      (c.status === "in_play" && !c.garage_first_message_at ? "<small>Has until " + S.when(c.deadline) + " to message you</small>" : "") +
      (c.review_date ? "<small>Inspection date: " + S.day(c.review_date) + "</small>" : "") + "</div>" +
      "<div class='msgs'>" + (msgs.length ? msgs.map(function (x) {
        return "<p class='msg " + (x.side === (sellerSide ? "seller" : "garage") ? "me" : "them") + "'>" + esc(x.body) + "<small>" + S.when(x.created_at) + "</small></p>";
      }).join("") : "<p class='note'>" + (sellerSide ? "The garage messages first." : "Message the seller to arrange the inspection.") + "</p>") + "</div>" +
      (closed ? "" : "<form class='send' data-c='" + c.id + "'><input name='body' placeholder='Write a message' maxlength='2000' required" + (sellerSide && !c.garage_first_message_at ? " disabled" : "") + "><button class='btn small'" + (sellerSide && !c.garage_first_message_at ? " disabled" : "") + ">Send</button></form>") +
      (c.status === "in_play" && closed === false ? "<p class='note'>Phone numbers and emails are hidden until " + (sellerSide ? "you agree" : "the seller agrees") + ". After that, share whatever you like. Saaz doesn't read these messages.</p>" : "") + "</div>";
  }
  S.convoHtml = convoHtml;
  S.wireSend = function (root) {
    S.$$("form.send", root).forEach(function (f) {
      f.onsubmit = function (e) { e.preventDefault(); var body = S.form(f).body; S.act(f.querySelector("button"), function () { return S.rpc("send_message", { p_conv: f.dataset.c, p_body: body }); }); };
    });
  };

  S.route("/my/cars/([0-9a-f-]+)", function (v, m) {
    var id = m[0];
    return Promise.all([
      S.q(S.db.from("listings").select("*").eq("id", id)),
      S.q(S.db.from("conversations").select("*, garages(name)").eq("listing_id", id).order("opened_at", { ascending: false })),
      S.rpc("listing_stats", { p_listing: id }),
      S.q(S.db.from("deals").select("*").eq("listing_id", id).order("updated_at", { ascending: false })),
      S.rpc("listing_history", { p_listing: id })
    ]).then(function (res) {
      var l = res[0][0]; if (!l) throw new Error("Listing not found.");
      var convs = res[1], st = res[2] || {}, deals = res[3], hist = res[4] || [];
      var open = convs.filter(function (c) { return c.status === "in_play" || c.status === "agreed"; })[0];
      return (open ? S.q(S.db.from("messages").select("*").eq("conversation_id", open.id).order("created_at")) : Promise.resolve([])).then(function (msgs) {
        return (l.current_review_id ? S.q(S.db.from("reviews").select("*").eq("id", l.current_review_id)) : Promise.resolve([])).then(function (rv) {
          draw(v, l, open, msgs, st, deals, hist, rv[0], convs);
        });
      });
    });
  }, "user");

  function draw(v, l, open, msgs, st, deals, hist, review, convs) {
    var editable = ["draft", "changes_requested"].indexOf(l.status) >= 0;
    var actions = [];
    if (["sold", "withdrawn", "rejected"].indexOf(l.status) < 0) actions.push("<a class='btn ghost' href='#/car/" + esc(l.ref) + "'>" + (l.status === "live" || l.status === "reserved" ? "Open the car page" : "See it as buyers will") + "</a>");
    if (editable) actions.push("<a class='btn' href='#/my/edit/" + l.id + "'>Edit</a>", "<div id='scopebox'></div>", "<button class='btn' id='submit'>Submit for a Saaz inspection</button>");
    if (["awaiting_review", "review_booked"].indexOf(l.status) >= 0 && !l.saaz_owned) actions.push("<form id='addscope' class='stack'><div id='scopebox'></div><button class='btn small ghost'>Request these inspections</button></form>");
    if (l.status === "re_review_due") actions.push("<button class='btn' id='submit'>Submit for a new Saaz inspection</button>");
    if (["live", "re_review_due"].indexOf(l.status) >= 0) actions.push("<button class='btn ghost' id='reopen'>Change something other than the price</button>");
    if (["reserved", "sold", "withdrawn", "rejected"].indexOf(l.status) < 0) actions.push("<button class='btn ghost' id='withdraw'>Withdraw</button>");
    var priceForm = ["live", "draft", "changes_requested", "awaiting_review", "review_booked", "awaiting_approval"].indexOf(l.status) >= 0
      ? "<form id='pricef' class='inlineform'><label>Price (" + l.currency + ")<input name='price' type='number' value='" + l.price + "' required></label><button class='btn small'>Change price</button></form><p class='note'>A live car keeps its inspection when only the price changes.</p>" : "";
    var daily = (st.daily_14 || []).map(function (d) { return { label: S.day(d.day), short: String(new Date(d.day + "T00:00:00").getDate()), value: d.views }; });
    var model = st.model || {};
    v.innerHTML = "<p class='crumbs'><a href='" + (l.saaz_owned ? "#/admin/saaz" : "#/my/cars") + "'>" + (l.saaz_owned ? "Saaz cars" : "My cars") + "</a> / " + esc(l.ref) + "</p>" +
      "<div class='pagehead'><h1>" + esc(S.name(l)) + "</h1>" + S.chip(l.status) + "</div>" + progress(l.status) +
      "<p class='box'>" + esc(STATUS_TEXT[l.status] || "") + (l.line_empty ? " No garage is left in line: Saaz will find one and let you know." : "") +
        (NEXT_TEXT[l.status] ? " " + esc(NEXT_TEXT[l.status]) : "") + "</p>" +
      (l.admin_note ? "<p class='box warn'><b>Note from Saaz:</b> " + esc(l.admin_note) + "</p>" : "") +
      "<div class='row'>" + actions.join("") + "</div>" + priceForm +
      (open ? "<section><h2>" + (open.status === "agreed" ? "Your garage" : "Garage in play") + "</h2>" + convoHtml(open, msgs, true) +
        (open.status === "in_play" ? "<div class='row'><button class='btn' id='agree'" + (open.garage_first_message_at ? "" : " disabled") + ">Agree: book my inspection with this garage</button>" +
          "<button class='btn ghost' id='pass'>Pass to the next garage</button></div><div id='passbox'></div>" : "") + "</section>" : "") +
      (review ? "<section><h2>Saaz inspection</h2><div class='insp-card'><div class='insp-head'>" + S.chip(review.verdict) + "<span>" + review.score + "/100 · " + esc(review.doc_no) + "</span></div>" +
        (review.odometer_flag ? "<p class='err'>Odometer flag: " + esc(review.odometer_flag) + "</p>" : "") + "<a href='#/report/" + esc(review.verify_code) + "'>Open the report</a></div></section>" : "") +
      "<section><h2>Demand</h2><div class='stats'>" +
        [["Views, last 7 days", st.views_7d], ["Views in total", st.views_total], ["Saves", st.saves], ["Offers", st.offers], ["Auto-rejected offers", st.auto_rejected],
         ["Highest offer", st.highest_offer ? S.money(l.currency, st.highest_offer) : "–"], ["Views a day since live", st.views_per_day], ["Same model, views a day", st.model_views_per_day == null ? "–" : st.model_views_per_day],
         ["Median days to sell, this model", model.median_days == null ? "–" : Math.round(model.median_days)], ["Typical agreed price, this model", model.typical_price ? S.money(l.currency, Math.round(model.typical_price)) : "–"]]
          .map(function (x) { return "<div><b>" + esc(x[1] == null ? 0 : x[1]) + "</b><span>" + x[0] + "</span></div>"; }).join("") + "</div>" +
        "<h3>Views, last 14 days</h3>" + S.bars(daily) + "</section>" +
      "<section><h2>Offer rules</h2><form id='rules' class='stack'><div class='grid2'><label>Minimum offer, percent of asking<input name='min_pct' type='number' min='1' max='100' value='" + esc(l.rule_min_pct || "") + "'></label>" +
        "<label>Or minimum amount (" + l.currency + ")<input name='min_amount' type='number' min='1' value='" + esc(l.rule_min_amount || "") + "'></label></div>" +
        "<label class='inline'><input type='checkbox' name='no_trade_in' value='1'" + (l.rule_no_trade_in ? " checked" : "") + "> Don't accept offers with a trade-in</label>" +
        "<label class='inline'><input type='checkbox' name='on_counters' value='1'" + (l.rule_on_counters ? " checked" : "") + "> Apply the rules to buyers' counter-offers too</label>" +
        "<fieldset class='seg'><legend>When an offer breaks a rule</legend><label><input type='radio' name='auto_reject' value='1'" + (l.auto_reject ? " checked" : "") + "><span>Reject automatically</span></label>" +
        "<label><input type='radio' name='auto_reject' value=''" + (l.auto_reject ? "" : " checked") + "><span>Flag it and I decide</span></label></fieldset>" +
        "<p class='note'>With auto-reject on, the buyer is told which rule they missed, never your minimum, and can offer again.</p><button class='btn small'>Save offer rules</button></form></section>" +
      "<section><h2>Offers</h2>" + (deals.length ? "<ul class='list'>" + deals.map(function (d) {
        return "<li><a href='#/deals/" + d.id + "'><b>" + S.money(l.currency, d.amount) + "</b> " + S.chip(d.status) + (d.flag ? " <span class='chip s-flag'>Breaks your offer rules</span>" : "") +
          (d.trade_in ? " <small>with trade-in</small>" : "") + "<small>" + S.when(d.updated_at) + "</small></a></li>";
      }).join("") + "</ul>" : "<p class='note'>No offers yet.</p>") + "</section>" +
      "<section><h2>Every inspection of this car</h2><div id='insps'><p class='loading'>Loading…</p></div></section>" +
      "<section><h2>History of this car</h2><ul class='timeline'>" + hist.map(function (h) { return "<li><small>" + S.when(h.at) + "</small> " + esc(h.who) + ": " + esc(h.action) + "</li>"; }).join("") + "</ul>" +
      (convs.length > 1 ? "<p class='note'>Garages so far: " + convs.map(function (c) { return esc(c.garages.name) + " (" + S.label(c.status) + ")"; }).join(", ") + "</p>" : "") + "</section>";
    S.loadInspections("insps", l.id);
    S.wireSend(v);
    var b;
    var extraScopes = function () { return S.$$("input[name=xscope]:checked").map(function (x) { return x.value; }); };
    if ((b = S.$("#submit"))) b.onclick = function () { var xs = extraScopes(); S.act(b, function () {
      return S.rpc("submit_listing", { p_listing: l.id }).then(function () { return xs.length ? S.rpc("request_inspections", { p_listing: l.id, p_scopes: xs }) : null; });
    }, "Submitted. Your inspection IDs are on this page; Saaz is putting a garage in play."); };
    var adds = S.$("#addscope"); if (adds) adds.onsubmit = function (e) { e.preventDefault(); var xs = extraScopes(); if (!xs.length) { S.toast("Tick at least one.", true); return; }
      S.act(adds.querySelector("button"), function () { return S.rpc("request_inspections", { p_listing: l.id, p_scopes: xs }); }, "Requested. Each one has its own inspection ID."); };
    S.scopes().then(function (sc) {
      var box = S.$("#scopebox"); if (!box) return;
      box.innerHTML = "<fieldset class='checks2'><legend>Also inspect separately (optional)</legend>" + sc.list.filter(function (x) { return x.key !== "general"; }).map(function (x) {
        return "<label class='inline'><input type='checkbox' name='xscope' value='" + esc(x.key) + "'> " + esc(x.name) + "</label>"; }).join("") +
        "</fieldset><p class='note'>Every car for sale gets a General inspection. Each extra one gets its own inspection ID and can be done by a different inspector. Extra reports don't decide whether the car goes live.</p>";
    });
    if ((b = S.$("#withdraw"))) { var wb = b; wb.onclick = function () { S.confirmBtn(wb, function () { S.act(wb, function () { return S.rpc("withdraw_listing", { p_listing: l.id }); }, "Withdrawn."); }); }; }
    if ((b = S.$("#reopen"))) { var rb = b; rb.onclick = function () { S.confirmBtn(rb, function () { S.act(rb, function () { return S.rpc("reopen_for_changes", { p_listing: l.id }); }, "Back to draft. Submitting again books a new Saaz inspection."); }); }; }
    if ((b = S.$("#agree"))) { var ab = b; ab.onclick = function () { S.act(ab, function () { return S.rpc("seller_respond", { p_conv: open.id, p_agree: true }); }, "Agreed. The garage will set a inspection date."); }; }
    if ((b = S.$("#pass"))) b.onclick = function () {
      S.$("#passbox").innerHTML = "<form id='pf' class='stack box'><label>Reason (optional, the garage won't see it)<input name='reason' maxlength='300'></label><button class='btn small'>Pass to the next garage</button></form>";
      S.$("#pf").onsubmit = function (e) { e.preventDefault(); var f = S.form(e.target); S.act(e.target.querySelector("button"), function () { return S.rpc("seller_respond", { p_conv: open.id, p_agree: false, p_reason: f.reason }); }, "Passed. The next garage is coming in."); };
    };
    var pf = S.$("#pricef"); if (pf) pf.onsubmit = function (e) { e.preventDefault(); var f = S.form(pf); S.act(pf.querySelector("button"), function () { return S.rpc("change_price", { p_listing: l.id, p_price: +f.price }); }, "Price changed."); };
    S.$("#rules").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target);
      S.act(e.target.querySelector("button"), function () { return S.rpc("set_offer_rules", { p_listing: l.id, p: { min_pct: f.min_pct, min_amount: f.min_amount, no_trade_in: !!f.no_trade_in, on_counters: !!f.on_counters, auto_reject: !!f.auto_reject } }); }, "Offer rules saved.");
    };
  }

  // ---------- Deals ----------
  S.route("/offers", function (v) {
    return S.rpc("my_deals").then(function (rows) {
      var mine = rows.filter(function (r) { return r.side === "buyer"; });
      v.innerHTML = "<h1>Offers I made</h1>" + (mine.length ? "<ul class='list'>" + mine.map(function (r) {
        return "<li><a href='#/deals/" + r.deal.id + "'><b>" + esc(r.listing.year + " " + r.listing.make + " " + r.listing.model) + "</b> " + S.chip(r.deal.status) +
          "<small>" + S.money(r.listing.currency, r.deal.amount) + " · asking " + S.money(r.listing.currency, r.listing.price) + "</small></a></li>";
      }).join("") + "</ul>" : "<div class='empty'><b>No offers yet</b><span><a href='#/browse'>Browse cars</a></span></div>");
    });
  }, "user");

  S.route("/deals/([0-9a-f-]+)", function (v, m) {
    return S.rpc("deal_view", { p_deal: m[0] }).then(function (d) {
      var deal = d.deal, l = d.listing, side = d.side, cur = l.currency, acts = [];
      var myOk = side === "buyer" ? deal.buyer_ok : deal.seller_ok;
      if (deal.status === "negotiating" && side !== "admin") {
        if (!myOk) acts.push("<button class='btn' data-a='accept'>Accept " + S.money(cur, deal.amount) + "</button>");
        acts.push("<form class='inlineform' id='cf'><label>Counter (" + cur + ")<input name='amount' type='number' required></label><button class='btn small'>Send counter</button></form>");
        if (side === "seller") acts.push("<button class='btn ghost' data-a='reject'>Reject</button>");
        if (side === "buyer") acts.push("<button class='btn ghost' data-a='withdraw'>Withdraw my offer</button>");
      }
      if (side === "admin") {
        if (deal.status === "negotiating") acts.push("<form class='inlineform' id='pf'><label>Propose a price to both (" + cur + ")<input name='amount' type='number' required></label><button class='btn small'>Propose</button></form>",
          "<form class='inlineform' id='mf'><label>Mark agreed: how did both confirm?<input name='note' required></label><button class='btn small'>Mark agreed</button></form>");
        if (deal.status === "agreed") acts.push("<button class='btn' data-a='complete'>Sale completed (handover confirmed)</button>");
        if (deal.status === "negotiating" || deal.status === "agreed") acts.push("<button class='btn ghost' data-a='cancel'>Cancel deal</button>");
      }
      var amt = function (f) { return { action: "counter", amount: +f.amount }; }, num = "<label>Counter (" + cur + ")<input name='amount' type='number' required></label>";
      var forSeller = [{ kind: "deal_seller", target: deal.id, label: "Counter for the seller", fields: num, p: amt },
        { kind: "deal_seller", target: deal.id, label: "Accept " + S.money(cur, deal.amount) + " for the seller", p: function () { return { action: "accept" }; } },
        { kind: "deal_seller", target: deal.id, label: "Decline for the seller", confirm: true, p: function () { return { action: "reject" }; } }];
      var forBuyer = [{ kind: "deal_buyer", target: deal.id, label: "Counter for the buyer", fields: num, p: amt },
        { kind: "deal_buyer", target: deal.id, label: "Accept " + S.money(cur, deal.amount) + " for the buyer", p: function () { return { action: "accept" }; } },
        { kind: "deal_buyer", target: deal.id, label: "Withdraw for the buyer", confirm: true, p: function () { return { action: "withdraw" }; } }];
      var actFor = side === "admin" && deal.status === "negotiating" && !l.saaz_owned
        ? S.actFor("afs", "Act for the seller", "Use when the seller asks you to, or can't do it themselves. You can't accept a figure an admin entered for the other side.", forSeller) +
          S.actFor("afb", "Act for the buyer", "Use when the buyer asks you to, or can't do it themselves.", forBuyer) : "";
      v.innerHTML = "<p class='crumbs'><a href='" + (side === "buyer" ? "#/offers" : side === "admin" ? "#/admin/deals" : "#/my/cars/" + l.id) + "'>Back</a></p>" +
        "<div class='pagehead'><h1>" + esc(l.year + " " + l.make + " " + l.model) + "</h1>" + S.chip(deal.status) + "</div>" +
        "<p class='lead'>Current figure <b>" + S.money(cur, deal.amount) + "</b> · asking " + S.money(cur, l.price) + (deal.trade_in ? " · includes a trade-in" : "") + "</p>" +
        (deal.flag && side !== "buyer" ? "<p class='box warn'>Breaks your offer rules: " + esc(deal.flag) + "</p>" : "") +
        (deal.status === "negotiating" ? "<p class='note'>Buyer " + (deal.buyer_ok ? "accepts" : "hasn't accepted") + " this figure · Seller " + (deal.seller_ok ? "accepts" : "hasn't accepted") + ". The deal is agreed when both accept the latest figure.</p>" : "") +
        (d.contacts ? "<div class='box good'><b>Contact details</b><p>" + esc(d.contacts.name) + (d.contacts.mobile ? " · " + esc(d.contacts.mobile) : "") + (d.contacts.email ? " · " + esc(d.contacts.email) : "") + (d.contacts.note ? " · " + esc(d.contacts.note) : "") +
          "</p><p class='note'>Arrange the handover between you. No money moves through Saaz.</p></div>" : "") +
        "<div class='row'>" + acts.join("") + "</div>" + actFor +
        "<section><h2>History of this deal</h2><ul class='timeline'>" + (d.events || []).map(function (e) {
          return "<li><small>" + S.when(e.created_at) + "</small> " + (e.admin_id ? "Saaz team, for the " + esc(e.by_side) : esc(S.label(e.by_side))) + ": " + esc(S.label(e.kind)) + (e.amount ? " " + S.money(cur, e.amount) : "") + (e.message ? " · “" + esc(e.message) + "”" : "") + (e.admin_reason ? " <small>Reason: " + esc(e.admin_reason) + "</small>" : "") + "</li>";
        }).join("") + "</ul></section>";
      S.$$("[data-a]", v).forEach(function (b) {
        b.onclick = function () {
          var run = function () { S.act(b, function () { return S.rpc("deal_action", { p_deal: deal.id, p_action: b.dataset.a }); }, "Done."); };
          if (["reject", "cancel", "complete", "withdraw"].indexOf(b.dataset.a) >= 0) S.confirmBtn(b, run); else run();
        };
      });
      var cf = S.$("#cf"); if (cf) cf.onsubmit = function (e) {
        e.preventDefault(); var f = S.form(cf);
        S.act(cf.querySelector("button"), function () { return S.rpc("deal_action", { p_deal: deal.id, p_action: "counter", p_amount: +f.amount }); }, function (r) { return r && r.message ? r.message : "Counter sent."; });
      };
      var pf = S.$("#pf"); if (pf) pf.onsubmit = function (e) { e.preventDefault(); var f = S.form(pf); S.act(pf.querySelector("button"), function () { return S.rpc("deal_action", { p_deal: deal.id, p_action: "propose", p_amount: +f.amount }); }, "Proposed to both."); };
      S.wireActFor("afs", forSeller); S.wireActFor("afb", forBuyer);
      var mf = S.$("#mf"); if (mf) mf.onsubmit = function (e) { e.preventDefault(); var f = S.form(mf); S.act(mf.querySelector("button"), function () { return S.rpc("deal_action", { p_deal: deal.id, p_action: "mark_agreed", p_message: f.note }); }, "Marked agreed."); };
    });
  }, "user");
})();
