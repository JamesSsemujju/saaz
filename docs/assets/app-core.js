/* app-core.js: the Saaz marketplace app at /app/. Client, router, helpers, accounts, header.
   Every change goes through a database function (supabase/marketplace_*.sql). The page never decides who may do what. */
(function () {
  var C = window.SAAZ || {};
  var S = window.Saaz = { routes: [], state: { session: null, roles: null } };
  var configured = C.supabaseUrl && C.supabaseAnonKey && window.supabase;
  S.db = configured ? window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey, { auth: { persistSession: true, autoRefreshToken: true } }) : null;
  S.site = C.base || "/";

  // ---------- helpers ----------
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  S.esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  S.money = function (cur, n) { return n == null ? "" : (cur || "UGX") + " " + Number(n).toLocaleString("en-US"); };
  S.day = function (iso) { if (!iso) return ""; var d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso); return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear(); };
  S.when = function (iso) { if (!iso) return ""; var d = new Date(iso); return S.day(iso) + ", " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
  S.km = function (n) { return n == null ? "" : Number(n).toLocaleString("en-US") + " km"; };
  S.label = function (s) { return String(s || "").replace(/_/g, " ").replace(/^./, function (c) { return c.toUpperCase(); }); };
  S.name = function (l) { return l.year + " " + l.make + " " + l.model; };
  S.photo = function (p) { return p ? C.supabaseUrl + "/storage/v1/object/public/car-photos/" + p : ""; };
  S.chip = function (status) { return "<span class='chip s-" + S.esc(status) + "'>" + S.esc(S.label(status)) + "</span>"; };
  S.$ = function (sel, root) { return (root || document).querySelector(sel); };
  S.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  S.form = function (f) { var o = {}; new FormData(f).forEach(function (v, k) { o[k] = typeof v === "string" ? v.trim() : v; }); return o; };
  S.device = function () {
    try { var d = localStorage.getItem("saaz-device"); if (!d) { d = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("saaz-device", d); } return d; }
    catch (e) { return null; }
  };
  S.REGIONS = { UG: ["Kampala", "Wakiso", "Entebbe", "Mukono", "Jinja", "Mbarara", "Gulu"], KE: ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"] };
  S.COUNTRY = { UG: "Uganda", KE: "Kenya" };

  // Database errors come back as plain sentences from the functions. Show them as they are.
  S.friendly = function (e) {
    var m = (e && (e.message || e.msg || e.error_description)) || String(e || "Something went wrong.");
    if (/Failed to fetch|NetworkError|network/i.test(m)) return "Couldn't reach Saaz. Check your connection and try again.";
    if (/Invalid login credentials/i.test(m)) return "Wrong email or password.";
    if (/Email not confirmed/i.test(m)) return "Confirm your email first: open the link Saaz sent you.";
    if (/JWT|token is expired/i.test(m)) return "Your session ended. Sign in again.";
    if (/violates row-level security/i.test(m)) return "You don't have access to do that.";
    return m;
  };
  S.rpc = function (fn, args) {
    return S.db.rpc(fn, args || {}).then(function (r) { if (r.error) throw r.error; return r.data; });
  };
  S.q = function (promise) { return promise.then(function (r) { if (r.error) throw r.error; return r.data; }); };
  S.toast = function (msg, bad) {
    var t = S.$("#toast"); t.textContent = msg; t.className = "toast show" + (bad ? " bad" : "");
    clearTimeout(S._t); S._t = setTimeout(function () { t.className = "toast"; }, 4200);
  };
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
  S.home = function () { return { seller: "#/my/cars", garage: "#/garage", admin: "#/admin" }[S.mode()] || "#/browse"; };
  S.signedIn = function () { return !!(S.state.roles && S.state.roles.signed_in); };
  S.isAdmin = function () { return !!(S.state.roles && S.state.roles.admin); };
  S.me = function () { return (S.state.roles && S.state.roles.profile) || {}; };

  // ---------- router ----------
  S.route = function (pattern, handler, need) { S.routes.push({ re: new RegExp("^" + pattern + "$"), handler: handler, need: need }); };
  S.go = function (hash) { if (location.hash === hash) S.render(); else location.hash = hash; };

  function header() {
    var r = S.state.roles, mode = S.mode(), modes = [];
    if (r && r.signed_in) {
      modes.push(["buyer", "Buyer"], ["seller", "Seller"]);
      if (r.garage) modes.push(["garage", "Garage team"]);
      if (r.admin) modes.push(["admin", "Admin"]);
    }
    var links = "<a href='#/browse'>Browse</a><a href='#/selling'>What's selling</a><a href='#/verify'>Verify</a>";
    var right = r && r.signed_in
      ? "<a href='" + S.home() + "' class='dash'>Dashboard</a><a href='#/inbox' class='inbox' aria-label='Inbox'>Inbox<b id='unread' hidden></b></a>" +
        "<select id='modesw' aria-label='Switch role'>" + modes.map(function (m) { return "<option value='" + m[0] + "'" + (m[0] === mode ? " selected" : "") + ">" + m[1] + "</option>"; }).join("") + "</select>" +
        "<button type='button' class='link' id='signout'>Sign out</button>"
      : "<a href='#/signin' class='dash'>Sign in</a>";
    return "<header class='apphead'><div class='wrap'><a class='logo' href='" + S.site + "'><i aria-hidden='true'>S</i>SAAZ</a>" +
      "<nav class='appnav'>" + links + "</nav><div class='appright'>" + right + "</div></div></header>";
  }
  function wireHeader() {
    var sw = S.$("#modesw"); if (sw) sw.onchange = function () { S.mode(sw.value); S.go(S.home()); };
    var so = S.$("#signout"); if (so) so.onclick = function () { S.db.auth.signOut().then(function () { S.state.roles = null; S.mode("buyer"); S.go("#/browse"); }); };
    if (S.signedIn()) S.q(S.db.from("notifications").select("id", { count: "exact", head: false }).eq("read", false).eq("user_id", S.me().id)).then(function (rows) {
      var b = S.$("#unread"); if (b && rows.length) { b.hidden = false; b.textContent = rows.length; }
    }).catch(function () {});
  }

  S.render = function () {
    var hash = location.hash.replace(/^#/, "") || "/";
    var path = hash.split("?")[0], query = new URLSearchParams(hash.split("?")[1] || "");
    var root = S.$("#app");
    if (!S.db) { root.innerHTML = "<div class='wrap pad'><div class='empty'><b>Saaz isn't connected yet</b><span>The database settings are missing from this build.</span></div></div>"; return; }
    S.loadRoles().then(function () {
      if (S.signedIn()) S.rpc("tick").catch(function () {}); // garage time-outs and review expiry
      var match = null, m;
      for (var i = 0; i < S.routes.length; i++) { m = S.routes[i].re.exec(path); if (m) { match = S.routes[i]; break; } }
      root.innerHTML = header() + "<main id='view' class='wrap pad'><p class='loading'>Loading…</p></main>";
      wireHeader();
      var view = S.$("#view");
      if (!match) { view.innerHTML = "<div class='empty'><b>Page not found</b><span><a href='#/browse'>Browse cars</a></span></div>"; return; }
      if (match.need && !S.signedIn()) { S.after = location.hash; S.go("#/signin"); return; }
      if (match.need === "admin" && !S.isAdmin()) { view.innerHTML = "<div class='empty'><b>Admins only</b></div>"; return; }
      window.scrollTo(0, 0);
      Promise.resolve(match.handler(view, m.slice(1), query)).catch(function (e) {
        view.innerHTML = "<div class='empty'><b>Couldn't load this page</b><span>" + S.esc(S.friendly(e)) + "</span></div>";
      });
    });
  };

  // ---------- sign in, sign up, passwords ----------
  var ROLES = [["buyer", "Buyer"], ["seller", "Seller"], ["garage", "Garage team"], ["admin", "Admin"]];
  S.route("/signin", function (v) {
    v.innerHTML = "<div class='narrow'><h1>Sign in</h1>" +
      "<form id='f' class='stack'><fieldset class='seg'><legend>Sign in as</legend>" + ROLES.map(function (r, i) {
        return "<label><input type='radio' name='as' value='" + r[0] + "'" + (r[0] === S.mode() || (!i && !S.mode()) ? " checked" : "") + "><span>" + r[1] + "</span></label>";
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
        if (f.as === "admin" && !roles.admin) { S.mode("buyer"); throw new Error("This account is not an admin."); }
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
    v.innerHTML = "<div class='narrow'><h1>Create your Saaz account</h1><p class='lead'>One account to buy and sell.</p>" +
      "<form id='f' class='stack'><label>Full name<input name='name' autocomplete='name' required minlength='2'></label>" +
      "<label>Email<input name='email' type='email' autocomplete='email' required></label>" +
      "<label>Country<select name='country' required><option value='UG'>Uganda</option><option value='KE'>Kenya</option></select></label>" +
      "<label>Mobile number<input name='mobile' type='tel' autocomplete='tel' placeholder='+256 7XX XXX XXX' required></label>" +
      "<label>Password<input name='password' type='password' autocomplete='new-password' minlength='8' required></label>" +
      "<p class='err' id='err' role='alert'></p><button class='btn wide'>Create account</button></form>" +
      "<p class='note'>Placeholder: mobile numbers are not verified by SMS yet. Already have an account? <a href='#/signin'>Sign in</a></p></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target), err = S.$("#err"), b = e.target.querySelector("button");
      b.disabled = true; err.textContent = "";
      S.db.auth.signUp({ email: f.email, password: f.password, options: { data: { name: f.name, country: f.country, mobile: f.mobile }, emailRedirectTo: location.origin + location.pathname + "#/signin" } })
        .then(function (r) {
          if (r.error) throw r.error;
          if (r.data.user && r.data.user.identities && !r.data.user.identities.length) throw new Error("exists");
          if (!r.data.session) { v.innerHTML = "<div class='narrow'><h1>Check your email</h1><p>Saaz sent a link to " + S.esc(f.email) + ". Open it to finish creating your account, then sign in.</p></div>"; return; }
          S.mode("buyer"); S.toast("Welcome to Saaz."); S.go(S.after || "#/browse");
        }).catch(function (e2) {
          var m = S.friendly(e2);
          err.innerHTML = /exists|already registered/i.test(m) ? "That email already has an account. <a href='#/forgot'>Forgot your password?</a>" : S.esc(m);
          b.disabled = false;
        });
    };
  });

  S.route("/forgot", function (v) {
    v.innerHTML = "<div class='narrow'><h1>Reset your password</h1><form id='f' class='stack'><label>Email<input name='email' type='email' required></label>" +
      "<button class='btn wide'>Send reset link</button></form><p class='note'>The link works for 24 hours.</p></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target);
      S.db.auth.resetPasswordForEmail(f.email, { redirectTo: location.origin + location.pathname + "#/reset" }).then(function () {
        v.innerHTML = "<div class='narrow'><h1>Check your email</h1><p>If " + S.esc(f.email) + " has a Saaz account, a reset link is on its way.</p></div>";
      });
    };
  });
  S.route("/reset", function (v) {
    v.innerHTML = "<div class='narrow'><h1>Set a new password</h1><form id='f' class='stack'><label>New password<input name='password' type='password' minlength='8' required autocomplete='new-password'></label>" +
      "<p class='err' id='err'></p><button class='btn wide'>Save password</button></form></div>";
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var f = S.form(e.target);
      S.db.auth.updateUser({ password: f.password }).then(function (r) { if (r.error) throw r.error; S.toast("Password saved."); S.go(S.home()); })
        .catch(function (e2) { S.$("#err").textContent = S.friendly(e2) + " Open the link from your email again."; });
    };
  });

  S.route("/account", function (v) {
    var p = S.me();
    v.innerHTML = "<div class='narrow'><h1>Your account</h1><form id='f' class='stack'>" +
      "<label>Full name<input name='name' value='" + S.esc(p.name) + "' required></label>" +
      "<label>Country<select name='country'><option value='UG'" + (p.country === "UG" ? " selected" : "") + ">Uganda</option><option value='KE'" + (p.country === "KE" ? " selected" : "") + ">Kenya</option></select></label>" +
      "<label>Mobile number<input name='mobile' type='tel' value='" + S.esc(p.mobile) + "'></label>" +
      "<p class='note'>Email: " + S.esc(p.email) + (p.trusted ? " · Trusted seller" : "") + "</p><button class='btn'>Save</button></form></div>";
    S.$("#f").onsubmit = function (e) { e.preventDefault(); var f = S.form(e.target); S.act(e.target.querySelector("button"), function () { return S.rpc("update_profile", { p_name: f.name, p_country: f.country, p_mobile: f.mobile }); }, "Saved."); };
  }, "user");

  S.route("/inbox", function (v) {
    return S.q(S.db.from("notifications").select("*").eq("user_id", S.me().id).order("created_at", { ascending: false }).limit(100)).then(function (rows) {
      v.innerHTML = "<h1>Inbox</h1><p class='note'>Placeholder: email and SMS aren't connected yet, so every notice lands here.</p>" +
        (rows.length ? "<ul class='list'>" + rows.map(function (n) {
          return "<li class='" + (n.read ? "" : "unread") + "'><a href='" + S.esc(n.link || "#/inbox") + "'><b>" + S.esc(n.body) + "</b><small>" + S.when(n.created_at) + " · " + S.esc(n.channels.join(", ")) + "</small></a></li>";
        }).join("") + "</ul>" : "<div class='empty'><b>No notices yet</b></div>");
      var unread = rows.filter(function (n) { return !n.read; }).map(function (n) { return n.id; });
      if (unread.length) S.rpc("mark_read", { p_ids: unread }).catch(function () {});
    });
  }, "user");

  S.route("/", function () { S.go(S.signedIn() ? S.home() : "#/browse"); });

  window.addEventListener("hashchange", S.render);
  document.addEventListener("DOMContentLoaded", function () {
    if (S.db) S.db.auth.onAuthStateChange(function (ev) { if (ev === "PASSWORD_RECOVERY") S.go("#/reset"); });
    S.render();
  });
})();
