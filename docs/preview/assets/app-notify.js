/* app-notify.js: Notifications (part 24). Account: mobile check and message settings. Admin: Outbox, notice channels,
   SMS opt-outs, Announcements. The database decides who gets what; the Edge Function send-outbox sends the SMS. */
(function () {
  var S = window.Saaz, esc = S.esc;

  // Ask the sender to run (at most every 30 seconds from this tab). Safe to call often: it only sends what the database queued.
  var lastKick = 0;
  S.kick = function (now) {
    if (!S.db || !S.signedIn || !S.signedIn()) return;
    if (!now && Date.now() - lastKick < 30000) return;
    lastKick = Date.now();
    try { S.db.functions.invoke("send-outbox", { body: {} }).catch(function () {}); } catch (e) {}
  };

  // ---------- My account: mobile check and message settings ----------
  S.accountMessages = function (el) {
    if (!el) return;
    S.rpc("my_notify_prefs").then(function (p) {
      var tick = function (name, label, on, note) { return "<label class='inline'><input type='checkbox' name='" + name + "' value='1'" + (on ? " checked" : "") + "> " + label + (note ? " <small>" + note + "</small>" : "") + "</label>"; };
      var mob = !p.mobile ? "<p>No mobile number yet. Add it under Details above.</p>"
        : !p.mobile_ok ? "<p>" + esc(p.mobile) + ": Saaz sends SMS to Ugandan mobiles only (07XX XXX XXX).</p>"
        : p.phone_verified ? "<p><b>" + esc(p.mobile) + "</b> · Verified</p>"
        : "<p><b>" + esc(p.mobile) + "</b> · Not verified yet. " + (p.needs_verified ? "SMS go only to verified numbers." : "") + "</p>" +
          "<div class='row'><button type='button' class='btn ghost' id='pcsend'>Send me a code by SMS</button></div>" +
          "<form id='pccheck' class='inlineform' hidden><label>Code from the SMS<input name='code' inputmode='numeric' autocomplete='one-time-code' pattern='[0-9]{6}' maxlength='6' required></label><button class='btn small'>Check</button></form>" +
          "<p class='err' id='pcerr' role='alert'></p>";
      el.innerHTML = "<section data-ref='account-messages'><h2>Mobile number</h2>" + mob + "</section>" +
        "<section><h2>Messages from Saaz</h2><form id='npf' class='stack'>" +
        "<b>About your own cars, offers, deals and jobs</b>" + tick("alerts_sms", "SMS", p.alerts_sms) + tick("alerts_email", "Email", p.alerts_email, "starts once Saaz connects email") +
        "<b>News and offers from Saaz</b>" + tick("news_sms", "SMS", p.news_sms) + tick("news_email", "Email", p.news_email, "starts once Saaz connects email") +
        "<p class='note'>Everything also lands in your Saaz inbox. Saaz never asks for money or codes by SMS.</p><button class='btn'>Save message settings</button></form></section>";
      S.$("#npf").onsubmit = function (e) {
        e.preventDefault(); var f = S.form(e.target);
        S.act(e.target.querySelector("button"), function () { return S.rpc("set_notify_prefs", { p: { alerts_sms: f.alerts_sms === "1", alerts_email: f.alerts_email === "1", news_sms: f.news_sms === "1", news_email: f.news_email === "1" } }); }, "Message settings saved.");
      };
      var send = S.$("#pcsend"), chk = S.$("#pccheck"), er = S.$("#pcerr");
      if (send) send.onclick = function () {
        send.disabled = true; er.textContent = "";
        S.rpc("phone_send_code").then(function (r) {
          S.kick(true); chk.hidden = false; chk.querySelector("input").focus();
          S.toast("Code sent to " + r.sent_to + ". It works for " + r.expires_in_minutes + " minutes.");
          setTimeout(function () { send.disabled = false; send.textContent = "Send a new code"; }, 60000);
        }).catch(function (e2) { er.textContent = S.friendly(e2); send.disabled = false; });
      };
      if (chk) chk.onsubmit = function (e) {
        e.preventDefault(); var b = chk.querySelector("button"); b.disabled = true; er.textContent = "";
        S.rpc("phone_check_code", { p_code: S.form(chk).code }).then(function (r) {
          if (r.ok) { S.toast("Mobile number verified."); S.render(); return; }
          b.disabled = false; er.textContent = "That code isn't right. " + r.tries_left + " tries left.";
        }).catch(function (e2) { b.disabled = false; er.textContent = S.friendly(e2); });
      };
    }).catch(function () { el.innerHTML = ""; });   // before part 24 is in the database the section simply isn't shown
  };

  // ---------- Admin ----------
  if (!S.adminPage) return;
  var page = S.adminPage;
  function table(head, rows) {
    return "<div class='tablewrap'><table class='tbl'><thead><tr>" + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr></thead><tbody>" +
      (rows.length ? rows.join("") : "<tr><td colspan='" + head.length + "' class='note'>Nothing here.</td></tr>") + "</tbody></table></div>";
  }
  var WORD = { queued: "Waiting to send", sending: "Sending", sent: "Sent", failed: "Failed", held: "Held", skipped: "Not sent" };

  S.route("/admin/outbox", function (v, m, q) {
    var st = q.get("status") || null, ch = q.get("channel") || null, pg = +(q.get("page") || 1), full = !!(S.state.roles || {}).full_admin;
    return Promise.all([S.rpc("admin_outbox", { p_status: st, p_channel: ch, p_page: pg }), S.rpc("admin_notify_kinds"), full ? S.rpc("admin_announcements") : Promise.resolve(null)]).then(function (x) {
      var o = x[0], kinds = x[1], an = x[2], c = o.counts || {}, lr = o.last_run;
      var link = function (s, c2, label) { return "<a href='#/admin/outbox?" + new URLSearchParams(Object.assign({}, s ? { status: s } : {}, c2 ? { channel: c2 } : {})).toString() + "'" + (s === st && c2 === ch ? " aria-current='page'" : "") + ">" + label + "</a>"; };
      var n = function (k) { return c[k] || 0; };
      var sender = !lr ? "<p class='note'>The SMS sender has never run. Deploy send-outbox and set its Africa's Talking secrets (README, Notifications).</p>"
        : !lr.configured ? "<p class='note'><b class='warn'>SMS sender ran " + S.when(lr.at) + " but its Africa's Talking keys aren't set.</b> SMS wait here until they are.</p>"
        : "<p class='note'>SMS sender last ran " + S.when(lr.at) + ": " + lr.claimed + " taken, " + lr.sent + " sent, " + lr.failed + " failed." + (lr.note ? " <b class='warn'>" + esc(lr.note) + "</b>" : "") + "</p>";
      var rows = o.rows.map(function (r) {
        return "<tr><td>" + S.when(r.at) + "</td><td>" + esc(r.name || "") + (r.to ? "<small> " + esc(r.to) + "</small>" : "") + "</td><td>" + esc(r.channel.toUpperCase()) + " <small>" + esc(r.purpose) + "</small></td><td>" + esc(r.kind) + "</td><td>" + esc(r.body) + "</td><td>" +
          (r.status === "failed" ? "<b class='bad'>" : r.status === "held" || r.status === "skipped" ? "<b class='warn'>" : "<b>") + esc(WORD[r.status] || r.status) + "</b>" +
          (r.reason ? "<small> " + esc(r.reason) + "</small>" : "") + (r.status === "sent" && r.cost ? "<small> " + esc(r.cost) + "</small>" : "") + (r.status === "queued" && new Date(r.next_try_at) > new Date() ? "<small> from " + S.when(r.next_try_at) + "</small>" : "") + "</td><td>" +
          (r.status === "failed" && r.channel === "sms" && r.purpose !== "code" ? "<button class='btn small ghost' data-retry='" + r.id + "'>Send again</button>" : "") + "</td></tr>";
      });
      var pages = Math.max(1, Math.ceil(o.total / o.size));
      var kindsSec = "<section><h2>Channels for each notice</h2><p class='note'>The app inbox always gets every notice. Changes apply to new notices." + (full ? "" : " Only a Saaz admin can change these.") + "</p>" +
        table(["Notice", "Used so far", "SMS", "Email", ""], kinds.filter(function (k) { return ["announcement", "phone_code"].indexOf(k.kind) < 0; }).map(function (k) {
          var cur = k.override || k.seen || ["app"];
          return "<tr><td>" + esc(k.kind) + (k.override ? " <small>" + (k.by_admin ? "changed by an admin" : "Saaz default") + "</small>" : "") + "</td><td>" + (k.count || 0) + "</td>" +
            ["sms", "email"].map(function (chn) { return "<td><input type='checkbox' aria-label='" + esc(k.kind + " by " + chn) + "' data-kind='" + esc(k.kind) + "' data-ch='" + chn + "'" + (cur.indexOf(chn) >= 0 ? " checked" : "") + (full ? "" : " disabled") + "></td>"; }).join("") +
            "<td>" + (full ? "<button class='btn small ghost' data-kindsave='" + esc(k.kind) + "'>Save</button>" + (k.override ? " <button class='btn small text' data-kindclear='" + esc(k.kind) + "'>As built</button>" : "") : "") + "</td></tr>";
        })) + "</section>";
      var optSec = !an ? "" : "<section><h2>SMS opt-outs</h2><p class='note'>Numbers that asked Saaz to stop SMS (by phone, WhatsApp or in person). Checked before every SMS except phone check codes they ask for.</p>" +
        table(["Number", "When", "How they asked", ""], an.optouts.map(function (z) { return "<tr><td>" + esc(z.mobile) + "</td><td>" + S.day(z.at) + "</td><td>" + esc(z.reason) + "</td><td><button class='btn small text' data-optin='" + esc(z.mobile) + "'>Remove</button></td></tr>"; })) +
        "<form id='optf' class='inlineform'><label>Mobile<input name='mobile' type='tel' required placeholder='0772 123456'></label><label>How they asked<input name='reason' required minlength='10' maxlength='200' placeholder='Called Saaz on 3 Nov'></label><button class='btn small'>Stop SMS to this number</button></form></section>";
      page(v, "outbox", "<div class='pagehead'><h2>Outbox</h2></div>" + sender +
        "<p class='note'>SMS: " + n("sms:sent") + " sent, " + n("sms:queued") + " waiting, " + n("sms:failed") + " failed, " + n("sms:skipped") + " not sent. Email: " + n("email:held") + " held (no email sender yet).</p>" +
        "<nav class='tabs' aria-label='Filter'>" + link(null, null, "All") + link("queued", "sms", "SMS waiting") + link("sent", "sms", "SMS sent") + link("failed", "sms", "SMS failed") + link("skipped", "sms", "SMS not sent") + link("held", "email", "Email held") + "</nav>" +
        table(["When", "To", "Channel", "Notice", "Message", "Status", ""], rows) +
        (pages > 1 ? "<nav class='pager' aria-label='Pages'>" + Array.apply(null, Array(Math.min(pages, 20))).map(function (_, i) { return i + 1 === o.page ? "<span aria-current='page'>" + (i + 1) + "</span>" : "<a href='#/admin/outbox?" + new URLSearchParams(Object.assign({ page: i + 1 }, st ? { status: st } : {}, ch ? { channel: ch } : {})).toString() + "'>" + (i + 1) + "</a>"; }).join("") + "</nav>" : "") +
        kindsSec + optSec);
      S.$$("[data-retry]", v).forEach(function (b) { b.onclick = function () { S.act(b, function () { return S.rpc("admin_outbox_retry", { p_id: +b.dataset.retry }); }, "Queued to send again."); }; });
      S.$$("[data-kindsave]", v).forEach(function (b) {
        b.onclick = function () {
          var k = b.dataset.kindsave, chs = ["app"].concat(S.$$("input[data-kind='" + k + "']:checked", v).map(function (i) { return i.dataset.ch; }));
          S.act(b, function () { return S.rpc("admin_notify_kind", { p_kind: k, p_channels: chs }); }, "Saved. New " + k + " notices use: " + chs.join(", ") + ".");
        };
      });
      S.$$("[data-kindclear]", v).forEach(function (b) { b.onclick = function () { S.act(b, function () { return S.rpc("admin_notify_kind", { p_kind: b.dataset.kindclear, p_channels: null }); }, "Back to the channels the notice was built with."); }; });
      var of = S.$("#optf"); if (of) of.onsubmit = function (e) { e.preventDefault(); var f = S.form(of); S.act(of.querySelector("button"), function () { return S.rpc("admin_sms_optout", { p_mobile: f.mobile, p_reason: f.reason, p_add: true }); }, "That number gets no more SMS."); };
      S.$$("[data-optin]", v).forEach(function (b) { b.onclick = function () { S.confirmBtn(b, function () { S.act(b, function () { return S.rpc("admin_sms_optout", { p_mobile: b.dataset.optin, p_reason: null, p_add: false }); }, "Removed from the opt-out list."); }); }; });
    });
  }, "admin");

  var AUD = [["all", "Everyone with a Saaz account"], ["sellers", "Sellers (listed a car)"], ["buyers", "Buyers (saved a car or made an offer)"], ["garages", "Certified garage teams"], ["promotion", "Entrants of a promotion"]];
  S.route("/admin/announce", function (v) {
    return S.rpc("admin_announcements").then(function (an) {
      var proms = an.promotions;
      page(v, "announce", "<div class='pagehead'><h2>Announcements</h2></div><p class='lead'>One message to many people. It lands in each person's Saaz inbox. SMS go only to people who opted in, between 08:00 and 20:00 East Africa Time.</p>" +
        "<section><h2>New announcement</h2><form id='anf' class='stack'>" +
        "<label>Who<select name='audience'>" + AUD.map(function (a) { return "<option value='" + a[0] + "'>" + a[1] + "</option>"; }).join("") + "</select></label>" +
        "<label id='anpromo' hidden>Promotion<select name='promotion'>" + proms.map(function (p) { return "<option value='" + p.id + "'>" + esc(p.title) + "</option>"; }).join("") + "</select></label>" +
        "<label>Message<textarea name='body' rows='3' minlength='10' maxlength='450' required placeholder='For example: New inspected Harriers this week. See them on Saaz.'></textarea></label><p class='note' id='ancount'>0 characters</p>" +
        "<label>Link (a Saaz page, optional)<input name='link' placeholder='#/browse' pattern='#/[^ ]*'></label>" +
        "<label class='inline'><input type='checkbox' name='sms' value='1'> Also by SMS (opted-in people only)</label>" +
        "<div class='row'><button type='button' class='btn ghost' id='anprev'>Check who gets it</button><button class='btn' id='ansend' disabled>Send</button></div><div id='anres'></div></form></section>" +
        "<section><h2>Sent</h2>" + table(["When", "By", "Who", "Message", "Inbox", "SMS"], an.list.map(function (a) {
          return "<tr><td>" + S.when(a.at) + "</td><td>" + esc(a.by || "") + "</td><td>" + esc((AUD.filter(function (x) { return x[0] === a.audience; })[0] || [0, a.audience])[1]) + (a.promotion ? "<small> " + esc(a.promotion) + "</small>" : "") + "</td><td>" + esc(a.body) + "</td><td>" + (a.counts.app || 0) + "</td><td>" +
            (a.channels.indexOf("sms") >= 0 ? (a.counts.sms || 0) + "<small> (" + (a.counts.sms_skipped || 0) + " not sent)</small>" : "No") + "</td></tr>"; })) + "</section>");
      var f = S.$("#anf"), cnt = S.$("#ancount"), send = S.$("#ansend"), res = S.$("#anres"), seen = null;
      var args = function () { var d = S.form(f); return { p_audience: d.audience, p_promotion: d.audience === "promotion" ? d.promotion || null : null, p_channels: d.sms === "1" ? ["app", "sms"] : ["app"], p_body: d.body, link: d.link || null }; };
      var stale = function () { send.disabled = true; seen = null; res.innerHTML = ""; };
      f.audience.onchange = function () { S.$("#anpromo").hidden = f.audience.value !== "promotion"; stale(); };
      f.body.oninput = function () { var l = ("Saaz: " + f.body.value + " Stop these in your Saaz account.").length; cnt.textContent = f.body.value.length + " characters · " + (l <= 160 ? 1 : Math.ceil(l / 153)) + " SMS part" + (l <= 160 ? "" : "s") + " each"; stale(); };
      [f.sms, f.link, f.promotion].forEach(function (x) { if (x) x.onchange = stale; });
      S.$("#anprev").onclick = function () {
        var a = args(), b = S.$("#anprev"); if (a.p_body.trim().length < 10) { S.toast("Write the message first (10 characters or more).", true); return; }
        b.disabled = true;
        S.rpc("admin_announce_preview", { p_audience: a.p_audience, p_promotion: a.p_promotion, p_channels: a.p_channels, p_body: a.p_body }).then(function (p) {
          b.disabled = false; seen = JSON.stringify(a); send.disabled = !p.people;
          var why = Object.keys(p.sms_not_sent || {}).map(function (k) { return esc(k) + ": " + p.sms_not_sent[k]; }).join("; ");
          res.innerHTML = "<div class='box'><p><b>" + p.people + "</b> people get it in their Saaz inbox.</p>" + (a.p_channels.indexOf("sms") >= 0 ?
            "<p><b>" + p.sms + "</b> get an SMS (" + p.segments + " part" + (p.segments > 1 ? "s" : "") + " each), from " + S.when(p.sms_from) + ". " +
            (p.cost_ugx != null ? "Estimated cost UGX " + Number(p.cost_ugx).toLocaleString("en-US") + "." : "Cost unknown: set sms_price_ugx in Settings.") + "</p>" + (why ? "<p class='note'>No SMS: " + why + ".</p>" : "") : "") + "</div>";
        }).catch(function (e2) { b.disabled = false; S.toast(S.friendly(e2), true); });
      };
      f.onsubmit = function (e) {
        e.preventDefault(); var a = args();
        if (seen !== JSON.stringify(a)) { stale(); S.toast("Check who gets it first.", true); return; }
        S.confirmBtn(send, function () {
          S.act(send, function () { return S.rpc("admin_announce", { p_audience: a.p_audience, p_promotion: a.p_promotion, p_channels: a.p_channels, p_body: a.p_body, p_link: a.link }); },
            function (r) { return "Sent to " + r.app + " inboxes" + (a.p_channels.indexOf("sms") >= 0 ? ", " + r.sms + " SMS queued" : "") + "."; });
        });
      };
    });
  }, "admin");
})();
