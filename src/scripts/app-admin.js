/* app-admin.js: Overview, Cars, Saaz cars, What's selling, Vehicles, Reviews, Garages, Users, Deals, Audit trail, Outbox, Settings. */
(function () {
  var S = window.Saaz, esc = S.esc;
  // Navigation grouped by the work being done (Zoho-style): a stable side menu on wide screens, a "Go to" menu on phones.
  var GROUPS = [
    ["Overview", [["", "Overview"]]],
    ["Vehicles and listings", [["cars", "Cars"], ["saaz", "Saaz cars"], ["vehicles", "Vehicle records"], ["selling", "What's selling"]]],
    ["Inspections and garage line", [["conversations", "Garage line"], ["reviews", "Car inspection reports"]]],
    ["Garages and partners", [["garages", "Garages"]]],
    ["Customers and deals", [["users", "Users"], ["deals", "Deals"]]],
    ["Communications", [["outbox", "Outbox"]]],
    ["System", [["audit", "All activity"], ["team", "Saaz team"], ["settings", "Settings"]]]
  ];
  var FULL_ONLY = ["team", "settings"];  // Staff don't get these (the database refuses them too)
  function tabs(at) {
    var opts = "", side = "";
    var full = !!(S.state.roles || {}).full_admin;
    GROUPS.map(function (g) { return [g[0], g[1].filter(function (t) { return full || FULL_ONLY.indexOf(t[0]) < 0; })]; }).filter(function (g) { return g[1].length; }).forEach(function (g) {
      side += "<div class='navgroup'><b>" + g[0] + "</b>" + g[1].map(function (t) { return "<a href='#/admin" + (t[0] ? "/" + t[0] : "") + "'" + (t[0] === at ? " aria-current='page'" : "") + ">" + t[1] + "</a>"; }).join("") + "</div>";
      opts += "<optgroup label='" + g[0] + "'>" + g[1].map(function (t) { return "<option value='#/admin" + (t[0] ? "/" + t[0] : "") + "'" + (t[0] === at ? " selected" : "") + ">" + t[1] + "</option>"; }).join("") + "</optgroup>";
    });
    return { side: "<nav class='adminside' aria-label='Admin'>" + side + "</nav>", phone: "<label class='adminjump'>Go to<select onchange='location.hash=this.value'>" + opts + "</select></label>" };
  }
  function page(v, at, html) { var t = tabs(at); v.innerHTML = "<h1 class='sr'>Admin</h1><div class='adminwrap'>" + t.side + "<div class='adminmain'>" + t.phone + html + "</div></div>"; }
  function table(head, rows) {
    return "<div class='tablewrap'><table class='tbl'><thead><tr>" + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr></thead><tbody>" +
      (rows.length ? rows.join("") : "<tr><td colspan='" + head.length + "' class='note'>Nothing here.</td></tr>") + "</tbody></table></div>";
  }
  var A = function (p, h, n) { S.route("/admin" + p, h, "admin"); };

  // ---------- Admin entry: account menu > Admin panel (admin accounts only) ----------
  // Every time: password again, then the authenticator. Entering the password starts a new session; the code lifts it to aal2.
  // The database only treats it as admin if that session used the authenticator pinned to the account (SQL Editor, part 10)
  // and the password and code were both entered in the last 12 hours (part 12). This page decides nothing on its own.
  var MAX_TRIES = 5;
  S.route("/admin/verify", function (v) {
    var r = S.state.roles || {}, email = S.me().email, tries = 0;
    if (!S.signedIn() || !r.admin_account) { v.innerHTML = "<div class='empty'><b>Page not found</b><span><a href='#/browse'>Browse cars</a></span></div>"; return; }
    var shell = function (h) { v.innerHTML = "<div class='narrow staff'><p class='crumbs'><a href='" + S.home() + "'>Back</a></p><h1>Admin panel</h1>" + h + "</div>"; };
    var failed = function (stage, msg, el) {
      tries++; S.rpc("admin_verify_failed", { p_stage: stage }).catch(function () {});
      if (tries >= MAX_TRIES) return S.signOut("Too many failed attempts. You were signed out.");
      el.textContent = msg + " " + (MAX_TRIES - tries) + " tries left.";
    };
    var enter = function () {
      return S.loadRoles().then(function (rr) {
        if (!rr || !rr.admin) {
          if (S._staffEnrolled) { S._staffEnrolled = false; return shell("<div class='box good'><b>Authenticator added</b><p>It works. It has to be pinned to your account before it opens Admin (README, Admin sign-in). Then choose Admin panel again.</p></div>"); }
          return shell("<p class='err' role='alert'>Admin access wasn't granted for this session. Choose Admin panel again, or check the authenticator is pinned (README, Admin sign-in).</p>");
        }
        return S.rpc("admin_signed_in").catch(function () {}).then(function () { S.mode("admin"); S.toast("Signed in to Admin."); S.go("#/admin"); });
      });
    };
    var codeForm = function (factorId, intro) {
      shell("<p class='lead'>Step 2 of 2: the 6-digit code from your authenticator app.</p>" + intro + "<form id='cf' class='stack'><label>Code<input name='code' inputmode='numeric' autocomplete='one-time-code' pattern='[0-9]{6}' maxlength='6' required autofocus></label>" +
        "<p class='err' id='cerr' role='alert'></p><button class='btn wide'>Open Admin</button></form>");
      S.$("#cf").onsubmit = function (e) {
        e.preventDefault(); var b = e.target.querySelector("button"), code = S.form(e.target).code, el = S.$("#cerr"); b.disabled = true; el.textContent = "";
        S.db.auth.mfa.challenge({ factorId: factorId }).then(function (c) {
          if (c.error) throw c.error;
          return S.db.auth.mfa.verify({ factorId: factorId, challengeId: c.data.id, code: code });
        }).then(function (x) { if (x.error) throw x.error; return enter(); })
          .catch(function (e2) { b.disabled = false; if (/invalid|code|verification/i.test(e2.message || "")) failed("code", "Wrong code. Codes change every 30 seconds.", el); else el.textContent = S.friendly(e2); });
      };
    };
    var enroll = function (all) {
      return Promise.all(all.filter(function (f) { return f.status !== "verified"; }).map(function (f) { return S.db.auth.mfa.unenroll({ factorId: f.id }); })).then(function () {
        return S.db.auth.mfa.enroll({ factorType: "totp", friendlyName: "Saaz admin " + new Date().toISOString().slice(0, 16), issuer: "Saaz" });
      }).then(function (x) {
        if (x.error) throw x.error;
        S._staffEnrolled = true;
        codeForm(x.data.id, "<p>First time: add Saaz to an authenticator app (Google Authenticator, Microsoft Authenticator or similar). Scan the code, or type the key.</p>" +
          "<img class='qr' src='" + esc(x.data.totp.qr_code) + "' width='200' height='200' alt='QR code for your authenticator app'>" +
          "<p class='key'>Key: <code>" + esc(x.data.totp.secret) + "</code></p><p class='note'>Keep this key off shared devices. Anyone with it can make codes.</p>");
      });
    };
    var step2 = function () {
      return S.db.auth.mfa.listFactors().then(function (f) {
        if (f.error) throw f.error;
        if (f.data.totp.length) return codeForm(f.data.totp[0].id, "");
        return enroll(f.data.all || []);
      }).catch(function (e) { shell("<p class='err' role='alert'>" + esc(S.friendly(e)) + "</p>"); });
    };
    shell("<p class='lead'>Step 1 of 2: enter your password again.</p><form id='pf' class='stack'><label>Email<input name='email' type='email' value='" + esc(email) + "' readonly autocomplete='username'></label>" +
      "<label>Password<input name='password' type='password' autocomplete='current-password' required autofocus></label><p class='err' id='perr' role='alert'></p><button class='btn wide'>Continue</button></form>");
    S.$("#pf").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), b = e.target.querySelector("button"), el = S.$("#perr"); b.disabled = true; el.textContent = "";
      S.db.auth.signInWithPassword({ email: email, password: f.password }).then(function (x) {
        if (x.error) throw x.error; return step2();
      }).catch(function (e2) { b.disabled = false; if (/invalid login|credentials/i.test(e2.message || "")) failed("password", "Wrong password.", el); else el.textContent = S.friendly(e2); });
    };
  }); // no "user" flag: signed-out visitors get the same "Page not found" as anyone else

  // Audit trail, shown on the page of the thing it is about. Each row links to what it touched.
  function aboutLink(a) {
    var id = String(a.entity_id);
    var href = { listing: "#/admin/car/" + id, garage: "#/admin/garage/" + id, account: "#/admin/user/" + id, deal: "#/deals/" + id }[a.entity];
    var label = { listing: "Car", vehicle: "Vehicle", review: "Inspection report", deal: "Deal", garage: "Garage", member: "Garage team member", account: "Account",
      setting: "Setting", conversation: "Garage line" }[a.entity] || a.entity;
    return href ? "<a href='" + href + "'>" + esc(label) + "</a>" : esc(label) + (a.entity === "setting" ? " <small>" + esc(id) + "</small>" : "");
  }
  function who(a, names) {
    var n = names[a.actor_id];
    return a.actor_id ? "<a href='#/admin/user/" + a.actor_id + "'>" + esc(n || S.label(a.actor_role)) + "</a> <small>" + esc(S.label(a.actor_role)) + "</small>" : esc(S.label(a.actor_role));
  }
  S.historyTable = function (rows, title, showAbout) {
    var ids = rows.map(function (a) { return a.actor_id; }).filter(Boolean);
    return (ids.length ? S.q(S.db.from("profiles").select("id,name").in("id", ids.filter(function (x, i) { return ids.indexOf(x) === i; }))) : Promise.resolve([])).then(function (ps) {
      var names = {}; ps.forEach(function (p) { names[p.id] = p.name; });
      return "<section><h2>" + title + "</h2>" + table(["When", "Who"].concat(showAbout ? ["About"] : []).concat(["What happened", "Detail"]), rows.map(function (a) {
        return "<tr><td>" + S.when(a.at) + "</td><td>" + who(a, names) + "</td>" + (showAbout ? "<td>" + aboutLink(a) + "</td>" : "") + "<td>" + esc(a.action) + "</td>" +
          "<td>" + (a.detail && Object.keys(a.detail).length ? "<details><summary>Show</summary><pre>" + esc(JSON.stringify(a.detail, null, 1)) + "</pre></details>" : "") + "</td></tr>";
      })) + "<p class='note'>Entries can't be edited or deleted.</p></section>";
    });
  };

  A("", function (v) {
    return Promise.all([
      S.q(S.db.from("listings").select("id,ref,make,model,year,status,line_empty,updated_at").in("status", ["awaiting_approval", "awaiting_review"])),
      S.q(S.db.from("garages").select("id,name,status,created_at").in("status", ["applied"])),
      S.q(S.db.from("deals").select("id,amount,status,listing_id,updated_at").eq("status", "agreed"))
    ]).then(function (r) {
      var approve = r[0].filter(function (l) { return l.status === "awaiting_approval"; }), empty = r[0].filter(function (l) { return l.line_empty; });
      function q(title, list, href, label) {
        return "<section><h2>" + title + " <span class='count'>" + list.length + "</span></h2>" + (list.length ? "<ul class='list'>" + list.map(function (x) { return "<li><a href='" + href(x) + "'>" + esc(label(x)) + "</a></li>"; }).join("") + "</ul>" : "<p class='note'>Nothing waiting.</p>") + "</section>";
      }
      page(v, "", q("Cars waiting for approval", approve, function (l) { return "#/admin/car/" + l.id; }, function (l) { return l.ref + " · " + l.year + " " + l.make + " " + l.model; }) +
        q("Cars with no garage left in line", empty, function (l) { return "#/admin/car/" + l.id; }, function (l) { return l.ref + " · " + l.year + " " + l.make + " " + l.model; }) +
        q("Garage applications", r[1], function (g) { return "#/admin/garage/" + g.id; }, function (g) { return g.name + " · applied " + S.day(g.created_at); }) +
        q("Deals agreed, handover pending", r[2], function (d) { return "#/deals/" + d.id; }, function (d) { return "Deal " + d.id.slice(0, 8) + " · " + Number(d.amount).toLocaleString("en-US"); }));
    });
  });

  A("/cars", function (v, m, q) {
    var st = q.get("status") || "";
    var query = S.db.from("listings").select("id,ref,make,model,year,status,price,currency,country,region,saaz_owned,line_empty,updated_at").order("updated_at", { ascending: false }).limit(300);
    if (st) query = query.eq("status", st);
    return S.q(query).then(function (rows) {
      page(v, "cars", "<form class='filters' id='fs'><select name='status'><option value=''>Every status</option>" + ["draft", "awaiting_review", "review_booked", "awaiting_approval", "changes_requested", "live", "reserved", "sold", "rejected", "withdrawn", "re_review_due"]
        .map(function (s) { return "<option value='" + s + "'" + (s === st ? " selected" : "") + ">" + S.label(s) + "</option>"; }).join("") + "</select><button class='btn small'>Show</button></form>" +
        table(["Ref", "Car", "Status", "Price", "Where", "Updated"], rows.map(function (l) {
          return "<tr><td><a href='#/admin/car/" + l.id + "'>" + esc(l.ref) + "</a></td><td>" + esc(S.name(l)) + (l.saaz_owned ? " <span class='src'>Saaz</span>" : "") + "</td><td>" + S.chip(l.status) + (l.line_empty ? " <span class='chip s-flag'>Line empty</span>" : "") + "</td><td>" + S.money(l.currency, l.price) + "</td><td>" + esc(l.region) + "</td><td>" + S.day(l.updated_at) + "</td></tr>";
        })));
      S.$("#fs").onsubmit = function (e) { e.preventDefault(); S.go("#/admin/cars?status=" + S.form(e.target).status); };
    });
  });

  A("/car/([0-9a-f-]+)", function (v, m) {
    var id = m[0];
    return Promise.all([
      S.q(S.db.from("listings").select("*, vehicles(vin,source)").eq("id", id)),
      S.q(S.db.from("conversations").select("id,status,opened_at,closed_at,assigned_by_admin,round,garage_first_message_at, garages(name)").eq("listing_id", id).order("opened_at")),
      S.rpc("listing_stats", { p_listing: id }), S.rpc("listing_history", { p_listing: id }),
      S.q(S.db.from("garages").select("id,name,region,country").eq("status", "certified")),
      S.q(S.db.from("reviews").select("id,doc_no,status,verdict,score,verify_code,odometer_flag,garage_name,member_name,issued_at").eq("listing_id", id).neq("status", "draft").order("issued_at"))
    ]).then(function (r) {
      var l = r[0][0], convs = r[1], st = r[2] || {}, hist = r[3] || [], garages = r[4].filter(function (g) { return g.country === l.country; }), reviews = r[5];
      var cur = reviews.filter(function (x) { return x.id === l.current_review_id; })[0];
      var st0 = l.status, forSeller = [];
      if (["live", "draft", "changes_requested", "awaiting_review", "review_booked", "awaiting_approval"].indexOf(st0) >= 0)
        forSeller.push({ kind: "price", target: l.id, label: "Change the price", fields: "<label>New asking price (" + l.currency + ")<input name='price' type='number' required value='" + l.price + "'></label>", p: function (f) { return { price: +f.price }; } });
      forSeller.push({ kind: "offer_rules", target: l.id, label: "Save offer rules", p: function (f) { return { rules: { min_pct: f.min_pct, min_amount: f.min_amount, no_trade_in: !!f.no_trade_in, on_counters: !!f.on_counters, auto_reject: !!f.auto_reject } }; },
        fields: "<label>Turn down below % of asking<input name='min_pct' type='number' min='0' max='100' value='" + (l.rule_min_pct == null ? "" : l.rule_min_pct) + "'></label>" +
          "<label>Or below (" + l.currency + ")<input name='min_amount' type='number' value='" + (l.rule_min_amount == null ? "" : l.rule_min_amount) + "'></label>" +
          "<label class='inline'><input type='checkbox' name='no_trade_in' value='1'" + (l.rule_no_trade_in ? " checked" : "") + "> No trade-ins</label>" +
          "<label class='inline'><input type='checkbox' name='on_counters' value='1'" + (l.rule_on_counters ? " checked" : "") + "> Apply to counters</label>" +
          "<label class='inline'><input type='checkbox' name='auto_reject' value='1'" + (l.auto_reject ? " checked" : "") + "> Decline automatically</label>" });
      if (["draft", "changes_requested", "re_review_due"].indexOf(st0) >= 0) forSeller.push({ kind: "submit", target: l.id, label: "Send for a Saaz inspection" });
      if (["live", "re_review_due"].indexOf(st0) >= 0) forSeller.push({ kind: "reopen", target: l.id, label: "Take off sale to edit", confirm: true });
      if (["reserved", "sold", "withdrawn"].indexOf(st0) < 0) forSeller.push({ kind: "withdraw", target: l.id, label: "Withdraw the car", confirm: true });
      convs.filter(function (c) { return c.status === "in_play"; }).forEach(function (c) {
        if (c.garage_first_message_at) forSeller.push({ kind: "garage_agree", target: c.id, label: "Agree to " + c.garages.name + " for the inspection" });
        forSeller.push({ kind: "garage_pass", target: c.id, label: "Pass on " + c.garages.name, confirm: true });
      });
      page(v, "cars", "<p class='crumbs'><a href='#/admin/cars'>Cars</a> / " + esc(l.ref) + "</p><div class='pagehead'><h2>" + esc(S.name(l)) + "</h2>" + S.chip(l.status) + "</div>" +
        "<p class='lead'>" + S.money(l.currency, l.price) + " · " + S.km(l.mileage) + " · " + esc(l.plate) + " · VIN " + esc(l.vehicles.vin) + " · " + esc(l.region) + (l.saaz_owned ? " · Saaz-owned" : "") + "</p>" +
        "<div class='thumbs'>" + (l.photos || []).map(function (p) { return "<figure><img src='" + esc(S.photo(p)) + "' alt=''></figure>"; }).join("") + "</div><p class='pre'>" + esc(l.description) + "</p>" +
        (l.logbook_name_matches ? "<p class='note'>Seller says the logbook is in their name.</p>" : l.owner_authorised ? "<p class='note'>Seller says the owner authorised the sale.</p>" : "") +
        (cur ? "<section><h2>Current Saaz inspection</h2><div class='insp-card'><div class='insp-head'>" + S.chip(cur.verdict) + "<span>" + cur.score + "/100 · " + esc(cur.doc_no) + "</span></div>" +
          "<p>" + esc(cur.member_name) + ", " + esc(cur.garage_name) + ", " + S.when(cur.issued_at) + "</p>" + (cur.odometer_flag ? "<p class='err'>Odometer flag: " + esc(cur.odometer_flag) + "</p>" : "") +
          "<a href='#/report/" + esc(cur.verify_code) + "'>Open the report</a></div></section>" : "") +
        "<section><h2>Decision</h2><form id='dec' class='stack'><label>Note to the seller (needed for changes, reject and unlist)<textarea name='note' rows='2'></textarea></label>" +
        "<label class='inline'><input type='checkbox' name='new_review' value='1'> Request changes needs a new Saaz inspection</label><div class='row'>" +
        (l.status === "awaiting_approval" ? "<button class='btn' value='approve'" + (cur && cur.verdict === "fail" ? " disabled title='A safety Fail cannot be approved'" : "") + ">Approve and go live</button><button class='btn ghost dark' value='changes'>Request changes</button><button class='btn ghost dark' value='reject'>Reject</button>" : "") +
        (["live", "re_review_due"].indexOf(l.status) >= 0 ? "<button class='btn ghost dark' value='unlist'>Unlist</button>" : "") + "</div></form>" +
        (cur && cur.verdict === "fail" ? "<p class='note'>A safety Fail can't be approved.</p>" : "") + "</section>" +
        (l.saaz_owned ? "" : S.actFor("afs", "Act for the seller", "Do what the seller can do, for them: the same rules apply. The seller is told each time, with your reason.", forSeller)) +
        "<section><h2>Garage line</h2>" + table(["Garage", "Status", "Round", "Opened", "Closed"], convs.map(function (c) {
          return "<tr><td>" + esc(c.garages.name) + (c.assigned_by_admin ? " <small>assigned</small>" : "") + "</td><td>" + S.chip(c.status) + "</td><td>" + c.round + "</td><td>" + S.when(c.opened_at) + "</td><td>" + S.when(c.closed_at) + "</td></tr>";
        })) + "<p class='note'>Saaz doesn't read these conversations.</p>" +
        (["awaiting_review", "review_booked"].indexOf(l.status) >= 0 ? "<form id='asg' class='inlineform'><label>Assign a garage directly<select name='g'>" + garages.map(function (g) { return "<option value='" + g.id + "'>" + esc(g.name + " · " + g.region) + "</option>"; }).join("") + "</select></label><button class='btn small'>Assign</button></form>" +
          "<button class='btn small ghost dark' id='restart'>Restart the line</button>" : "") + "</section>" +
        (cur ? "<section><h2>Saaz view of this report</h2><p class='note'>Saaz never changes a report. Support it or object to it, with a reason: the garage and the seller see it, the report shows it, and the garage can reply. An objection keeps the car off sale until Saaz supports the report or asks for a new inspection.</p>" +
          "<div id='ops'><p class='loading'>Loading…</p></div><form id='opf' class='stack'><label>Reason<textarea name='reason' rows='2' minlength='10' required></textarea></label><div class='row'>" +
          "<button class='btn small ghost dark' value='support'>Support the report</button><button class='btn small ghost dark' value='object'>Object to the report</button></div></form></section>" : "") +
        "<section><h2>Demand</h2><div class='stats'>" + [["Views, 7 days", st.views_7d], ["Views in total", st.views_total], ["Saves", st.saves], ["Offers", st.offers], ["Auto-rejected", st.auto_rejected]]
          .map(function (x) { return "<div><b>" + (x[1] || 0) + "</b><span>" + x[0] + "</span></div>"; }).join("") + "</div></section>" +
        "<section><h2>Every inspection of this car</h2><div id='insps'><p class='loading'>Loading…</p></div></section>" +
        "<section><h2>History of this car</h2><ul class='timeline'>" + hist.map(function (h) { return "<li><small>" + S.when(h.at) + "</small> " + esc(h.who) + ": " + esc(h.action) + "</li>"; }).join("") + "</ul></section>");
      S.$("#dec").onsubmit = function (e) {
        e.preventDefault(); var f = S.form(e.target), b = e.submitter;
        S.act(b, function () { return S.rpc("admin_decide_listing", { p_listing: id, p_decision: b.value, p_note: f.note, p_new_review: !!f.new_review }); }, "Saved. The seller is told.");
      };
      S.wireActFor("afs", forSeller);
      var asg = S.$("#asg"); if (asg) asg.onsubmit = function (e) { e.preventDefault(); S.act(asg.querySelector("button"), function () { return S.rpc("admin_assign_garage", { p_listing: id, p_garage: S.form(asg).g }); }, "Garage assigned."); };
      var rs = S.$("#restart"); if (rs) rs.onclick = function () { S.confirmBtn(rs, function () { S.act(rs, function () { return S.rpc("admin_restart_line", { p_listing: id }); }, "Line restarted."); }); };
      S.loadInspections("insps", l.id);
      if (cur) { S.showOpinions("ops", cur.verify_code); var opf = S.$("#opf"); opf.onsubmit = function (e) { e.preventDefault(); var b = e.submitter, why = S.form(opf).reason;
        S.act(b, function () { return S.rpc("review_opinion", { p_review: cur.id, p_stance: b.value, p_reason: why }); }, b.value === "object" ? "Objection recorded. The garage and the seller are told." : "Support recorded."); }; }
    });
  });

  A("/saaz", function (v) {
    return Promise.all([S.rpc("my_listings", { p_saaz: true }), S.q(S.db.from("vehicles").select("*").eq("saaz_owned", true).order("created_at", { ascending: false })),
      S.q(S.db.from("listings").select("vehicle_id").eq("saaz_owned", true).not("status", "in", "(sold,rejected,withdrawn)"))]).then(function (r) {
      var listed = {}; r[2].forEach(function (x) { listed[x.vehicle_id] = 1; });
      var unlisted = r[1].filter(function (veh) { return !listed[veh.id]; });
      page(v, "saaz", "<div class='pagehead row'><h2>Saaz cars</h2><a class='btn' href='#/sell/new?saaz=1'>New Saaz car</a></div>" + S.carRows(r[0], true) +
        "<section><h2>Saaz imports not listed yet</h2>" + table(["VIN", "Car", "Import mileage", ""], unlisted.map(function (veh) {
          return "<tr><td class='mono'>" + esc(veh.vin) + "</td><td>" + esc(veh.year + " " + veh.make + " " + veh.model) + "</td><td>" + S.km(veh.import_mileage) + "</td><td><a href='#/sell/new?saaz=1&vin=" + encodeURIComponent(veh.vin) + "'>List it</a></td></tr>";
        })) + "</section><section><h2>Record a Saaz import</h2><form id='imp' class='stack'><div class='grid2'>" +
        [["vin", "VIN or chassis number"], ["make", "Make"], ["model", "Model"], ["year", "Year", "number"], ["fuel", "Fuel"], ["gearbox", "Gearbox"], ["body", "Body"], ["engine", "Engine"], ["import_mileage", "Import mileage (km)", "number"]]
          .map(function (x) { return "<label>" + x[1] + "<input name='" + x[0] + "' type='" + (x[2] || "text") + "' required></label>"; }).join("") +
        "</div><label class='inline'><input type='checkbox' name='saaz_owned' value='1' checked> Owned by Saaz (uncheck for an import already sold to a person)</label><button class='btn'>Record import</button></form></section>");
      S.$("#imp").onsubmit = function (e) { e.preventDefault(); var f = S.form(e.target); f.saaz_owned = !!f.saaz_owned; S.act(e.target.querySelector("button"), function () { return S.rpc("admin_add_import", { p: f }); }, "Import recorded."); };
    });
  });

  A("/selling", function (v) {
    return S.rpc("whats_selling", { p_country: "UG" }).then(function (rows) {
      page(v, "selling", "<h2>What's selling in Uganda</h2>" + S.sellingTable(rows));
    });
  });

  A("/vehicles", function (v) {
    return Promise.all([S.q(S.db.from("vehicles").select("*").order("created_at", { ascending: false }).limit(300)), S.q(S.db.from("odometer_readings").select("vehicle_id,km,source,flagged,recorded_at").order("recorded_at"))]).then(function (r) {
      var reads = {}; r[1].forEach(function (o) { (reads[o.vehicle_id] = reads[o.vehicle_id] || []).push(o); });
      page(v, "vehicles", table(["VIN", "Car", "Provenance", "First record", "Odometer readings"], r[0].map(function (veh) {
        return "<tr><td class='mono'>" + esc(veh.vin) + "</td><td>" + esc([veh.year, veh.make, veh.model].filter(Boolean).join(" ")) + "</td><td>" + (veh.source === "saaz_import" ? "Saaz import" + (veh.saaz_owned ? ", Saaz-owned" : "") : "Local") + "</td><td>" + S.day(veh.first_record_date) + "</td><td>" +
          (reads[veh.id] || []).map(function (o) { return S.km(o.km) + " (" + S.label(o.source) + ", " + S.day(o.recorded_at) + ")" + (o.flagged ? " <b class='err'>flag</b>" : ""); }).join("<br>") + "</td></tr>";
      })));
    });
  });

  A("/reviews", function (v) {
    return S.q(S.db.from("reviews").select("id,doc_no,status,verdict,score,verify_code,garage_name,member_name,issued_at,odometer_flag, listings!reviews_listing_id_fkey(ref)").neq("status", "draft").order("issued_at", { ascending: false }).limit(300)).then(function (rows) {
      page(v, "reviews", "<p class='lead'>A Saaz inspection is always a report on one car, made by a certified garage. Saaz doesn't rate sellers or garages yet.</p>" + table(["Document", "Car", "Status", "Verdict", "Garage", "Member", "Issued"], rows.map(function (x) {
        return "<tr><td><a href='#/report/" + esc(x.verify_code) + "'>" + esc(x.doc_no) + "</a></td><td>" + esc(x.listings.ref) + "</td><td>" + S.chip(x.status) + "</td><td>" + esc(S.label(x.verdict)) + " " + x.score + (x.odometer_flag ? " <b class='err'>odometer</b>" : "") + "</td><td>" + esc(x.garage_name) + "</td><td>" + esc(x.member_name) + "</td><td>" + S.day(x.issued_at) + "</td></tr>";
      })) + "<p class='note'>To void an inspection report, open its car from Cars.</p>");
    });
  });

  A("/garages", function (v) {
    return S.q(S.db.from("garages").select("*").order("created_at", { ascending: false })).then(function (rows) {
      page(v, "garages", "<div class='pagehead row'><h2>Garages</h2><a class='btn' href='#/admin/garage-new'>Add a garage directly</a></div>" +
        table(["Garage", "Status", "Where", "Since"], rows.map(function (g) {
          return "<tr><td><a href='#/admin/garage/" + g.id + "'>" + esc(g.name) + "</a><small> " + esc(S.label(g.business_type)) + "</small></td><td>" + S.chip(g.status) + "</td><td>" + esc(g.region + ", " + S.COUNTRY[g.country]) + "</td><td>" + S.day(g.certified_at || g.created_at) + "</td></tr>";
        })));
    });
  });
  A("/garage/([0-9a-f-]+)", function (v, m) {
    var id = m[0];
    return Promise.all([S.q(S.db.from("garages").select("*").eq("id", id)), S.rpc("garage_team", { p_garage: id }),
      S.q(S.db.from("reviews").select("doc_no,verdict,score,status,verify_code,issued_at").eq("garage_id", id).neq("status", "draft").order("issued_at", { ascending: false }).limit(50))]).then(function (r) {
      var g = r[0][0], acts = [];
      if (g.status === "applied" || g.status === "more_info") acts.push("<button class='btn' value='approve'>Approve</button><button class='btn ghost dark' value='more_info'>Ask for more information</button><button class='btn ghost dark' value='rejected'>Reject</button>");
      if (g.status === "certified") acts.push("<button class='btn ghost dark' value='suspended'>Suspend</button>");
      if (g.status === "suspended") acts.push("<button class='btn' value='reinstate'>Reinstate</button>");
      page(v, "garages", "<p class='crumbs'><a href='#/admin/garages'>Garages</a> / " + esc(g.name) + "</p><div class='pagehead'><h2>" + esc(g.name) + "</h2>" + S.chip(g.status) + "</div>" +
        "<dl class='specs'>" + [["Type", S.label(g.business_type)], ["Where", g.region + ", " + S.COUNTRY[g.country]], ["Address", g.address], ["Phone", g.phone], ["Registration or licence", g.registration_no], ["Years", g.years], ["Specialties", (g.specialties || []).join(", ")], ["Honest-inspections declaration", g.honest_declaration ? "Ticked" : "No"], ["Note", g.status_note]]
          .filter(function (x) { return x[1] != null && x[1] !== ""; }).map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd></div>"; }).join("") + "</dl>" +
        (acts.length ? "<form id='gd' class='stack'><label>Note (needed for more information, reject and suspend)<textarea name='note' rows='2'></textarea></label><div class='row'>" + acts.join("") + "</div></form>" : "") +
        "<section><h2>Team</h2>" + table(["Name", "Email", "Role", "Status", ""], r[1].map(function (t) {
          var info = S.inviteInfo(t);
          return "<tr><td>" + esc(t.name) + "</td><td>" + esc(t.email) + "</td><td>" + esc(S.label(t.role)) + "</td><td>" + S.inviteStage(t) + (info ? "<br><small>" + info + "</small>" : "") + "</td><td>" + S.teamActions(t, true) + "</td></tr>";
        })) + "</section><section><h2>Car inspection reports this garage issued</h2>" + table(["Document", "Verdict", "Status", "Issued"], r[2].map(function (x) {
          return "<tr><td><a href='#/report/" + esc(x.verify_code) + "'>" + esc(x.doc_no) + "</a></td><td>" + esc(S.label(x.verdict)) + " " + x.score + "</td><td>" + S.chip(x.status) + "</td><td>" + S.day(x.issued_at) + "</td></tr>";
        })) + "</section><div id='ghist'></div>");
      var memberIds = r[1].map(function (t) { return t.id; }).concat(r[1].map(function (t) { return t.user_id; })).filter(Boolean);
      S.q(S.db.from("audit_log").select("*").or("entity_id.eq." + id + ",detail->>garage.eq." + id + (memberIds.length ? ",entity_id.in.(" + memberIds.join(",") + ")" : "")).order("at", { ascending: false }).limit(200))
        .then(function (rows) { return S.historyTable(rows, "History of this garage and its team", false); }).then(function (h) { S.$("#ghist").innerHTML = h; });
      S.wireTeam(v);
      var gd = S.$("#gd"); if (gd) gd.onsubmit = function (e) { e.preventDefault(); var b = e.submitter, f = S.form(gd); S.act(b, function () { return S.rpc("admin_decide_garage", { p_garage: id, p_decision: b.value, p_note: f.note }); }, "Saved. The owner is told."); };
    });
  });
  A("/garage-new", function (v) {
    page(v, "garages", "<h2>Add a certified garage directly</h2><form id='f' class='stack'>" + S.garageFields() +
      "<h3>Owner</h3><div class='grid2'><label>Name<input name='o_name' required></label><label>Email<input name='o_email' type='email' required></label><label>Mobile<input name='o_mobile' type='tel'></label></div>" +
      "<label>Why are you adding this garage directly, without an application?<input name='reason' required placeholder='For example: visited the garage on 17 Oct and checked its licence'></label><p class='note'>Saved in the garage's history so the team can see why it skipped the application.</p><button class='btn'>Add garage</button><p class='note'>If the owner has no Saaz account, they become Owner when they create one with this email.</p></form>");
    S.wireRegions();
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var form = e.target, f = S.form(form), p = S.garagePayload(form);
      ["o_name", "o_email", "o_mobile", "reason"].forEach(function (k) { delete p[k]; });
      S.act(form.querySelector("button"), function () { return S.rpc("admin_add_garage", { p: p, p_owner_email: f.o_email, p_owner_name: f.o_name, p_owner_mobile: f.o_mobile, p_reason: f.reason }); }, "Garage added.")
        .then(function (gid) {
          if (!gid) return;
          S.go("#/admin/garage/" + gid);
          S.sendInvite(f.o_email).then(function (m) { S.toast(m); }).catch(function (e) { if (!/No waiting invite/.test(e.message)) S.toast(S.friendly(e), true); });
        });
    };
  });

  A("/users", function (v) {
    return Promise.all([S.q(S.db.from("profiles").select("*").order("created_at", { ascending: false }).limit(500)), S.q(S.db.from("admins").select("user_id"))]).then(function (r) {
      var admins = {}; r[1].forEach(function (a) { admins[a.user_id] = 1; });
      page(v, "users", table(["Name", "Email", "Country", "Mobile", "Trusted seller", "Phone verified", "Suspended"], r[0].map(function (p) {
        function t(field, on) { return "<td><label class='switch'><input type='checkbox' data-u='" + p.id + "' data-f='" + field + "'" + (on ? " checked" : "") + (p.id === S.me().id ? " disabled" : "") + "><span>" + (on ? "Yes" : "No") + "</span></label></td>"; }
        return "<tr><td><a href='#/admin/user/" + p.id + "'>" + esc(p.name || "(no name)") + "</a></td><td>" + esc(p.email) + "</td><td>" + esc(p.country || "") + "</td><td>" + esc(p.mobile || "") + "</td>" + t("trusted", p.trusted) + t("phone_verified", p.phone_verified) + t("suspended", p.suspended) + "</tr>";
      })) + "<p class='note'>Suspending a seller withdraws their cars (admins only). You can't change your own access. Saaz team members are added on the <a href='#/admin/team'>Saaz team</a> page.</p>");
      S.$$("[data-f]").forEach(function (c) { c.onchange = function () { S.act(c, function () { return S.rpc("admin_set_user", { p_user: c.dataset.u, p_field: c.dataset.f, p_value: c.checked }); }, "Saved."); }; });
    });
  });

  A("/deals", function (v) {
    return S.q(S.db.from("deals").select("*, listings(ref,make,model,year,currency)").order("updated_at", { ascending: false }).limit(300)).then(function (rows) {
      page(v, "deals", table(["Car", "Figure", "Status", "Updated"], rows.map(function (d) {
        return "<tr><td><a href='#/deals/" + d.id + "'>" + esc(d.listings.ref + " · " + d.listings.year + " " + d.listings.make + " " + d.listings.model) + "</a></td><td>" + S.money(d.listings.currency, d.amount) + (d.trade_in ? " + trade-in" : "") + "</td><td>" + S.chip(d.status) + "</td><td>" + S.when(d.updated_at) + "</td></tr>";
      })) + "<p class='note'>No money moves through Saaz.</p>");
    });
  });

  A("/conversations", function (v) {
    return S.rpc("admin_conversation_counts").then(function (rows) {
      page(v, "conversations", "<p class='note'>Counts only. Saaz doesn't read garage conversations, except on Saaz-owned cars.</p>" +
        table(["Car", "Garage", "Status", "Messages", "Opened"], rows.map(function (c) { return "<tr><td>" + esc(c.listing_ref) + "</td><td>" + esc(c.garage) + "</td><td>" + S.chip(c.status) + "</td><td>" + c.messages + "</td><td>" + S.when(c.opened_at) + "</td></tr>"; })));
    });
  });

  var FILTERS = [["", "Everything"], ["listing", "Listings"], ["vehicle", "Vehicles"], ["review", "Inspections"], ["deal", "Deals"], ["garage", "Garages and teams"], ["seller", "By sellers"], ["buyer", "By buyers"], ["account", "Accounts"], ["admin", "By admins"], ["system", "System"]];
  A("/audit", function (v, m, q) {
    var f = q.get("f") || "", query = S.db.from("audit_log").select("*").order("at", { ascending: false }).limit(300);
    if (["seller", "buyer", "admin", "system"].indexOf(f) >= 0) query = query.eq("actor_role", f);
    else if (f === "garage") query = query.in("entity", ["garage", "member"]);
    else if (f) query = query.eq("entity", f);
    return S.q(query).then(function (rows) { return S.historyTable(rows, "All activity", true); }).then(function (h) {
      page(v, "audit", "<p class='lead'>Everything that happened on Saaz. Each car, garage, account and deal also shows its own history on its page.</p>" +
        "<div class='tabs'>" + FILTERS.map(function (x) { return "<a href='#/admin/audit?f=" + x[0] + "'" + (x[0] === f ? " aria-current='page'" : "") + ">" + x[1] + "</a>"; }).join("") + "</div>" + h);
    });
  });

  // One account: details, access, cars, offers, garage, and its history
  A("/user/([0-9a-f-]+)", function (v, m) {
    var id = m[0];
    return Promise.all([
      S.q(S.db.from("profiles").select("*").eq("id", id)), S.q(S.db.from("admins").select("user_id").eq("user_id", id)),
      S.q(S.db.from("listings").select("id,ref,make,model,year,status,price,currency").eq("seller_id", id).order("updated_at", { ascending: false })),
      S.q(S.db.from("deals").select("id,amount,status,updated_at, listings(ref,make,model,year,currency)").eq("buyer_id", id).order("updated_at", { ascending: false })),
      S.q(S.db.from("garage_members").select("role,status, garages(id,name,status)").eq("user_id", id)),
      S.q(S.db.from("audit_log").select("*").or("actor_id.eq." + id + ",entity_id.eq." + id).order("at", { ascending: false }).limit(300))
    ]).then(function (r) {
      var p = r[0][0]; if (!p) throw new Error("Account not found.");
      return S.historyTable(r[5], "History of this account: what they did, and what was done to it", true).then(function (h) {
        page(v, "users", "<p class='crumbs'><a href='#/admin/users'>Users</a> / " + esc(p.name || p.email) + "</p><div class='pagehead'><h2>" + esc(p.name || "(no name)") + "</h2>" +
          (r[1].length ? "<span class='chip'>Admin</span>" : "") + (p.trusted ? "<span class='chip s-live'>Trusted seller</span>" : "") + (p.suspended ? "<span class='chip s-suspended'>Suspended</span>" : "") + "</div>" +
          "<dl class='specs'>" + [["Email", p.email], ["Mobile", p.mobile || "–"], ["Country", S.COUNTRY[p.country] || "–"], ["Phone verified", p.phone_verified ? "Yes" : "No"], ["Joined", S.day(p.created_at)]]
            .map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd></div>"; }).join("") + "</dl>" +
          "<section><h2>Cars they listed</h2>" + table(["Ref", "Car", "Status", "Price"], r[2].map(function (l) {
            return "<tr><td><a href='#/admin/car/" + l.id + "'>" + esc(l.ref) + "</a></td><td>" + esc(S.name(l)) + "</td><td>" + S.chip(l.status) + "</td><td>" + S.money(l.currency, l.price) + "</td></tr>"; })) + "</section>" +
          "<section><h2>Offers they made</h2>" + table(["Car", "Figure", "Status", "Updated"], r[3].map(function (d) {
            return "<tr><td><a href='#/deals/" + d.id + "'>" + esc(d.listings.ref + " · " + d.listings.year + " " + d.listings.make + " " + d.listings.model) + "</a></td><td>" + S.money(d.listings.currency, d.amount) + "</td><td>" + S.chip(d.status) + "</td><td>" + S.day(d.updated_at) + "</td></tr>"; })) + "</section>" +
          "<section><h2>Garage team</h2>" + (r[4].length ? table(["Garage", "Role", "Status"], r[4].map(function (g) {
            return "<tr><td><a href='#/admin/garage/" + g.garages.id + "'>" + esc(g.garages.name) + "</a></td><td>" + esc(S.label(g.role)) + "</td><td>" + S.chip(g.status) + "</td></tr>"; })) : "<p class='note'>Not on a garage team.</p>") + "</section>" + h);
      });
    });
  });

  A("/outbox", function (v, m, q) {
    var ch = q.get("ch") || "", query = S.db.from("notifications").select("*").order("created_at", { ascending: false }).limit(300);
    if (ch) query = query.contains("channels", [ch]);
    return S.q(query).then(function (rows) {
      page(v, "outbox", "<div class='tabs'>" + [["", "All"], ["app", "App"], ["email", "Email"], ["sms", "SMS"]].map(function (x) { return "<a href='#/admin/outbox?ch=" + x[0] + "'" + (x[0] === ch ? " aria-current='page'" : "") + ">" + x[1] + "</a>"; }).join("") + "</div>" +
        "<p class='note'>Placeholder: email and SMS aren't connected, so those notices only land in each person's inbox.</p>" +
        table(["When", "To", "Kind", "Message", "Channels"], rows.map(function (n) { return "<tr><td>" + S.when(n.created_at) + "</td><td><small>" + esc(n.user_id.slice(0, 8)) + "</small></td><td>" + esc(n.kind) + "</td><td>" + esc(n.body) + "</td><td>" + esc(n.channels.join(", ")) + "</td></tr>"; })));
    });
  });

  // Saaz team: Admin (everything) and Staff (daily work). Admins add, change, remove and approve authenticators.
  A("/team", function (v) {
    return S.rpc("admin_staff_list").then(function (rows) {
      var full = !!(S.state.roles || {}).full_admin;
      page(v, "team", "<h2>Saaz team</h2><p class='note'><b>Admin:</b> everything, including settings and this page. <b>Staff:</b> cars, garages, deals, acting for sellers and buyers, supporting or objecting to reports. Everyone needs their own authenticator, approved by an admin.</p>" +
        table(["Name", "Email", "Role", "Authenticator", ""], rows.map(function (t) {
          var auth = t.pinned ? "Approved " + S.day(t.pinned_at) : t.authenticators === 1 ? "<b>Added " + S.when(t.authenticator_added_at) + ", waiting for approval</b>" : t.authenticators > 1 ? "<b class='bad'>" + t.authenticators + " on the account: they remove extras</b>" : "Not set up yet";
          var acts = t.me || !full ? (t.me ? "<small>you</small>" : "") :
            (!t.pinned && t.authenticators === 1 ? "<button class='btn small' data-pin='" + t.user_id + "'>Approve authenticator</button> " : "") +
            "<button class='btn small ghost dark' data-role='" + t.user_id + "' data-to='" + (t.role === "admin" ? "staff" : "admin") + "'>Make " + (t.role === "admin" ? "Staff" : "Admin") + "</button> " +
            "<button class='btn small ghost dark' data-rmstaff='" + t.user_id + "'>Remove</button>";
          return "<tr><td>" + esc(t.name) + "</td><td>" + esc(t.email) + "</td><td>" + esc(S.label(t.role)) + "</td><td>" + auth + "</td><td>" + acts + "</td></tr>";
        })) +
        (full ? "<section><h2>Add someone to the Saaz team</h2><form id='sf' class='inlineform'><label>Email of their Saaz account<input name='email' type='email' required></label><label>Role<select name='role'><option value='staff'>Staff</option><option value='admin'>Admin</option></select></label><button class='btn small'>Add</button></form>" +
          "<p class='note'>They create a normal Saaz account first. Then they sign in as Seller and choose Admin panel in their menu to add an authenticator; you approve it here. Approve only an authenticator added at a time they confirm.</p></section>" : ""));
      var sf = S.$("#sf"); if (sf) sf.onsubmit = function (e) { e.preventDefault(); var f = S.form(sf); S.act(sf.querySelector("button"), function () { return S.rpc("admin_add_staff", { p_email: f.email, p_role: f.role }); }, "Added. They're told how to start."); };
      S.$$("[data-pin]").forEach(function (b) { b.onclick = function () { S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("admin_pin_staff_authenticator", { p_user: b.dataset.pin }); }, "Authenticator approved."); }); }; });
      S.$$("[data-role]").forEach(function (b) { b.onclick = function () { S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("admin_set_staff_role", { p_user: b.dataset.role, p_role: b.dataset.to }); }, "Role changed."); }); }; });
      S.$$("[data-rmstaff]").forEach(function (b) { b.onclick = function () {
        S.popup("Remove from the Saaz team", "<label>Reason<textarea id='rmwhy' rows='2'></textarea></label><p class='note'>Their Admin access ends at once, on every device.</p>", [
          { text: "Cancel" }, { text: "Remove", primary: true, click: function (close, el) { el.disabled = true; S.rpc("admin_remove_staff", { p_user: b.dataset.rmstaff, p_reason: S.$("#rmwhy").value })
            .then(function () { close(); S.toast("Removed."); S.render(); }).catch(function (e2) { el.disabled = false; S.toast(S.friendly(e2), true); }); } }]);
      }; });
    });
  });

  A("/settings", function (v) {
    return S.q(S.db.from("settings").select("*").order("key")).then(function (rows) {
      page(v, "settings", "<p class='note'>Every number here is an assumption until you confirm it. Changes are logged.</p>" + table(["Setting", "Value", ""], rows.map(function (s) {
        return "<tr><td><b>" + esc(s.note) + "</b><small> " + esc(s.key) + "</small></td><td><input data-k='" + esc(s.key) + "' value='" + esc(typeof s.value === "string" ? s.value : JSON.stringify(s.value)) + "'></td><td><button class='btn small' data-save='" + esc(s.key) + "'>Save</button></td></tr>";
      })));
      S.$$("[data-save]").forEach(function (b) {
        b.onclick = function () {
          var raw = S.$("input[data-k='" + b.dataset.save + "']").value, val;
          try { val = JSON.parse(raw); } catch (e) { val = raw; }
          S.act(b, function () { return S.rpc("admin_set_setting", { p_key: b.dataset.save, p_value: val }); }, "Saved.");
        };
      });
    });
  });
})();
