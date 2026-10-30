/* app-core.js: the Saaz marketplace app at /app/. Client, router, helpers, accounts, header.
   Every change goes through a database function (supabase/marketplace_*.sql). The page never decides who may do what. */
(function () {
  // 30 Oct 2026 (security): Saaz never runs inside another site's frame (clickjacking). GitHub Pages can't send frame headers.
  if (window.top !== window.self) { try { window.top.location = window.self.location.href; } catch (e) {} document.documentElement.innerHTML = ""; return; }
  var C = window.SAAZ || {};
  // Links in Saaz emails (invite, password reset, email confirmation) arrive as #access_token=...&type=...
  // Read them before the Supabase client clears the address bar.
  var AUTH_LINK = (function () {
    var h = location.hash.replace(/^#/, "");
    if (!/(^|&)(access_token|error_description)=/.test(h)) return null;
    var p = new URLSearchParams(h); return { type: p.get("type"), error: p.get("error_description") };
  })();
  // New email links: ?token_hash=...&type=...#/confirm. The code is only used when the person taps on the page,
  // so email scanners that open links (Gmail does) can't use it up first. Taken out of the address straight away.
  var EMAIL_CODE = (function () {
    var q = new URLSearchParams(location.search), th = q.get("token_hash"), ty = q.get("type");
    if (!th || !ty) return null;
    try { history.replaceState(null, "", location.pathname + "#/confirm"); } catch (e) {}
    return { token_hash: th, type: ty };
  })();
  // Where an email link should land: ?next=seller (sign-up as seller) or ?next=garage (garage invite)
  var NEXT = new URLSearchParams(location.search).get("next");
  var S = window.Saaz = { routes: [], state: { session: null, roles: null } };
  var configured = C.supabaseUrl && C.supabaseAnonKey && window.supabase;
  S.db = configured ? window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey, { auth: { persistSession: true, autoRefreshToken: true } }) : null;
  S.site = C.base || "/";
  // One handler for small page actions written into markup, so no page needs inline script (the security policy blocks it):
  // data-after (remember where to come back to after signing in), data-print, data-jump (a select that changes page).
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("[data-after],[data-print]"); if (!a) return;
    if (a.hasAttribute("data-print")) { e.preventDefault(); window.print(); return; }
    S.after = a.getAttribute("data-after") || location.hash;
  });
  document.addEventListener("change", function (e) { var t = e.target; if (t && t.hasAttribute && t.hasAttribute("data-jump") && /^#\//.test(t.value)) location.hash = t.value; });

  // ---------- helpers ----------
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  S.esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  // Links built from stored data go through here: only Saaz's own pages (#/...) are allowed, anything else becomes the fallback.
  S.safeHref = function (h, fallback) { h = String(h == null ? "" : h); return /^#\/[^\s"'<>]*$/.test(h) ? h : (fallback || "#/"); };
  S.money = function (cur, n) { return n == null ? "" : (cur || "UGX") + " " + Number(n).toLocaleString("en-US"); };
  // Saaz runs on East Africa Time (Africa/Kampala), whatever the visitor's device is set to
  var EAT = { timeZone: "Africa/Kampala" };
  function parts(d, o) { var r = {}; new Intl.DateTimeFormat("en-GB", Object.assign({}, EAT, o)).formatToParts(d).forEach(function (x) { r[x.type] = x.value; }); return r; }
  S.day = function (iso) {
    if (!iso) return "";
    var d = new Date(iso.length === 10 ? iso + "T12:00:00+03:00" : iso), p = parts(d, { day: "numeric", month: "short", year: "numeric" });
    return p.day + " " + p.month + " " + p.year;
  };
  S.when = function (iso) { if (!iso) return ""; var p = parts(new Date(iso), { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }); return S.day(iso) + ", " + p.hour + ":" + p.minute + " EAT"; };
  S.km = function (n) { return n == null ? "" : Number(n).toLocaleString("en-US") + " km"; };
  // Status words come from the database; "review" there means the Saaz inspection
  S.label = function (s) { return String(s || "").replace(/_/g, " ").replace(/\breview\b/g, "inspection").replace(/^./, function (c) { return c.toUpperCase(); }); };
  S.name = function (l) { return [l.year, l.make, l.model].filter(function (x) { return x !== "" && x != null; }).join(" "); };
  S.photo = function (p) { return p ? C.supabaseUrl + "/storage/v1/object/public/car-photos/" + p : ""; };
  S.chip = function (status) { return "<span class='chip s-" + S.esc(status) + "'>" + S.esc(S.label(status)) + "</span>"; };
  S.$ = function (sel, root) { return (root || document).querySelector(sel); };
  S.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  S.form = function (f) { var o = {}; new FormData(f).forEach(function (v, k) { o[k] = typeof v === "string" ? v.trim() : v; }); return o; };
  S.device = function () {
    try { var d = localStorage.getItem("saaz-device"); if (!d) { d = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("saaz-device", d); } return d; }
    catch (e) { return null; }
  };
  // Saaz operates in Uganda only. Regions must match the regions table in the database.
  S.COUNTRY_CODE = "UG";
  S.REGIONS = { UG: ["Kampala", "Wakiso", "Entebbe", "Mukono", "Jinja", "Mbarara", "Gulu"] };
  S.COUNTRY = { UG: "Uganda" };

  // Database errors come back as plain sentences from the functions. Show them as they are.
  S.friendly = function (e) {
    var m = (e && (e.message || e.msg || e.error_description)) || String(e || "Something went wrong.");
    if (/Failed to fetch|NetworkError|network/i.test(m)) return "Couldn't reach Saaz. Check your connection and try again.";
    if (/Invalid login credentials/i.test(m)) return "Wrong email or password.";
    if (/Email not confirmed/i.test(m)) return "Confirm your email first: open the link Saaz sent you.";
    if (/JWT|token is expired/i.test(m)) return "Your session ended. Sign in again.";
    if (/violates row-level security|permission denied/i.test(m)) return "You don't have access to do that.";
    if (e && e.code === "42501") return m;   // Saaz's own access answers (Build Assistant: "Not found.", "switched off")
    if (e && e.code === "PT429") return "Too many requests. Wait a few minutes and try again.";
    // Database messages Saaz wrote itself (raise exception, code P0001) are meant for people. Any other database or API
    // error (constraint names, types, internal paths) stays out of the page: logged for debugging, a plain sentence shown.
    if (e && typeof e.code === "string" && /^([0-9A-Z]{5}|PGRST\d+)$/.test(e.code) && e.code !== "P0001") {
      try { console.error("Saaz:", e.code, m); } catch (x) {}
      return "Something went wrong. Try again, and tell Saaz if it keeps happening.";
    }
    return m;
  };
  S.rpc = function (fn, args) {
    return S.db.rpc(fn, args || {}).then(function (r) { if (r.error) throw r.error; return r.data; });
  };
  S.q = function (promise) { return promise.then(function (r) { if (r.error) throw r.error; return r.data; }); };
  // Pop-up over the current page. buttons: [{text, primary, click(close)}]. Closes on the X, Escape, or a button.
  S.popup = function (title, html, buttons) {
    var old = document.getElementById("saaz-pop"); if (old) old.remove();
    var d = document.createElement("dialog"); d.id = "saaz-pop"; d.className = "pop"; d.setAttribute("aria-labelledby", "pop-h");
    d.innerHTML = "<button class='pop-x' aria-label='Close'>&times;</button><h2 id='pop-h'>" + S.esc(title) + "</h2><div class='pop-body'>" + html + "</div><div class='pop-acts'></div>";
    var close = function () { if (d.open) d.close(); d.remove(); };
    (buttons || [{ text: "OK", primary: true }]).forEach(function (b) {
      var el = document.createElement("button"); el.className = "btn" + (b.primary ? "" : " ghost"); el.textContent = b.text;
      el.onclick = function () { if (b.click) b.click(close, el); else close(); }; d.querySelector(".pop-acts").appendChild(el);
    });
    d.querySelector(".pop-x").onclick = close; d.addEventListener("cancel", function (e) { e.preventDefault(); close(); });
    document.body.appendChild(d); d.showModal(); return close;
  };
  // One toast that changes state: S.busy("Saving…") stays up with a spinner until the next S.toast or S.toastHide.
  // S.toast(msg, bad, action): action {text, href} or {text, click} puts one button inside the toast.
  S.toast = function (msg, bad, action) {
    var t = S.$("#toast"); clearTimeout(S._t);
    t.textContent = ""; var m = document.createElement("span"); m.className = "tmsg"; m.textContent = msg; t.appendChild(m);
    if (action && action.text) {
      var a = document.createElement(action.href ? "a" : "button"); a.className = "tact"; a.textContent = action.text;
      if (action.href) a.href = action.href; else a.type = "button";
      a.onclick = function () { t.className = "toast"; if (action.click) action.click(); }; t.appendChild(a);
    }
    t.className = "toast show" + (bad ? " bad" : "");
    S._t = setTimeout(function () { t.className = "toast"; }, action ? 6000 : 4200);
  };
  S.busy = function (msg) {
    var t = S.$("#toast"); clearTimeout(S._t);
    t.textContent = ""; var m = document.createElement("span"); m.className = "tmsg"; m.textContent = msg; t.appendChild(m);
    t.className = "toast show busy";
  };
  S.toastHide = function () { clearTimeout(S._t); var t = S.$("#toast"); if (t) t.className = "toast"; };
  // Run an action from a button: disable it, show the database's answer, then re-render.
  S.act = function (btn, fn, ok) {
    if (btn) btn.disabled = true;
    return Promise.resolve().then(fn).then(function (r) { if (ok) S.toast(typeof ok === "function" ? ok(r) : ok); S.render(); return r; })
      .catch(function (e) { S.toast(S.friendly(e), true); if (btn) btn.disabled = false; });
  };
  S.confirmBtn = function (btn, fn) { // two taps for anything that can't be undone
    if (btn.dataset.armed) return fn();
    btn.dataset.armed = "1"; var t = btn.textContent; btn.textContent = "Tap again to confirm";
    setTimeout(function () { delete btn.dataset.armed; btn.textContent = t; }, 4000);
  };
  // Invite email for someone added to a garage who has no Saaz account yet (Edge Function invite-user)
  S.sendInvite = function (email) {
    return S.db.functions.invoke("invite-user", { body: { email: email, redirectTo: location.origin + location.pathname + "?next=garage" } }).then(function (r) {
      if (!r.error) return (r.data && r.data.kind === "password_link" ? "Set-password email sent to " : "Invite email sent to ") + email + ". The link works for " + (S.linkHours || 24) + " hours.";
      var ctx = r.error.context;
      return (ctx && ctx.json ? ctx.json().catch(function () { return {}; }) : Promise.resolve({})).then(function (b) {
        throw new Error((b && b.error) || "Couldn't send the invite email to " + email + ". They're saved on your team: tap Send invite email to try again.");
      });
    });
  };
  // Team rows (garage Team page and admin garage page): invite state, and the buttons an owner or admin gets
  // Invite stage of a team member: Invited until they set their password, then Accepted. Separate from the garage's certification.
  S.inviteStage = function (t) {
    if (t.status === "removed") return S.chip("removed");
    if (t.kind === "invite" || !t.accepted_at) return "<span class='chip s-invited'>Invited</span>";
    return "<span class='chip s-accepted'>Accepted</span>" + (t.garage_status && t.garage_status !== "certified" ? " <small>can work once Saaz certifies the garage</small>" : "");
  };
  S.garageStage = function (status) {
    return { certified: "Certified by Saaz", applied: "Application with Saaz, not certified yet", more_info: "Saaz asked for more information, not certified yet",
      rejected: "Application not approved", suspended: "Suspended by Saaz" }[status] || S.label(status);
  };
  S.inviteInfo = function (t) {
    if (t.kind === "invite") return "Invite not sent yet";
    if (t.status !== "invited" || !t.invited_at || t.accepted_at) return "";
    var expired = t.link_expires_at && new Date(t.link_expires_at) < new Date();
    return "Invite sent " + S.when(t.invited_at) + " · " + (expired ? "<b class='bad'>link expired " + S.when(t.link_expires_at) + "</b>" : "link expires " + S.when(t.link_expires_at));
  };
  S.teamActions = function (t, manage) {
    if (!manage || t.status === "removed" || (t.user_id && t.user_id === S.me().id)) return "";
    var e = S.esc(t.email);
    if (t.kind === "invite") return "<button class='btn small ghost' data-inv='" + e + "'>Send invite</button> <button class='btn small ghost' data-rv='" + t.id + "'>Revoke</button>";
    if (t.status === "invited" && !t.accepted_at) return "<button class='btn small ghost' data-inv='" + e + "'>Resend invite</button> <button class='btn small ghost' data-rm='" + t.id + "' data-what='revoke'>Revoke</button>";
    return "<button class='btn small ghost' data-rm='" + t.id + "'>Remove</button>";
  };
  S.wireTeam = function (root) {
    S.wireInvites(root);
    S.$$("[data-rv]", root).forEach(function (b) { b.onclick = function () { S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("revoke_garage_invite", { p_invite: b.dataset.rv }); }, "Invite revoked."); }); }; });
    S.$$("[data-rm]", root).forEach(function (b) { b.onclick = function () { S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("remove_garage_member", { p_member: b.dataset.rm }); }, b.dataset.what === "revoke" ? "Invite revoked. The link no longer opens the garage." : "Removed."); }); }; });
  };
  S.wireInvites = function (root) {
    S.$$("[data-inv]", root).forEach(function (b) {
      b.onclick = function () { b.disabled = true; S.sendInvite(b.dataset.inv).then(function (m) { S.toast(m); setTimeout(S.render, 1200); }).catch(function (e) { S.toast(S.friendly(e), true); b.disabled = false; }); };
    });
  };
  // Admin acting for a seller or buyer (part 11). One reason box per section; every button sends it with admin_act.
  // items: [{kind, target, label, fields (html, optional), p(form) -> jsonb, confirm (bool)}]
  S.actFor = function (id, title, intro, items) {
    return "<section class='actfor' id='" + id + "'><h2>" + S.esc(title) + "</h2><p class='note'>" + intro + "</p>" +
      "<label>Reason (they see it, and it goes in the history)<textarea name='reason' rows='2' minlength='10' placeholder='For example: seller phoned, can not upload from their phone'></textarea></label>" +
      "<div class='actitems'>" + items.map(function (it, i) {
        return "<form class='inlineform' data-i='" + i + "'>" + (it.fields || "") + "<button class='btn small ghost'>" + S.esc(it.label) + "</button></form>";
      }).join("") + "</div></section>";
  };
  S.wireActFor = function (id, items) {
    var box = S.$("#" + id); if (!box) return;
    S.$$("form[data-i]", box).forEach(function (f) {
      var it = items[+f.dataset.i];
      f.onsubmit = function (e) {
        e.preventDefault(); var b = f.querySelector("button"), why = box.querySelector("textarea[name=reason]").value.trim();
        if (why.length < 10) { S.toast("Write the reason first (10 characters or more).", true); box.querySelector("textarea").focus(); return; }
        var run = function () { S.act(b, function () { return S.rpc("admin_act", { p_kind: it.kind, p_target: it.target, p_reason: why, p: it.p ? it.p(S.form(f)) : {} }); }, function (r) { return "Done: " + (r && r.done ? r.done : "saved") + ". They're told, with your reason."; }); };
        if (it.confirm) S.confirmBtn(b, run); else run();
      };
    });
  };
  // Every inspection of a car, each with its own inspection ID (car_inspections, part 13)
  S.loadInspections = function (id, listingId) {
    return S.rpc("car_inspections", { p_listing: listingId }).then(function (rows) {
      var el = S.$("#" + id); if (!el) return;
      el.innerHTML = rows.length ? "<div class='tablewrap'><table class='tbl'><thead><tr><th>Inspection ID</th><th>Type</th><th>Garage</th><th>Inspector</th><th>Status</th><th>Result</th><th>Saaz</th></tr></thead><tbody>" + rows.map(function (r0) {
        var x = r0;
        return "<tr><td><a href='#/inspection/" + S.esc(x.doc_no) + "'>" + S.esc(x.doc_no || "") + "</a>" + (x.verify_code ? " · <a href='#/report/" + S.esc(x.verify_code) + "'>report</a>" : "") + "</td><td>" + S.esc(x.scope_name || "") + "</td><td>" + S.esc(x.garage || "") + "</td><td>" + S.esc(x.inspector || "") + "</td><td>" + S.inspChip(x.status) +
          "<small> " + S.day(x.issued_at || x.started_at) + "</small></td><td>" + (x.verdict ? S.esc(S.label(x.verdict)) + " " + x.score : "") + "</td><td>" + (x.saaz_stance === "object" ? "<span class='chip s-flag'>Objected</span>" : x.saaz_stance === "support" ? "<span class='chip s-pass'>Supported</span>" : "") + "</td></tr>";
      }).join("") + "</tbody></table></div><p class='note'>" + rows.length + " inspection" + (rows.length === 1 ? "" : "s") + " of this car, each with its own ID.</p>" : "<p class='note'>No inspections yet.</p>";
    }).catch(function (e) { var el = S.$("#" + id); if (el) el.innerHTML = "<p class='note'>" + S.esc(S.friendly(e)) + "</p>"; });
  };
  // What Saaz said about a report, and the garage's replies (opinions, part 13)
  S.opinionsHtml = function (ops) {
    if (!ops || !ops.length) return "<p class='note'>Saaz has not commented on this report.</p>";
    return "<ul class='timeline'>" + ops.map(function (o) {
      var what = o.stance === "object" ? "<b class='bad'>Saaz objected</b>" : o.stance === "support" ? "<b>Saaz supports this report</b>" : "<b>Garage replied</b>";
      return "<li><small>" + S.when(o.at) + "</small> " + what + ": " + S.esc(o.reason) + "</li>";
    }).join("") + "</ul>";
  };
  S.showOpinions = function (id, code) {
    return S.rpc("review_document", { p_code: code }).then(function (d) { var el = S.$("#" + id); if (el) el.innerHTML = S.opinionsHtml(d && d.opinions); });
  };
  // Inspection types (General and scoped), from the database table inspection_scopes. Cached for the visit.
  S.scopes = function () {
    if (S._scopes) return Promise.resolve(S._scopes);
    return S.q(S.db.from("inspection_scopes").select("*").order("sort")).then(function (rows) { var m = {}; rows.forEach(function (x) { m[x.key] = x; }); S._scopes = { list: rows, by: m }; return S._scopes; });
  };
  // Inspection status words for people (the database says draft for "in progress")
  S.inspStatus = function (st) { return { requested: "Requested", draft: "In progress", issued: "Completed", superseded: "Completed, replaced by a newer report", cancelled: "Cancelled", void: "Void" }[st] || S.label(st); };
  S.inspChip = function (st) { var cls = { requested: "awaiting_review", draft: "in_play", issued: "issued", superseded: "issued", cancelled: "cancelled", void: "void" }[st] || st; return "<span class='chip s-" + cls + "'>" + S.esc(S.inspStatus(st)) + "</span>"; };
  S.bars = function (rows) { // tiny bar chart: [{label, value}]
    var max = Math.max.apply(null, rows.map(function (r) { return r.value; }).concat([1]));
    return "<div class='bars' role='img' aria-label='" + S.esc(rows.map(function (r) { return r.label + ": " + r.value; }).join(", ")) + "'>" +
      rows.map(function (r) { return "<div class='bar'><i style='height:" + Math.round(r.value / max * 100) + "%'></i><span>" + S.esc(r.short || "") + "</span></div>"; }).join("") + "</div>";
  };

  // ---------- accounts ----------
  S.loadRoles = function () {
    if (!S.db) return Promise.resolve(null);
    return S.db.auth.getSession().then(function (r) {
      S.state.session = r.data.session;
      if (!S.state.session) { S.state.roles = null; return null; }
      return S.rpc("my_roles").then(function (roles) { S.state.roles = roles; return roles; });
    }).catch(function () { S.state.roles = null; });
  };
  S.mode = function (m) {
    try { if (m) localStorage.setItem("saaz-mode", m); return m || localStorage.getItem("saaz-mode") || "buyer"; } catch (e) { return m || "buyer"; }
  };
  S.home = function () { var m = S.mode(); if (m === "admin" && !S.isAdmin()) m = "buyer"; return { seller: "#/my/cars", garage: "#/garage", admin: "#/admin" }[m] || "#/browse"; };
  // One sign-out for every role and page: end the session on Supabase (all devices, so admin elevation is gone too),
  // forget everything this browser kept, and land on the public listings at the site root. Never the sign-in page.
  S.signOut = function (notice) {
    if (S._signingOut) return; S._signingOut = true;
    var done = function () {
      S.state.roles = null; S.state.session = null; S.after = null;
      try { localStorage.removeItem("saaz-mode"); Object.keys(localStorage).forEach(function (k) { if (/^sb-.*-auth-token/.test(k) || /^saaz-build-/.test(k) || /^saaz-sell/.test(k)) localStorage.removeItem(k); }); } catch (e) {}
      try { if (notice) sessionStorage.setItem("saaz-bye", notice); } catch (e) {}
      location.replace(location.origin + S.site);
    };
    var p = S.db ? S.db.auth.signOut({ scope: "global" }) : Promise.resolve();
    Promise.resolve(p).then(done, done);
  };
  S.signedIn = function () { return !!(S.state.roles && S.state.roles.signed_in); };
  S.isAdmin = function () { return !!(S.state.roles && S.state.roles.admin); };
  // In Admin: an admin session (password and authenticator, checked by the database) and Admin chosen as the area.
  // It lasts until the admin leaves Admin, switches area, signs out, or the admin session ends. Viewing the marketplace keeps it.
  S.inAdmin = function () { return S.isAdmin() && S.mode() === "admin"; };
  S.leaveAdmin = function () { S.mode("buyer"); S.toast("You left Admin. Your account menu takes you back while your admin session lasts."); S.go("#/browse"); };
  S.me = function () { return (S.state.roles && S.state.roles.profile) || {}; };

  // ---------- router ----------
  S.route = function (pattern, handler, need) { S.routes.push({ re: new RegExp("^" + pattern + "$"), handler: handler, need: need }); };
  S.go = function (hash) { if (location.hash === hash) S.render(); else location.hash = hash; };

  // ---------- shell: one top bar everywhere, plus a work-area bar in Selling, Garage and Admin ----------
  // Everyone starts on the marketplace. The logo and "Buy cars" always go back to it; the account menu switches area.
  function areaOf(path) {
    if (/^\/(my\/|sell\/)/.test(path)) return "seller";
    if (/^\/garage(\/|$)/.test(path) && path !== "/garage/apply") return "garage";
    if (/^\/admin(\/|$)/.test(path) && path !== "/admin/verify") return "admin";
    return "";
  }
  S.areaOf = areaOf;
  function initials(p) {
    var n = String(p.name || p.email || "?").trim().split(/\s+/).filter(function (w) { return /^[A-Za-z\u00C0-\u024F]/.test(w); });  // words that start with a letter: "Sam Seller (demo)" gives SS
    if (!n.length) n = ["?"];
    return ((n[0] || "?")[0] + (n.length > 1 ? n[n.length - 1][0] : "")).toUpperCase();
  }
  function areas(r) {
    var a = [["buyer", "Buying", "#/browse"], ["seller", "Selling", "#/my/cars"]];
    if (r.garage) a.push(["garage", "Garage: " + (r.garage.name || "my garage"), "#/garage"]);
    if (S.isAdmin()) a.push(["admin", "Admin", "#/admin"]);  // only while the admin session lasts: no password or code needed to go back
    return a;
  }
  function header(path, area) {
    var r = S.state.roles, on = function (test) { return test ? " aria-current='page'" : ""; };
    var links = "<a href='#/browse'" + on(path === "/browse" && !/saved=1/.test(location.hash) || /^\/car\//.test(path)) + ">Buy cars</a>" +
      "<a href='#/selling'" + on(path === "/selling") + ">What's selling</a><a href='#/verify'" + on(path === "/verify" || /^\/report\//.test(path)) + ">Verify a report</a>" +
      "<a href='#/track'" + on(path === "/track" || /^\/inspection\//.test(path)) + ">Track an inspection</a>";
    var right;
    if (r && r.signed_in) {
      var p = S.me(), cur = area || (S.inAdmin() ? "admin" : "buyer");
      right = "<a class='hide-s' href='#/browse?saved=1'" + on(/saved=1/.test(location.hash)) + ">Saved</a>" +
        "<a class='hide-s' href='#/offers'" + on(path === "/offers" || /^\/deals\//.test(path)) + ">My offers</a>" +
        "<a href='#/inbox' class='inbox'" + on(path === "/inbox") + ">Inbox<b id='unread' hidden></b></a>" +
        "<a class='sellbtn' data-ref='sell-btn' href='#/sell/new'>Sell a car</a>" +
        "<details class='acct' id='acct' data-ref='account-menu'><summary aria-label='Account menu'><span class='av'>" + S.esc(initials(p)) + "</span> ▾</summary><div class='acctmenu'>" +
        "<p class='who'><b>" + S.esc(p.name || "") + "</b><small>" + S.esc(p.email || "") + "</small></p>" +
        "<b class='mh'>Switch area</b>" + areas(r).map(function (x) {
          return "<a href='" + x[2] + "' data-mode='" + x[0] + "'" + (x[0] === cur ? " aria-current='true'" : "") + ">" + S.esc(x[1]) + (x[0] === cur ? " <small>you're here</small>" : "") + "</a>";
        }).join("") +
        (r.admin_account && !S.isAdmin() && area !== "garage" && S.mode() === "seller" ? "<hr><a href='#/admin/verify' class='adminentry'>Admin panel <small>password and authenticator</small></a>" : "") +
        (S.inAdmin() ? "<hr><button type='button' id='leaveadmin'>Leave Admin</button>" : "") +
        "<hr><a class='show-s' href='#/browse?saved=1'>Saved</a><a class='show-s' href='#/offers'>My offers</a>" +
        "<a href='#/account'>My account</a><button type='button' id='signout'>Sign out</button></div></details>";
    } else {
      right = "<a href='#/signin'" + on(path === "/signin") + ">Sign in</a><a class='hide-s' href='#/signup'" + on(path === "/signup") + ">Create account</a><a class='sellbtn' data-ref='sell-btn' href='#/sell'>Sell a car</a>";
    }
    var head = "<header class='apphead' data-ref='header'><div class='wrap'><a class='logo' data-ref='logo' href='#/' aria-label='Saaz home'><img src='" + S.site + "assets/img/brand/saaz-wordmark-white-240.webp' srcset='" + S.site + "assets/img/brand/saaz-wordmark-white-240.webp 1x, " + S.site + "assets/img/brand/saaz-wordmark-white-480.webp 2x' width='112' height='32' alt='Saaz'></a>" +
      "<nav class='appnav' data-ref='main-nav' aria-label='Marketplace'>" + links + "</nav><div class='appright'>" + right + "</div></div></header>";
    return head + areaBar(path, area);
  }
  function areaBar(path, area) {
    // Viewing the marketplace while in Admin: a bar that keeps the way back, and says offers and saves are off
    if (!area && S.inAdmin()) return "<div class='areabar viewas' data-ref='area-bar'><div class='wrap'><a class='back' href='#/admin'>‹ Back to Admin</a><b>Viewing the marketplace as admin</b>" +
      "<span id='viewas-extra'></span><button type='button' class='btn text' id='leaveadmin2'>Leave Admin</button></div></div>";
    if (!area || !S.signedIn()) return "";
    var r = S.state.roles, tabs = [], title = "";
    if (area === "seller") { title = "Selling"; tabs = [["#/my/cars", "My cars", /^\/my\//.test(path)], ["#/sell/new", "List a car", /^\/sell\//.test(path)]]; }
    if (area === "garage") { title = "Garage" + (r.garage && r.garage.name ? ": " + r.garage.name : ""); tabs = [["#/garage", r.garage && r.garage.member_role === "owner" ? "Jobs" : "My jobs", path !== "/garage/team"]];
      if (r.garage && r.garage.member_role === "owner") tabs.push(["#/garage/team", "Team", path === "/garage/team"]); }
    if (area === "admin") title = "Admin";
    var back = area === "admin" ? "<a class='back' href='#/browse'>View marketplace as admin</a>" : "<a class='back' href='#/browse'>‹ Back to marketplace</a>";
    return "<div class='areabar' data-ref='area-bar'><div class='wrap'>" + back + "<b>" + S.esc(title) + "</b>" + (area === "admin" ? "<button type='button' class='btn text' id='leaveadmin2'>Leave Admin</button>" : "") +
      (tabs.length ? "<nav aria-label='" + S.esc(title) + "'>" + tabs.map(function (t) { return "<a href='" + t[0] + "'" + (t[2] ? " aria-current='page'" : "") + ">" + t[1] + "</a>"; }).join("") + "</nav>" : "") + "</div></div>";
  }
  function wireHeader() {
    var acct = S.$("#acct");
    if (acct) {
      S.$$("[data-mode]", acct).forEach(function (a) { a.onclick = function () { S.mode(a.dataset.mode); }; });
      document.onclick = function (e) { if (acct.open && !acct.contains(e.target)) acct.open = false; };
      acct.onkeydown = function (e) { if (e.key === "Escape") { acct.open = false; acct.querySelector("summary").focus(); } };
    }
    var so = S.$("#signout"); if (so) so.onclick = function () { so.disabled = true; S.signOut(); };
    ["#leaveadmin", "#leaveadmin2"].forEach(function (id) { var b = S.$(id); if (b) b.onclick = S.leaveAdmin; });
    if (S.signedIn()) S.q(S.db.from("notifications").select("id", { count: "exact", head: false }).eq("read", false).eq("user_id", S.me().id)).then(function (rows) {
      var b = S.$("#unread"); if (b && rows.length) { b.hidden = false; b.textContent = rows.length; }
    }).catch(function () {});
  }

  // Build Assistant (part 18): the database decides who may use it. Only then is its script loaded.
  // Visitors, buyers, sellers, garages and staff who aren't developers never get the script or any of its data.
  function buildCheck() {
    if (S._buildLoaded || S._buildChecking || !S.isAdmin()) return;
    var tok = (S.state.session || {}).access_token;
    if (S._buildNo === tok) return;   // already told no (or Part 18 isn't there) for this session: don't ask on every page
    S._buildChecking = true;
    S.rpc("build_status").then(function (s) {
      if (!s || !s.allowed || !s.enabled) { S._buildChecking = false; S._buildNo = tok; return; }
      var tag = document.createElement("script"); tag.src = S.site + "assets/build-assistant.js?v=" + encodeURIComponent(C.build || ""); tag.defer = true;
      document.body.appendChild(tag);
    }).catch(function () { S._buildChecking = false; S._buildNo = tok; });
  }
  S.buildCheck = buildCheck;

  var linkPending = false;
  S.render = function () {
    if (linkPending) return; // the Supabase client may change the address while it reads an email link
    if (AUTH_LINK) {
      var link = AUTH_LINK; AUTH_LINK = null; linkPending = true;
      var next = function () {
        linkPending = false;
        if (link.error) { history.replaceState(null, "", location.pathname + "#/signin"); setTimeout(function () { S.toast(link.error.replace(/\+/g, " ") + " Ask for a new link.", true); }, 600); }
        else {
          if (NEXT === "seller" || NEXT === "garage") S.mode(NEXT);
          if (NEXT === "sellnew") S.mode("seller");
          var land = link.type === "invite" ? "#/reset?first=1" : link.type === "recovery" ? "#/reset" : (NEXT === "sellnew" ? "#/sell/new" : NEXT === "seller" ? "#/my/cars" : "#/browse");
          history.replaceState(null, "", location.pathname + land);
        }
        S.render(); if (link.type === "signup") S.toast("Email confirmed. Welcome to Saaz.");
      };
      // Let the Supabase client read the sign-in from the address bar first, then tidy the address
      return S.db ? S.db.auth.getSession().then(next, next) : next();
    }
    var hash = location.hash.replace(/^#/, "") || "/";
    var path = hash.split("?")[0], query = new URLSearchParams(hash.split("?")[1] || "");
    var root = S.$("#app");
    if (!S.db) { root.innerHTML = "<div class='wrap pad'><div class='empty'><b>Saaz isn't connected yet</b><span>The database settings are missing from this build.</span></div></div>"; return; }
    S.loadRoles().then(function () {
      if (S.signedIn()) S.rpc("tick").catch(function () {}); // garage time-outs and review expiry
      var match = null, m;
      for (var i = 0; i < S.routes.length; i++) { m = S.routes[i].re.exec(path); if (m) { match = S.routes[i]; break; } }
      var area = S.signedIn() ? areaOf(path) : "";
      if (area === "admin" && !S.isAdmin()) area = "";  // no Admin bar on the "Page not found" a non-admin sees
      if (area && (area !== "garage" || S.state.roles.garage) && (area !== "admin" || S.isAdmin())) S.mode(area);
      buildCheck();
      root.innerHTML = header(path, area) + "<main id='view' class='wrap pad" + (area || S.inAdmin() ? " inarea" : "") + "'><p class='loading'>Loading…</p></main>";
      wireHeader();
      var view = S.$("#view");
      var notFound = "<div class='empty'><b>Page not found</b><span><a href='#/browse'>Browse cars</a></span></div>";
      // Inside Admin, a missing or failing page keeps the Admin menu, so there is always a way to the other Admin pages
      var inAdminShell = function (h) { if (area === "admin" && S.adminPage) S.adminPage(view, "", h); else view.innerHTML = h; };
      if (!match) { inAdminShell(notFound); return; }
      // Admin pages look like any missing page unless this session passed the admin's authenticator (checked by the database)
      if (match.need === "admin" && !S.isAdmin()) { view.innerHTML = notFound; return; }
      // Signed out (or the session ended) on a page that needs an account: a public page with a sign-in option, never the page itself
      if (match.need && !S.signedIn()) {
        view.innerHTML = "<div class='empty'><b>Sign in to see this page</b><span><a class='btn small' href='#/signin' id='needsignin'>Sign in</a> or <a href='#/browse'>browse cars</a></span></div>";
        var ns = S.$("#needsignin"), here = location.hash; if (ns) ns.onclick = function () { S.after = here; };
        return;
      }
      window.scrollTo(0, 0);
      Promise.resolve(match.handler(view, m.slice(1), query)).catch(function (e) {
        var h = "<div class='empty'><b>Couldn't load this page</b><span>" + S.esc(S.friendly(e)) + "</span></div>";
        if (/^\/admin\/reports/.test(path) && S.reportShell) S.reportShell(view, path.split("/")[3] || "", query, h); else inAdminShell(h);
      });
    });
  };

  // ---------- sign in, sign up, passwords ----------
  var ROLES = [["buyer", "Buyer"], ["seller", "Seller"], ["garage", "Garage team"]];
  S.route("/signin", function (v) {
    v.innerHTML = "<div class='narrow'><h1>Sign in</h1>" +
      "<form id='f' class='stack'><fieldset class='seg'><legend>Sign in as</legend>" + ROLES.map(function (r, i) {
        return "<label><input type='radio' name='as' value='" + r[0] + "'" + (r[0] === S.mode() || (!i && ["seller", "garage"].indexOf(S.mode()) < 0) ? " checked" : "") + "><span>" + r[1] + "</span></label>";
      }).join("") + "</fieldset>" +
      "<label>Email<input name='email' type='email' autocomplete='email' required></label>" +
      "<label>Password<input name='password' type='password' autocomplete='current-password' required></label>" +
      "<p class='err' id='err' role='alert'></p><button class='btn wide'>Sign in</button></form>" +
      "<p class='note'><a href='#/forgot'>Forgot your password?</a> · <a href='#/signup'>Create an account</a> · <a href='#/garage/apply'>Become a certified garage</a></p></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#err"), b = e.target.querySelector("button");
      b.disabled = true; err.textContent = "";
      S.db.auth.signInWithPassword({ email: f.email, password: f.password }).then(function (r) {
        if (r.error) throw r.error;
        return S.loadRoles();
      }).then(function (roles) {
        if (f.as === "garage") return S.rpc("garage_sign_in").then(function (g) {
          if (!g.ok) { S.mode("buyer"); throw new Error(g.message); }
          S.mode("garage"); S.go("#/garage");
        });
        S.mode(f.as);
        var next = S.after; S.after = null; S.go(next && next !== "#/signin" ? next : S.home());
      }).catch(function (e2) { err.textContent = S.friendly(e2); b.disabled = false; });
    };
  });

  S.route("/signup", function (v) {
    // Came from "Start selling" on #/sell: seller is ticked, and the email link brings them back to the listing form (next=sellnew)
    var selling = /^#\/sell\/new/.test(S.after || "");
    var nextFor = function (as) { return as === "seller" ? (selling ? "sellnew" : "seller") : "buyer"; };
    v.innerHTML = "<div class='narrow'><h1>Create your Saaz account</h1><p class='lead'>" + (selling ? "One account to sell and buy. Next you add your car." : "One account to buy and sell.") + "</p>" +
      "<form id='f' class='stack'><fieldset class='seg'><legend>I'm here to</legend><label><input type='radio' name='as' value='buyer'" + (selling ? "" : " checked") + "><span>Buy a car</span></label>" +
      "<label><input type='radio' name='as' value='seller'" + (selling ? " checked" : "") + "><span>Sell a car</span></label></fieldset>" +
      "<label>Full name<input name='name' autocomplete='name' required minlength='2'></label>" +
      "<label>Email<input name='email' type='email' autocomplete='email' required></label>" +

      "<label>Mobile number<input name='mobile' type='tel' autocomplete='tel' placeholder='+256 7XX XXX XXX' required></label>" +
      "<label>Password<input name='password' type='password' autocomplete='new-password' minlength='8' required></label>" +
      "<p class='err' id='err' role='alert'></p><button class='btn wide'>Create account</button></form>" +
      "<p class='note'>Placeholder: mobile numbers are not verified by SMS yet. Already have an account? <a href='#/signin'>Sign in</a></p></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#err"), b = e.target.querySelector("button");
      b.disabled = true; err.textContent = "";
      S.db.auth.signUp({ email: f.email, password: f.password, options: { data: { name: f.name, country: "UG", mobile: f.mobile, as: f.as === "seller" ? "seller" : "buyer" }, emailRedirectTo: location.origin + location.pathname + "?next=" + nextFor(f.as) } })
        .then(function (r) {
          if (r.error) throw r.error;
          if (r.data.user && r.data.user.identities && !r.data.user.identities.length) throw new Error("exists");
          if (!r.data.session) {
            b.disabled = false;
            S.popup("Check your email", "<p>We sent a link to <strong>" + S.esc(f.email) + "</strong>. Open it to confirm your email; it signs you in" + (f.as === "seller" ? (selling ? " and opens the form to list your car" : " and takes you to My cars") : "") + ".</p><p class='note'>Nothing after a few minutes? Check spam.</p>", [
              { text: "Resend email", click: function (close, el) {
                el.disabled = true;
                S.db.auth.resend({ type: "signup", email: f.email, options: { emailRedirectTo: location.origin + location.pathname + "?next=" + nextFor(f.as) } })
                  .then(function (x) { if (x.error) throw x.error; el.textContent = "Sent again"; })
                  .catch(function (e3) { el.disabled = false; S.toast(S.friendly(e3), true); });
              } },
              { text: "OK", primary: true, click: function (close) { close(); S.go("#/signin"); } }]);
            return;
          }
          S.mode(f.as === "seller" ? "seller" : "buyer"); S.toast("Welcome to Saaz."); S.go(S.after || (f.as === "seller" ? "#/my/cars" : "#/browse"));
        }).catch(function (e2) {
          var m = S.friendly(e2);
          // Same answer whether or not the email is taken, so the form can't be used to find out who has an account
          err.innerHTML = /exists|already registered/i.test(m) ? "We couldn't create an account with these details. If you already have one, <a href='#/signin'>sign in</a> or <a href='#/forgot'>reset your password</a>." : S.esc(m);
          b.disabled = false;
        });
    };
  });

  S.route("/forgot", function (v) {
    v.innerHTML = "<div class='narrow'><h1>Reset your password</h1><form id='f' class='stack'><label>Email<input name='email' type='email' required></label>" +
      "<button class='btn wide'>Send reset link</button></form><p class='note'>The link in the email works once. <a href='#/signin'>Back to sign in</a></p></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), b = e.target.querySelector("button"); b.disabled = true;
      S.db.auth.resetPasswordForEmail(f.email, { redirectTo: location.origin + location.pathname + "#/reset" }).then(function (r) {
        b.disabled = false;
        if (r && r.error && /rate|too many|seconds/i.test(r.error.message || "")) { S.toast(S.friendly(r.error), true); return; }
        S.popup("Check your email", "<p>If <strong>" + S.esc(f.email) + "</strong> has a Saaz account, a reset link is on its way.</p><p class='note'>Nothing after a few minutes? Check spam.</p>",
          [{ text: "OK", primary: true, click: function (close) { close(); S.go("#/signin"); } }]);
      });
    };
  });
  // Email links land here (see EMAIL_CODE). One tap uses the code; invites and resets set the password in the same step.
  S.route("/confirm", function (v) {
    var code = EMAIL_CODE, ty = code && code.type;
    var used = function (msg) {
      var next = { invite: "Ask your garage owner, or Saaz, to send a new invite from the Team page.", recovery: "<a href='#/forgot'>Get a new reset link</a>.",
        signup: "<a href='#/signin'>Sign in</a>: if your email isn't confirmed yet, Saaz offers to send a new link." }[ty] || "<a href='#/signin'>Sign in</a>.";
      v.innerHTML = "<div class='narrow'><h1>This link can't be used</h1><p>" + S.esc(msg || "Links from Saaz emails work once, and only until they expire.") + "</p><p>" + next + "</p></div>";
    };
    if (!code) return used();
    var pw = ty === "invite" || ty === "recovery";
    var title = { invite: "Set up your garage account", recovery: "Set a new password", signup: "Confirm your email", email_change: "Confirm your new email", magiclink: "Sign in to Saaz" }[ty] || "Continue";
    v.innerHTML = "<div class='narrow'><h1>" + title + "</h1>" +
      (ty === "invite" ? "<p class='lead'>Choose a password. You'll use it with your email to sign in as Garage team.</p>" : "") +
      "<form id='f' class='stack'>" + (pw ? "<label>New password (8 characters or more)<input name='password' type='password' minlength='8' required autocomplete='new-password'></label>" +
        "<label>Type it again<input name='password2' type='password' minlength='8' required autocomplete='new-password'></label>" : "") +
      "<p class='err' id='err' role='alert'></p><button class='btn wide'>" + ({ invite: "Save password and open my dashboard", recovery: "Save new password", signup: "Confirm my email", email_change: "Confirm new email" }[ty] || "Continue") + "</button></form></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#err"), b = e.target.querySelector("button");
      if (pw && f.password !== f.password2) { err.textContent = "The two passwords don't match."; return; }
      b.disabled = true; err.textContent = "";
      S.db.auth.verifyOtp({ token_hash: code.token_hash, type: ty }).then(function (r) {
        if (r.error) { EMAIL_CODE = null; used(/expired|invalid/i.test(r.error.message) ? "This link has expired or was already used." : S.friendly(r.error)); throw null; }
        EMAIL_CODE = null;
        return pw ? S.db.auth.updateUser({ password: f.password }).then(function (u) { if (u.error) throw u.error; }) : null;
      }).then(function () {
        // Setting a password from an invite (or set-password) email = the garage invite is Accepted. Certification is separate.
        return pw ? S.rpc("accept_garage_invite").catch(function () {}) : null;
      }).then(function () { return S.loadRoles(); }).then(function (roles) {
        var meta = ((S.state.session || {}).user || {}).user_metadata || {};
        if (roles && roles.garage && (ty === "invite" || ty === "recovery")) {
          return S.rpc("garage_sign_in").then(function (g) {
            if (g && g.ok === false) { S.toast(g.message, true); S.go("#/browse"); return; }
            S.mode("garage"); S.toast(ty === "invite" ? "Password saved. Welcome to " + (roles.garage.name || "your garage") + "." : "Password saved."); S.go("#/garage");
          });
        }
        if (ty === "signup") { S.mode(meta.as === "seller" ? "seller" : "buyer"); S.toast("Email confirmed. Welcome to Saaz."); return S.go(NEXT === "sellnew" ? "#/sell/new" : meta.as === "seller" ? "#/my/cars" : "#/browse"); }
        if (ty === "email_change") { S.toast("New email confirmed."); return S.go("#/account"); }
        S.toast(pw ? "Password saved." : "Signed in."); S.go(S.home());
      }).catch(function (x) { if (x) { err.textContent = S.friendly(x); b.disabled = false; } });
    };
  });
  S.route("/reset", function (v, m, q) {
    var first = q.get("first") === "1";
    if (!S.signedIn()) { v.innerHTML = "<div class='narrow'><h1>This link has expired</h1><p>Links from Saaz emails work once. <a href='#/forgot'>Get a new link</a>.</p></div>"; return; }
    v.innerHTML = "<div class='narrow'><h1>" + (first ? "Set your password" : "Set a new password") + "</h1>" +
      (first ? "<p class='lead'>Welcome to Saaz, " + S.esc(S.me().email) + ". Choose a password to finish setting up your account.</p>" : "") +
      "<form id='f' class='stack'><label>New password (8 characters or more)<input name='password' type='password' minlength='8' required autocomplete='new-password'></label>" +
      "<p class='err' id='err'></p><button class='btn wide'>Save password</button></form></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target);
      S.db.auth.updateUser({ password: f.password }).then(function (r) {
        if (r.error) throw r.error; S.toast("Password saved."); S.rpc("accept_garage_invite").catch(function () {});
        S.go(first && S.state.roles && S.state.roles.garage ? (S.mode("garage"), "#/garage") : S.home());
      })
        .catch(function (e2) { S.$("#err").textContent = S.friendly(e2) + " Open the link from your email again."; });
    };
  });

  S.route("/account", function (v) {
    var p = S.me();
    v.innerHTML = "<div class='narrow'><h1>Your account</h1><section><h2>Details</h2><form id='f' class='stack'>" +
      "<label>Full name<input name='name' value='" + S.esc(p.name) + "' required minlength='2'></label>" +
      "<label>Mobile number<input name='mobile' type='tel' value='" + S.esc(p.mobile) + "' placeholder='+256 7XX XXX XXX'></label>" +
      "<p class='note'>" + (p.trusted ? "Trusted seller. " : "") + "Saaz operates in Uganda.</p><button class='btn'>Save details</button></form></section>" +
      "<section><h2>Password</h2><form id='pw' class='stack'><label>New password (8 characters or more)<input name='password' type='password' minlength='8' required autocomplete='new-password'></label>" +
      "<label>Type it again<input name='again' type='password' minlength='8' required autocomplete='new-password'></label><p class='err' id='pwerr' role='alert'></p><button class='btn'>Change password</button></form></section>" +
      "<section><h2>Email</h2><p>Now: <b>" + S.esc(p.email) + "</b></p><form id='em' class='stack'><label>New email<input name='email' type='email' required autocomplete='email'></label>" +
      "<p class='err' id='emerr' role='alert'></p><button class='btn'>Change email</button><p class='note'>Saaz sends a confirmation link. The change only happens once it is opened.</p></form></section></div>";
    S.$("#f").onsubmit = function (e) { e.preventDefault(); var f = S.form(e.target); S.act(e.target.querySelector("button"), function () { return S.rpc("update_profile", { p_name: f.name, p_country: "UG", p_mobile: f.mobile }); }, "Saved."); };
    S.$("#pw").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#pwerr"); err.textContent = "";
      if (f.password !== f.again) { err.textContent = "The two passwords don't match."; return; }
      S.db.auth.updateUser({ password: f.password }).then(function (r) { if (r.error) throw r.error; e.target.reset(); S.toast("Password changed."); })
        .catch(function (e2) { err.textContent = /reauthentication|recent/i.test(e2.message || "") ? "For safety, sign out and sign in again, then change your password." : S.friendly(e2); });
    };
    S.$("#em").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#emerr"); err.textContent = "";
      S.db.auth.updateUser({ email: f.email }, { emailRedirectTo: location.origin + location.pathname + "#/account" }).then(function (r) { if (r.error) throw r.error; e.target.reset(); S.toast("Check " + f.email + " for the confirmation link."); })
        .catch(function (e2) { err.textContent = S.friendly(e2); });
    };
  }, "user");

  S.route("/inbox", function (v) {
    return S.q(S.db.from("notifications").select("*").eq("user_id", S.me().id).order("created_at", { ascending: false }).limit(100)).then(function (rows) {
      v.innerHTML = "<h1>Inbox</h1><p class='note'>Placeholder: email and SMS aren't connected yet, so every notice lands here.</p>" +
        (rows.length ? "<ul class='list'>" + rows.map(function (n) {
          return "<li class='" + (n.read ? "" : "unread") + "'><a href='" + S.esc(S.safeHref(n.link, "#/inbox")) + "'>" + (n.read ? "<span>" + S.esc(n.body) + "</span>" : "<b>" + S.esc(n.body) + "</b><span class='new'>New</span>") + "<small>" + S.when(n.created_at) + " · " + S.esc(n.channels.join(", ")) + "</small></a></li>";
        }).join("") + "</ul>" : "<div class='empty'><b>No notices yet</b></div>");
      var unread = rows.filter(function (n) { return !n.read; }).map(function (n) { return n.id; });
      if (unread.length) S.rpc("mark_read", { p_ids: unread }).catch(function () {});
    });
  }, "user");

  // The site root is the home page for buyers and visitors; a seller, garage or admin goes to their own area's start page
  S.route("/", function (v, m, q) {
    var h = S.signedIn() ? S.home() : "#/browse";
    if (h !== "#/browse" && h !== "#/admin") return S.go(h);
    return S.homePage(v, q);
  });

  // Every field that must be filled in gets a red asterisk after its label
  S.markRequired = function (root) {
    S.$$("label", root || document).forEach(function (l) {
      if (l.querySelector(".req") || !l.querySelector("input[required],select[required],textarea[required]")) return;
      var star = document.createElement("span"); star.className = "req"; star.setAttribute("aria-hidden", "true"); star.textContent = " *";
      var field = l.querySelector("input,select,textarea");
      if (l.classList.contains("inline")) { l.appendChild(star); return; }
      // keep the label words and the * on one line: wrap everything before the field
      var words = document.createElement("span"); words.className = "lbl";
      while (l.firstChild && l.firstChild !== field && !(l.firstChild.contains && l.firstChild.contains(field))) words.appendChild(l.firstChild);
      words.appendChild(star); l.insertBefore(words, l.firstChild);
    });
  };
  if (window.MutationObserver) document.addEventListener("DOMContentLoaded", function () {
    new MutationObserver(function () { S.markRequired(S.$("#app")); }).observe(S.$("#app"), { childList: true, subtree: true });
  });

  window.addEventListener("hashchange", S.render);
  document.addEventListener("DOMContentLoaded", function () {
    if (S.db) S.db.auth.onAuthStateChange(function (ev, session) {
      if (ev === "PASSWORD_RECOVERY") S.go("#/reset");
      // Session ended without the Sign out button (expired, revoked, or signed out in another tab): same safe landing
      if (ev === "SIGNED_OUT" && !S._signingOut && S._wasSignedIn) S.signOut("Your session ended. Sign in again to continue.");
      if (session) S._wasSignedIn = true;
    });
    try { var bye = sessionStorage.getItem("saaz-bye"); if (bye) { sessionStorage.removeItem("saaz-bye"); setTimeout(function () { S.toast(bye); }, 400); } } catch (e) {}
    S.render();
  });
})();
