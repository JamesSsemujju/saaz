/* app-promotions.js: Promotions (part 23). First type: prize draw.
   Public: #/promotions/<slug> (and #/promotions/current, which /giveaway/ opens). Signed-in people enter; one entry per account.
   Admin (full admins only): #/admin/promotions and #/admin/promotion/<id>. The database decides everything; this page only shows it. */
(function () {
  var S = window.Saaz, esc = S.esc;

  // datetime-local fields are East Africa Time, whatever the device says
  function toLocal(iso) {
    if (!iso) return "";
    var p = {}; new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Kampala", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date(iso)).forEach(function (x) { p[x.type] = x.value; });
    return p.year + "-" + p.month + "-" + p.day + "T" + p.hour + ":" + p.minute;
  }
  function fromLocal(v) { return v ? v + ":00+03:00" : ""; }
  function dayEAT(iso) { return iso ? toLocal(iso).slice(0, 10) : ""; }

  // ---------- public page ----------
  S.route("/promotions/([a-z0-9-]{3,40})", function (v, m, q) {
    return S.rpc("promotion_public", { p_slug: m[0] }).then(function (r) {
      if (!r || !r.running) {
        v.innerHTML = "<div class='narrow' data-ref='promotion-page'><div class='empty'><b>No promotion running right now</b><span><a href='#/browse'>Browse inspected cars</a></span></div></div>";
        return;
      }
      var p = r.promotion, me = r.me, mine = r.my_entry, src = (q.get("src") || "").toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 30);
      var contact = "Saaz contacts winners only through your Saaz inbox" + (p.contact_phone ? " and " + esc(p.contact_phone) : "") + ". Saaz never asks for money to release a prize.";
      var head = "<div class='pagehead'><h1>" + esc(p.title) + "</h1></div>" +
        (p.prize ? "<p class='lead'>Prize: " + esc(p.prize) + "</p>" : "") +
        (p.summary ? "<p>" + esc(p.summary) + "</p>" : "") +
        "<p class='note'>" + (p.open ? "Entries close " + S.when(p.closes_at) + ". One entry per person." : "Entries closed " + S.when(p.closes_at) + ".") +
        (p.permit_no ? " Permit " + esc(p.permit_no) + "." : "") + "</p><p class='note'>" + contact + "</p>";
      var terms = "<details class='terms'><summary>Terms and conditions (" + esc(p.terms_version) + ")</summary><div class='termstext'>" + esc(p.terms) + "</div></details>";
      var body;
      if (mine && mine.status === "entered") body = "<div class='box good' id='promodone'><b>You're in.</b> Entered " + S.when(mine.at) + ". The draw is after entries close.</div>";
      else if (mine) body = "<div class='box warn'><b>Your entry was not accepted.</b> Contact Saaz if you think this is wrong.</div>";
      else if (!p.open) body = "<div class='empty'><b>Entries are closed</b><span><a href='#/browse'>Browse inspected cars</a></span></div>";
      else if (!S.signedIn()) body = "<section><h2>Enter</h2><p>Entry needs a Saaz account, so each person enters once.</p><div class='row'>" +
        "<a class='btn' href='#/signup' data-after='" + esc(location.hash) + "'>Create an account</a> <a class='btn text' href='#/signin' data-after='" + esc(location.hash) + "'>Sign in</a></div></section>";
      else if (me && me.saaz_team) body = "<p class='note'>Saaz team members can't enter Saaz promotions.</p>";
      else body = "<section><h2>Enter</h2><form id='pf' class='stack' data-ref='promotion-form'>" +
        "<label>Full name<input name='name' required minlength='3' maxlength='80' autocomplete='name' value='" + esc(me && me.name || "") + "'></label>" +
        "<label>Mobile number<input name='mobile' type='tel' required autocomplete='tel' placeholder='0772 123456' value='" + esc(me && me.mobile || "") + "'></label>" +
        "<label>The car you drive now<input name='current_car' required minlength='2' maxlength='80' placeholder='For example Toyota Premio 2008, or None'></label>" +
        "<label>The car you'd like next<input name='dream_car' required minlength='2' maxlength='80' placeholder='For example Toyota Harrier'></label>" +
        "<label>Promo code" + (p.needs_code ? "" : " (if you have one)") + "<input name='code' maxlength='16' autocapitalize='characters'" + (p.needs_code ? " required" : "") + "></label>" +
        terms +
        "<label class='inline'><input type='checkbox' name='terms' value='1' required> I accept the terms and conditions</label>" +
        "<label class='inline'><input type='checkbox' name='marketing_ok' value='1'> Saaz may tell me about cars and offers (optional)</label>" +
        "<label class='inline'><input type='checkbox' name='whatsapp_ok' value='1'> Saaz may message me on WhatsApp (optional)</label>" +
        "<p class='err' id='perr' role='alert'></p><button class='btn wide'>Enter the draw</button></form></section>";
      v.innerHTML = "<div class='narrow' data-ref='promotion-page'>" + head + body + (mine || !p.open || !S.signedIn() ? terms : "") + "</div>";
      var f = S.$("#pf"); if (!f) return;
      f.onsubmit = function (e) {
        e.preventDefault(); var d = S.form(f), b = f.querySelector("button"), el = S.$("#perr"); b.disabled = true; el.textContent = "";
        S.rpc("promotion_enter", { p_slug: p.slug, p: { name: d.name, mobile: d.mobile, current_car: d.current_car, dream_car: d.dream_car, code: d.code || null,
          terms_version: p.terms_version, terms: d.terms === "1", marketing_ok: d.marketing_ok === "1", whatsapp_ok: d.whatsapp_ok === "1", source: src } })
          .then(function () { S.toast("You're in."); S.render(); })
          .catch(function (e2) { el.textContent = S.friendly(e2); b.disabled = false; });
      };
    });
  });

  // ---------- admin ----------
  if (!S.adminPage) return;
  var page = S.adminPage;
  function table(head, rows) {
    return "<div class='tablewrap'><table class='tbl'><thead><tr>" + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr></thead><tbody>" +
      (rows.length ? rows.join("") : "<tr><td colspan='" + head.length + "' class='note'>Nothing here.</td></tr>") + "</tbody></table></div>";
  }
  var STATUS_WORD = { draft: "Draft", open: "Open", closed: "Closed", drawn: "Drawn", cancelled: "Cancelled" };
  function chip(st, open) { return "<span class='chip s-" + (open ? "active" : st === "cancelled" ? "suspended" : "draft") + "'>" + esc(STATUS_WORD[st] || st) + (st === "open" && !open ? " (not taking entries)" : "") + "</span>"; }

  S.route("/admin/promotions", function (v) {
    return S.rpc("admin_promotions").then(function (b) {
      var on = b.enabled;
      page(v, "promotions", "<div class='pagehead'><h2>Promotions</h2><span class='chip s-" + (on ? "active" : "suspended") + "'>" + (on ? "On" : "Off") + "</span></div>" +
        "<p class='lead'>Prize draws now; other kinds later. A promotion takes entries only when this switch is on, it is open, and today is between its dates. It can't open without a permit number and terms.</p>" +
        "<section><h2>" + (on ? "Switch off" : "Switch on") + "</h2>" +
        (on ? "<p>When off: promotion pages say nothing is running, the database refuses entries, and nothing is deleted.</p>" : "<p>Switch on only once the permit and data protection registration are in place.</p>") +
        "<form id='psw' class='inlineform'><label>Reason (kept in the history)<input name='reason' maxlength='200'" + (on ? " required minlength='10'" : "") + "></label><button class='btn" + (on ? " ghost" : "") + "'>" + (on ? "Switch off" : "Switch on") + "</button></form></section>" +
        "<section><h2>All promotions</h2>" + table(["Promotion", "Status", "Dates (EAT)", "Entries", "Flagged"], b.promotions.map(function (p) {
          return "<tr><td><a href='#/admin/promotion/" + p.id + "'>" + esc(p.title) + "</a><small> " + esc(p.slug) + "</small></td><td>" + chip(p.status, p.open) + "</td><td>" +
            (p.opens_at ? S.day(p.opens_at) + " to " + S.day(p.closes_at) : "<small>not set</small>") + "</td><td>" + p.entries + (p.purged_at ? " <small>details cleared</small>" : "") + "</td><td>" + (p.flagged ? "<b class='bad'>" + p.flagged + "</b>" : "0") + "</td></tr>";
        })) + "</section>" +
        "<section><h2>New prize draw</h2><form id='pnew' class='inlineform'><label>Title<input name='title' required minlength='3' maxlength='80' placeholder='Win a car'></label>" +
        "<label>Web name<input name='slug' required pattern='[a-z0-9][a-z0-9-]{2,39}' placeholder='win-a-car'></label><button class='btn small'>Create draft</button></form></section>" +
        "<section><h2>History of the switch</h2>" + table(["When", "Change", "By", "Reason"], b.toggles.map(function (t) {
          return "<tr><td>" + S.when(t.at) + "</td><td>" + (t.enabled ? "On" : "Off") + "</td><td>" + esc(t.by || "") + "</td><td>" + esc(t.reason || "") + "</td></tr>"; })) + "</section>");
      S.$("#psw").onsubmit = function (e) { e.preventDefault(); S.act(e.target.querySelector("button"), function () { return S.rpc("admin_promotion_switch", { p_on: !on, p_reason: S.form(e.target).reason || null }); }, on ? "Promotions switched off." : "Promotions switched on."); };
      S.$("#pnew").onsubmit = function (e) {
        e.preventDefault(); var f = S.form(e.target), b = e.target.querySelector("button"); b.disabled = true;
        S.rpc("admin_promotion_save", { p_id: null, p: { title: f.title, slug: f.slug } }).then(function (id) { S.toast("Draft created."); S.go("#/admin/promotion/" + id); })
          .catch(function (e2) { S.toast(S.friendly(e2), true); b.disabled = false; });
      };
    });
  }, "admin");

  function csv(p, r) {
    var cell = function (x) { x = x == null ? "" : String(x); return /[",\r\n]/.test(x) || /^[=+\-@]/.test(x) ? "\"" + (/^[=+\-@]/.test(x) ? "'" : "") + x.replace(/"/g, "\"\"") + "\"" : x; };
    var cols = [["at", "Entered (EAT)"], ["name", "Name"], ["mobile", "Mobile"], ["email", "Email"], ["current_car", "Current car"], ["dream_car", "Next car"], ["source", "Source"],
      ["code", "Code"], ["marketing_ok", "Marketing OK"], ["whatsapp_ok", "WhatsApp OK"], ["status", "Status"], ["status_reason", "Status reason"], ["terms_version", "T&C version"]];
    var lines = [["Saaz promotion: " + p.title, "Entries " + dayEAT(p.opens_at) + " to " + dayEAT(p.closes_at) + " (East Africa Time)", "Exported " + new Date().toISOString(), r.total + " entries"].map(cell).join(",")];
    lines.push(cols.map(function (c) { return cell(c[1]); }).join(","));
    r.rows.forEach(function (x) { lines.push(cols.map(function (c) { return cell(c[0] === "at" ? S.when(x.at) : x[c[0]]); }).join(",")); });
    var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
    a.download = "Promotions_" + p.slug + "_Entries_" + dayEAT(p.opens_at) + "_to_" + dayEAT(p.closes_at) + ".csv"; document.body.appendChild(a); a.click(); a.remove();
  }

  S.route("/admin/promotion/([0-9a-f-]{36})", function (v, m, q) {
    var id = m[0], args = { p_id: id, p_q: q.get("q") || null, p_status: q.get("status") || null, p_source: q.get("source") || null, p_page: +(q.get("page") || 1), p_size: 50, p_export: false };
    return Promise.all([S.rpc("admin_promotion", args), S.rpc("admin_promotion_report", { p_id: id })]).then(function (x) {
      var d = x[0], rp = x[1], p = d.promotion, draft = p.status === "draft", open = p.status === "open", editable = draft || open;
      var link = function (ch) { return location.origin + location.pathname + "#/promotions/" + p.slug + (ch ? "?src=" + ch : ""); };
      var fld = function (name, label, val, extra, lock) { return "<label>" + label + "<input name='" + name + "' value='" + esc(val == null ? "" : val) + "' " + (extra || "") + (lock ? " disabled" : "") + "></label>"; };
      var details = "<section><h2>Details</h2><form id='pd' class='stack'>" +
        fld("title", "Title", p.title, "required minlength='3' maxlength='80'", !draft) + fld("slug", "Web name", p.slug, "required pattern='[a-z0-9][a-z0-9-]{2,39}'", !draft) +
        fld("prize", "Prize", p.prize, "maxlength='200'", !draft) +
        "<label>Summary<textarea name='summary' rows='2' maxlength='600'" + (editable ? "" : " disabled") + ">" + esc(p.summary) + "</textarea></label>" +
        fld("opens_at", "Opens (EAT)", toLocal(p.opens_at), "type='datetime-local'", !draft) + fld("closes_at", "Closes (EAT)", toLocal(p.closes_at), "type='datetime-local'", !editable) +
        fld("winners", "Winners", p.winners, "type='number' min='1' max='100'", !draft) + fld("reserves", "Reserves", p.reserves, "type='number' min='0' max='20'", !draft) +
        fld("permit_no", "Permit number (from the regulator)", p.permit_no, "maxlength='60' placeholder='Not issued yet'", !draft) +
        fld("terms_version", "Terms version", p.terms_version, "maxlength='20' placeholder='v1'", !draft) +
        "<label>Terms and conditions<textarea name='terms' rows='8' maxlength='20000'" + (draft ? "" : " disabled") + ">" + esc(p.terms) + "</textarea></label>" +
        "<label class='inline'><input type='checkbox' name='needs_code' value='1'" + (p.needs_code ? " checked" : "") + (draft ? "" : " disabled") + "> Only people with a promo code can enter</label>" +
        fld("retention_days", "Keep personal details for (days after closing)", p.retention_days, "type='number' min='30' max='1095'", !draft) +
        (editable ? "<button class='btn'>Save details</button>" + (open ? "<p class='note'>Open: only the summary and a later closing time can change.</p>" : "") : "") + "</form></section>";
      var acts = draft ? "<button class='btn' id='popen'>Open for entries</button> <button class='btn text' data-to='cancelled'>Cancel</button>"
        : open ? "<button class='btn ghost' data-to='closed'>Close entries now</button> <button class='btn text' data-to='cancelled'>Cancel</button>" : "";
      var linksSec = "<section><h2>Tracked links</h2><p class='note'>One link per channel shows where entries came from. Without a source, entries count as direct.</p>" +
        table(["Channel", "Link", "Entries"], [{ channel: "", label: "Direct", entries: (rp.by_source.filter(function (s) { return s.source === "direct"; })[0] || { n: 0 }).n }].concat(d.links).map(function (l) {
          return "<tr><td>" + esc(l.label || l.channel) + (l.channel ? " <small>" + esc(l.channel) + "</small>" : "") + "</td><td><code>" + esc(link(l.channel)) + "</code></td><td>" + (l.entries || 0) + "</td></tr>"; })) +
        (editable ? "<form id='plink' class='inlineform'><label>Channel<input name='channel' required pattern='[a-z0-9][a-z0-9-]{1,29}' placeholder='whatsapp'></label><label>Label<input name='label' maxlength='80' placeholder='WhatsApp status'></label><button class='btn small'>Add link</button></form>" : "") + "</section>";
      var codesSec = "<section><h2>Promo codes</h2>" + table(["Code", "Given to", "Used", "Limit", "Active", ""], d.codes.map(function (c) {
          return "<tr><td><code>" + esc(c.code) + "</code></td><td>" + esc(c.label) + "</td><td>" + c.uses + "</td><td>" + (c.max_uses || "No limit") + "</td><td>" + (c.active ? "Yes" : "No") + "</td><td>" +
            (editable ? "<button class='btn small ghost' data-code='" + esc(c.code) + "' data-label='" + esc(c.label) + "' data-max='" + (c.max_uses || "") + "' data-active='" + (c.active ? "0" : "1") + "'>" + (c.active ? "Turn off" : "Turn on") + "</button>" : "") + "</td></tr>"; })) +
        (editable ? "<form id='pcode' class='inlineform'><label>Code<input name='code' required pattern='[A-Za-z0-9]{4,16}' placeholder='KAMPALA1'></label><label>Given to<input name='label' maxlength='80' placeholder='Kampala Motors'></label><label>Limit<input name='max' type='number' min='1' placeholder='No limit'></label><button class='btn small'>Add code</button></form>" : "") + "</section>";
      var fig = function (n, l) { return "<div><b>" + n + "</b><span>" + l + "</span></div>"; };
      var reportSec = "<section><h2>Report</h2><div class='stats'>" + fig(rp.total, "entries") + fig(rp.valid, "valid") + fig(rp.flagged, "flagged") + fig(rp.invalid, "invalid") +
        fig(rp.marketing_ok, "agreed to marketing") + fig(rp.whatsapp_ok, "agreed to WhatsApp") + fig(rp.listed_after, "listed a car after entering") + fig(rp.offered_after, "made an offer after entering") + "</div>" +
        (rp.by_day.length > 1 ? S.bars(rp.by_day.map(function (x) { return { label: x.day, value: x.n, short: x.day.slice(8) }; })) : rp.by_day.length ? "<p class='note'>All " + rp.by_day[0].n + " entries came on " + S.day(rp.by_day[0].day) + ".</p>" : "") +
        "<div class='rgrid'>" + table(["Source", "Entries"], rp.by_source.map(function (s) { return "<tr><td>" + esc(s.source) + "</td><td>" + s.n + "</td></tr>"; })) +
        table(["Next car wanted", "Entries"], rp.top_dream_cars.map(function (s) { return "<tr><td>" + esc(s.car) + "</td><td>" + s.n + "</td></tr>"; })) + "</div></section>";
      var pages = Math.max(1, Math.ceil(d.total / d.size)), base = "#/admin/promotion/" + id + "?", qs = function (o) { var u = new URLSearchParams(); ["q", "status", "source"].forEach(function (k) { if (q.get(k)) u.set(k, q.get(k)); }); Object.keys(o).forEach(function (k) { if (o[k]) u.set(k, o[k]); else u.delete(k); }); return base + u.toString(); };
      var entriesSec = "<section><h2>Entries <span class='count'>" + d.total + "</span></h2>" +
        "<form id='pq' class='inlineform'><label>Search<input name='q' value='" + esc(q.get("q") || "") + "' placeholder='Name, email, mobile, car'></label>" +
        "<label>Status<select name='status'><option value=''>Any</option>" + ["valid", "flagged", "invalid"].map(function (s) { return "<option" + (q.get("status") === s ? " selected" : "") + ">" + s + "</option>"; }).join("") + "</select></label>" +
        "<label>Source<select name='source'><option value=''>Any</option>" + rp.by_source.map(function (s) { return "<option" + (q.get("source") === s.source ? " selected" : "") + ">" + esc(s.source) + "</option>"; }).join("") + "</select></label>" +
        "<button class='btn small ghost'>Filter</button></form><div class='row'><button type='button' class='btn small ghost' id='pexport'>Export CSV</button><small>The export is recorded in the history.</small></div>" +
        table(["Entered", "Name", "Mobile", "Cars (now, next)", "Source", "Consent", "Status", ""], d.rows.map(function (e) {
          return "<tr><td>" + S.when(e.at) + "</td><td>" + esc(e.name) + "<small> " + esc(e.email || "") + "</small></td><td>" + esc(e.mobile || "") + "</td><td>" + esc(e.current_car) + " → " + esc(e.dream_car) + "</td><td>" + esc(e.source) + (e.code ? " <small>" + esc(e.code) + "</small>" : "") + "</td><td>" +
            [e.marketing_ok ? "Marketing" : "", e.whatsapp_ok ? "WhatsApp" : ""].filter(Boolean).join(", ") + "</td><td>" + (e.status === "valid" ? "Valid" : "<b class='" + (e.status === "flagged" ? "warn" : "bad") + "'>" + esc(S.label(e.status)) + "</b>") +
            (e.status_reason ? "<small> " + esc(e.status_reason) + "</small>" : "") + "</td><td>" + (d.draw ? "" : "<button class='btn small ghost' data-entry='" + e.id + "' data-st='" + e.status + "'>Change</button>") + "</td></tr>"; })) +
        (pages > 1 ? "<nav class='pager' aria-label='Pages'>" + Array.apply(null, Array(pages)).map(function (_, i) { return i + 1 === d.page ? "<span aria-current='page'>" + (i + 1) + "</span>" : "<a href='" + qs({ page: i + 1 }) + "'>" + (i + 1) + "</a>"; }).join("") + "</nav>" : "") + "</section>";
      var drawSec = "<section><h2>Draw</h2>" + (d.draw ?
        "<p>Drawn " + S.when(d.draw.at) + " by " + esc(d.draw.by || "") + ", witnessed by " + esc(d.draw.witness) + ", from " + d.draw.entries_in_draw + " valid entries.</p>" +
        "<p class='note'>Seed <code>" + esc(d.draw.seed) + "</code>. Anyone can check the order: sort the valid entries by md5(seed + entry id).</p>" +
        table(["Rank", "Role", "Name", "Mobile", "Step", "Note", ""], d.results.map(function (r) {
          var next = r.role !== "winner" ? [] : r.state === "pending" ? [["contacted", "Tell them (inbox notice)"], ["declined", "Declined"], ["no_reply", "No reply"], ["ineligible", "Not eligible"]]
            : r.state === "contacted" ? [["confirmed", "Confirmed"], ["declined", "Declined"], ["no_reply", "No reply"], ["ineligible", "Not eligible"]] : r.state === "confirmed" ? [["handed_over", "Handed over"], ["ineligible", "Not eligible"]] : [];
          return "<tr><td>" + r.rank + "</td><td>" + esc(S.label(r.role)) + "</td><td>" + esc(r.name) + "</td><td>" + esc(r.mobile || "") + "</td><td>" + esc(S.label(r.state)) + "</td><td>" + esc(r.note || "") + "</td><td>" +
            next.map(function (n) { return "<button class='btn small ghost' data-res='" + r.id + "' data-to='" + n[0] + "'>" + n[1] + "</button>"; }).join(" ") + "</td></tr>"; }))
        : p.status === "closed" ? "<p>Flagged entries must be cleared or marked invalid first. The draw runs once and can't be undone.</p><form id='pdraw' class='inlineform'><label>Witness<input name='witness' required minlength='3' maxlength='120' placeholder='Name and organisation'></label><button class='btn'>Run the draw</button></form>"
        : "<p class='note'>The draw runs after entries close.</p>") + "</section>";
      page(v, "promotions", "<p class='crumbs'><a href='#/admin/promotions'>Promotions</a></p><div class='pagehead'><h2>" + esc(p.title) + "</h2>" + chip(p.status, d.open) + "</div>" +
        (!d.switch_on ? "<p class='note'>The promotions switch is off, so nothing is public.</p>" : "") +
        "<p class='note'>Public page: <code>" + esc(link("")) + "</code></p>" + (acts ? "<div class='row'>" + acts + "</div>" : "") +
        (draft ? details + linksSec + codesSec + reportSec + entriesSec + drawSec : reportSec + entriesSec + drawSec + linksSec + codesSec + details));

      var pd = S.$("#pd");
      if (pd) pd.onsubmit = function (e) {
        e.preventDefault(); var f = S.form(pd), o = {};
        if (draft) o = { title: f.title, slug: f.slug, prize: f.prize, summary: f.summary, opens_at: fromLocal(f.opens_at), closes_at: fromLocal(f.closes_at), winners: +f.winners, reserves: +f.reserves,
          permit_no: f.permit_no, terms_version: f.terms_version, terms: f.terms, needs_code: f.needs_code === "1", retention_days: +f.retention_days };
        else { o.summary = f.summary; if (fromLocal(f.closes_at) && toLocal(p.closes_at) !== f.closes_at) o.closes_at = fromLocal(f.closes_at); }
        S.act(pd.querySelector("button"), function () { return S.rpc("admin_promotion_save", { p_id: id, p: o }); }, "Saved.");
      };
      var po = S.$("#popen"); if (po) po.onclick = function () { S.confirmBtn(po, function () { S.act(po, function () { return S.rpc("admin_promotion_status", { p_id: id, p_to: "open", p_reason: null }); }, "Open. It takes entries while the switch is on and between its dates."); }); };
      S.$$(".row [data-to]", v).forEach(function (b) {
        b.onclick = function () {
          if (b.dataset.to === "closed") return S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("admin_promotion_status", { p_id: id, p_to: "closed", p_reason: null }); }, "Entries closed."); });
          S.popup("Cancel this promotion", "<label>Reason (kept in the history)<textarea id='pwhy' rows='2' minlength='10'></textarea></label>", [{ text: "Back" }, { text: "Cancel promotion", primary: true, click: function (close, el) {
            el.disabled = true; S.rpc("admin_promotion_status", { p_id: id, p_to: "cancelled", p_reason: S.$("#pwhy").value }).then(function () { close(); S.toast("Cancelled."); S.render(); }).catch(function (e2) { el.disabled = false; S.toast(S.friendly(e2), true); }); } }]);
        };
      });
      var pl = S.$("#plink"); if (pl) pl.onsubmit = function (e) { e.preventDefault(); var f = S.form(pl); S.act(pl.querySelector("button"), function () { return S.rpc("admin_promotion_link", { p_promotion: id, p_channel: f.channel, p_label: f.label }); }, "Link added."); };
      var pc = S.$("#pcode"); if (pc) pc.onsubmit = function (e) { e.preventDefault(); var f = S.form(pc); S.act(pc.querySelector("button"), function () { return S.rpc("admin_promotion_code", { p_promotion: id, p_code: f.code.toUpperCase(), p_label: f.label, p_max: f.max ? +f.max : null, p_active: true }); }, "Code added."); };
      S.$$("[data-code]", v).forEach(function (b) { b.onclick = function () { S.act(b, function () { return S.rpc("admin_promotion_code", { p_promotion: id, p_code: b.dataset.code, p_label: b.dataset.label, p_max: b.dataset.max ? +b.dataset.max : null, p_active: b.dataset.active === "1" }); }, "Saved."); }; });
      S.$("#pq").onsubmit = function (e) { e.preventDefault(); var f = S.form(e.target); S.go(base + new URLSearchParams(Object.keys(f).reduce(function (o, k) { if (f[k]) o[k] = f[k]; return o; }, {})).toString()); };
      S.$("#pexport").onclick = function () {
        var b = S.$("#pexport"); b.disabled = true;
        S.rpc("admin_promotion", Object.assign({}, args, { p_export: true })).then(function (r) { csv(p, r); S.toast("Exported " + r.rows.length + " entries. The export is recorded."); b.disabled = false; })
          .catch(function (e2) { S.toast(S.friendly(e2), true); b.disabled = false; });
      };
      S.$$("[data-entry]", v).forEach(function (b) {
        b.onclick = function () {
          S.popup("Change this entry", "<label>Status<select id='pst'>" + ["valid", "flagged", "invalid"].map(function (s) { return "<option" + (s === b.dataset.st ? " selected" : "") + ">" + s + "</option>"; }).join("") + "</select></label>" +
            "<label>Reason (kept in the history)<textarea id='pwhy' rows='2' minlength='10'></textarea></label>", [{ text: "Back" }, { text: "Save", primary: true, click: function (close, el) {
              el.disabled = true; S.rpc("admin_promotion_entry", { p_entry: b.dataset.entry, p_to: S.$("#pst").value, p_reason: S.$("#pwhy").value }).then(function () { close(); S.toast("Saved."); S.render(); }).catch(function (e2) { el.disabled = false; S.toast(S.friendly(e2), true); }); } }]);
        };
      });
      var pdr = S.$("#pdraw"); if (pdr) pdr.onsubmit = function (e) { e.preventDefault(); var bt = pdr.querySelector("button"); S.confirmBtn(bt, function () { S.act(bt, function () { return S.rpc("admin_promotion_draw", { p_id: id, p_witness: S.form(pdr).witness }); }, function (r) { return "Drawn from " + r.entries_in_draw + " entries."; }); }); };
      S.$$("[data-res]", v).forEach(function (b) {
        b.onclick = function () {
          if (b.dataset.to === "contacted" || b.dataset.to === "confirmed" || b.dataset.to === "handed_over")
            return S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("admin_promotion_result", { p_result: b.dataset.res, p_to: b.dataset.to, p_note: null }); }, "Saved."); });
          S.popup("What happened", "<label>Note (kept in the history)<textarea id='pwhy' rows='2' minlength='10' placeholder='For example: no reply after 14 days, called 3 times'></textarea></label><p class='note'>The next reserve becomes the winner.</p>",
            [{ text: "Back" }, { text: "Save", primary: true, click: function (close, el) {
              el.disabled = true; S.rpc("admin_promotion_result", { p_result: b.dataset.res, p_to: b.dataset.to, p_note: S.$("#pwhy").value }).then(function () { close(); S.toast("Saved. The next reserve is now the winner."); S.render(); }).catch(function (e2) { el.disabled = false; S.toast(S.friendly(e2), true); }); } }]);
        };
      });
    });
  }, "admin");
})();
