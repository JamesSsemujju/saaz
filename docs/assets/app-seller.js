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

  // ---------- List a car ----------
  function sellForm(v, existing, saaz, preVin) {
    var l = existing || {}, look = null, photos = (l.photos || []).slice();
    var lockedMsg = "";
    function fieldsHtml(locked) {
      var dis = locked ? " readonly" : "";
      return "<div class='grid2'><label>Make<input name='make' required value='" + esc(l.make || "") + "'" + dis + "></label><label>Model<input name='model' required value='" + esc(l.model || "") + "'" + dis + "></label>" +
        "<label>Year<input name='year' type='number' min='1980' max='" + (new Date().getFullYear() + 1) + "' required value='" + esc(l.year || "") + "'" + dis + "></label>" +
        "<label>Fuel<select name='fuel' required" + (locked ? " disabled" : "") + ">" + ["Petrol", "Diesel", "Hybrid", "Electric"].map(function (x) { return "<option" + (l.fuel === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Gearbox<select name='gearbox' required" + (locked ? " disabled" : "") + ">" + ["Automatic", "Manual"].map(function (x) { return "<option" + (l.gearbox === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Body<select name='body' required" + (locked ? " disabled" : "") + ">" + ["Saloon", "Hatchback", "SUV", "Station wagon", "Pickup", "Van", "Minibus", "Coupe"].map(function (x) { return "<option" + (l.body === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
        "<label>Engine<input name='engine' placeholder='2.0' value='" + esc(l.engine || "") + "'" + dis + "></label><label>Colour<input name='colour' required value='" + esc(l.colour || "") + "'></label>" +
        "<label>Mileage (km)<input name='mileage' type='number' min='0' max='1000000' required value='" + esc(l.mileage == null ? "" : l.mileage) + "'></label>" +
        "<input type='hidden' name='country' id='ctry' value='UG'>" +
        "<label>Region<select name='region' id='reg' required></select></label><label>Number plate (Uganda)<input name='plate' required placeholder='UBA 123X' value='" + esc(l.plate || "") + "' autocapitalize='characters'></label>" +
        "<label>Asking price (UGX)<input name='price' type='number' required min='1000000' step='1000' value='" + esc(l.price || "") + "'></label></div>" +
        "<label>Description<textarea name='description' rows='4' minlength='30' required>" + esc(l.description || "") + "</textarea></label>" +
        "<div><b>Photos<span class='req' aria-hidden='true'> *</span></b> <small>4 to 12. Shrunk to about 30 KB each.</small><div id='thumbs' class='thumbs'></div><input type='file' id='files' accept='image/*' multiple></div>" +
        (saaz ? "" : "<p class='note'>Tick one of these two<span class='req' aria-hidden='true'> *</span></p><label class='inline'><input type='checkbox' name='logbook_name_matches' value='1'" + (l.logbook_name_matches ? " checked" : "") + "> The logbook is in my name</label>" +
          "<label class='inline'><input type='checkbox' name='owner_authorised' value='1'" + (l.owner_authorised ? " checked" : "") + "> The owner authorised me to sell</label>") +
        "<p class='err' id='err' role='alert'></p><div class='row'><button class='btn' name='go' value='save'>Save draft</button><button class='btn dark' name='go' value='submit'>Save and submit for a Saaz inspection</button></div>";
    }
    function drawThumbs() {
      S.$("#thumbs").innerHTML = photos.map(function (p, i) { return "<figure><img src='" + esc(S.photo(p)) + "' alt=''><button type='button' data-i='" + i + "' aria-label='Remove photo'>×</button></figure>"; }).join("");
      S.$$("#thumbs button").forEach(function (b) { b.onclick = function () { photos.splice(+b.dataset.i, 1); drawThumbs(); }; });
    }
    function regions() {
      var c = S.$("#ctry").value, sel = S.$("#reg");
      sel.innerHTML = S.REGIONS[c].map(function (r) { return "<option" + (r === l.region ? " selected" : "") + ">" + r + "</option>"; }).join("");
    }
    function showForm(locked) {
      S.$("#rest").innerHTML = lockedMsg + "<form id='f' class='stack'>" + fieldsHtml(locked) + "</form>";
      regions(); drawThumbs();
      S.$("#files").onchange = function (e) {
        var files = Array.prototype.slice.call(e.target.files, 0, 12 - photos.length);
        S.toast("Uploading " + files.length + " photo" + (files.length === 1 ? "" : "s") + "…");
        Promise.all(files.map(function (file) {
          return shrink(file).then(function (blob) {
            var path = S.me().id + "/" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7) + ".webp";
            return S.db.storage.from("car-photos").upload(path, blob, { contentType: "image/webp" }).then(function (r) { if (r.error) throw r.error; photos.push(path); });
          });
        })).then(function () { drawThumbs(); S.toast("Photos added."); }).catch(function (e2) { drawThumbs(); S.toast(S.friendly(e2), true); });
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
        }).then(function (id) { S.toast(go === "submit" ? "Submitted. Saaz is putting a garage in play." : "Draft saved."); S.go("#/my/cars/" + id); })
          .catch(function (e2) { err.textContent = S.friendly(e2); S.$$("button", e.target).forEach(function (b) { b.disabled = false; }); if (l.id) history.replaceState(null, "", "#/my/edit/" + l.id); });
      };
    }
    v.innerHTML = "<div class='narrow wide'><h1>" + (existing ? "Edit " + esc(l.ref) : saaz ? "New Saaz car" : "List a car") + "</h1>" +
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
        if (r.active_listing) { box.innerHTML = "<p class='err'>This car already has an active listing on Saaz.</p>"; S.$("#rest").innerHTML = ""; return; }
        if (r.found === "saaz_import") {
          var veh = r.vehicle; l = Object.assign(l, { make: veh.make, model: veh.model, year: veh.year, fuel: veh.fuel, gearbox: veh.gearbox, body: veh.body, engine: veh.engine, mileage: r.highest_km });
          lockedMsg = "<p class='box good'>Saaz import record found. Make, model, year, fuel, gearbox, body and engine are filled in and locked. Import mileage: " + S.km(veh.import_mileage) + ".</p>";
          box.innerHTML = ""; showForm(true);
        } else if (r.found === "earlier") {
          var v2 = r.vehicle; l = Object.assign(l, { make: v2.make, model: v2.model, year: v2.year, fuel: v2.fuel, gearbox: v2.gearbox, body: v2.body, engine: v2.engine });
          lockedMsg = "<p class='box'>Saaz has seen this car before. Its history carries on with this listing. Mileage can't be lower than " + S.km(r.highest_km) + ".</p>";
          box.innerHTML = ""; showForm(false);
        } else {
          var d = S.decode(vin); l = Object.assign(l, { make: d.make || "", model: d.model || "", year: d.year || "" });
          lockedMsg = "<p class='box'>New to Saaz. " + (d.make ? "Partial decode from the " + esc(d.how) + ": " + esc([d.make, d.model, d.year].filter(Boolean).join(" ")) + ". Check it." : "The " + esc(d.how) + " gave nothing. Fill in the details.") +
            " Importer unknown. This listing starts the car's Saaz record.</p>";
          box.innerHTML = ""; showForm(false);
        }
      }).catch(function (e2) { S.$("#look").innerHTML = "<p class='err'>" + esc(S.friendly(e2)) + "</p>"; });
    };
    if (preVin) S.$("#vf").requestSubmit();
  }
  S.route("/sell/new", function (v, m, q) {
    var saaz = q.get("saaz") === "1";
    if (saaz && !S.isAdmin()) { v.innerHTML = "<div class='empty'><b>Admins only</b></div>"; return; }
    sellForm(v, null, saaz, q.get("vin"));
  }, "user");
  S.route("/my/edit/([0-9a-f-]+)", function (v, m) {
    return S.q(S.db.from("listings").select("*, vehicles(vin)").eq("id", m[0])).then(function (rows) {
      var l = rows[0]; if (!l) throw new Error("Listing not found.");
      sellForm(v, l, l.saaz_owned, l.vehicles.vin);
    });
  }, "user");

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
    if (editable) actions.push("<a class='btn' href='#/my/edit/" + l.id + "'>Edit</a>", "<div id='scopebox'></div>", "<button class='btn dark' id='submit'>Submit for a Saaz inspection</button>");
    if (["awaiting_review", "review_booked"].indexOf(l.status) >= 0 && !l.saaz_owned) actions.push("<form id='addscope' class='stack'><div id='scopebox'></div><button class='btn small ghost dark'>Request these inspections</button></form>");
    if (l.status === "re_review_due") actions.push("<button class='btn dark' id='submit'>Submit for a new Saaz inspection</button>");
    if (["live", "re_review_due"].indexOf(l.status) >= 0) actions.push("<button class='btn ghost dark' id='reopen'>Change something other than the price</button>");
    if (["reserved", "sold", "withdrawn", "rejected"].indexOf(l.status) < 0) actions.push("<button class='btn ghost dark' id='withdraw'>Withdraw</button>");
    var priceForm = ["live", "draft", "changes_requested", "awaiting_review", "review_booked", "awaiting_approval"].indexOf(l.status) >= 0
      ? "<form id='pricef' class='inlineform'><label>Price (" + l.currency + ")<input name='price' type='number' value='" + l.price + "' required></label><button class='btn small'>Change price</button></form><p class='note'>A live car keeps its inspection when only the price changes.</p>" : "";
    var daily = (st.daily_14 || []).map(function (d) { return { label: S.day(d.day), short: String(new Date(d.day + "T00:00:00").getDate()), value: d.views }; });
    var model = st.model || {};
    v.innerHTML = "<p class='crumbs'><a href='" + (l.saaz_owned ? "#/admin/saaz" : "#/my/cars") + "'>" + (l.saaz_owned ? "Saaz cars" : "My cars") + "</a> / " + esc(l.ref) + "</p>" +
      "<div class='pagehead'><h1>" + esc(S.name(l)) + "</h1>" + S.chip(l.status) + "</div>" + progress(l.status) +
      "<p class='box'>" + esc(STATUS_TEXT[l.status] || "") + (l.line_empty ? " No garage is left in line: Saaz will find one and let you know." : "") + "</p>" +
      (l.admin_note ? "<p class='box warn'><b>Note from Saaz:</b> " + esc(l.admin_note) + "</p>" : "") +
      "<div class='row'>" + actions.join("") + "</div>" + priceForm +
      (open ? "<section><h2>" + (open.status === "agreed" ? "Your garage" : "Garage in play") + "</h2>" + convoHtml(open, msgs, true) +
        (open.status === "in_play" ? "<div class='row'><button class='btn' id='agree'" + (open.garage_first_message_at ? "" : " disabled") + ">Agree: book my inspection with this garage</button>" +
          "<button class='btn ghost dark' id='pass'>Pass to the next garage</button></div><div id='passbox'></div>" : "") + "</section>" : "") +
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
        if (side === "seller") acts.push("<button class='btn ghost dark' data-a='reject'>Reject</button>");
        if (side === "buyer") acts.push("<button class='btn ghost dark' data-a='withdraw'>Withdraw my offer</button>");
      }
      if (side === "admin") {
        if (deal.status === "negotiating") acts.push("<form class='inlineform' id='pf'><label>Propose a price to both (" + cur + ")<input name='amount' type='number' required></label><button class='btn small'>Propose</button></form>",
          "<form class='inlineform' id='mf'><label>Mark agreed: how did both confirm?<input name='note' required></label><button class='btn small'>Mark agreed</button></form>");
        if (deal.status === "agreed") acts.push("<button class='btn' data-a='complete'>Sale completed (handover confirmed)</button>");
        if (deal.status === "negotiating" || deal.status === "agreed") acts.push("<button class='btn ghost dark' data-a='cancel'>Cancel deal</button>");
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
