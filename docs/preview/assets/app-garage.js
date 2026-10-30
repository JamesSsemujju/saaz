/* app-garage.js: become a certified garage, garage dashboard (offered to you, my jobs), a job, the review editor, the team. */
(function () {
  var S = window.Saaz, esc = S.esc;
  var SPECIALTIES = ["Toyota", "Nissan", "Honda", "Subaru", "Mercedes-Benz", "BMW", "Diesel engines", "Hybrids", "Gearboxes", "Bodywork", "Electrics"];

  function garageFields(g) {
    g = g || {};
    return "<div class='grid2'><label>Business type<select name='business_type' required><option value='garage'" + (g.business_type !== "independent_mechanic" ? " selected" : "") + ">Garage</option>" +
      "<option value='independent_mechanic'" + (g.business_type === "independent_mechanic" ? " selected" : "") + ">Independent mechanic</option></select></label>" +
      "<label>Business name<input name='name' required value='" + esc(g.name || "") + "'></label>" +
      "<input type='hidden' name='country' id='gctry' value='UG'>" +
      "<label>Region<select name='region' id='greg' required></select></label><label>Address<input name='address' required value='" + esc(g.address || "") + "'></label>" +
      "<label>Business phone<input name='phone' type='tel' required value='" + esc(g.phone || "") + "'></label>" +
      "<label>Registration or licence number<input name='registration_no' required value='" + esc(g.registration_no || "") + "'></label>" +
      "<label>Years in business<input name='years' type='number' min='0' value='" + esc(g.years == null ? "" : g.years) + "'></label></div>" +
      "<fieldset class='checks2'><legend>Specialties</legend>" + SPECIALTIES.map(function (s) { return "<label class='inline'><input type='checkbox' name='sp' value='" + s + "'" + ((g.specialties || []).indexOf(s) >= 0 ? " checked" : "") + "> " + s + "</label>"; }).join("") + "</fieldset>";
  }
  S.garageFields = garageFields;
  S.wireRegions = function (g) {
    var c = S.$("#gctry"), r = S.$("#greg");
    function fill() { r.innerHTML = S.REGIONS[c.value].map(function (x) { return "<option" + (g && g.region === x ? " selected" : "") + ">" + x + "</option>"; }).join(""); }
    fill();
  };
  S.garagePayload = function (form) {
    var f = S.form(form); f.specialties = S.$$("input[name=sp]:checked", form).map(function (i) { return i.value; }); delete f.sp; f.honest_declaration = true; return f;
  };

  S.route("/garage/apply", function (v) {
    var signed = S.signedIn();
    v.innerHTML = "<div class='narrow wide'><h1>Become a certified Saaz garage</h1><p class='lead'>Garages and independent mechanics inspect cars inside Saaz. Saaz answers within " +
      "2 working days (assumption).</p><form id='f' class='stack'>" +
      (signed ? "" : "<h2>Your account</h2><div class='grid2'><label>Full name<input name='acc_name' required></label><label>Email<input name='acc_email' type='email' required></label>" +
        "<label>Mobile<input name='acc_mobile' type='tel' required></label><label>Password<input name='acc_password' type='password' minlength='8' required></label></div><p class='note'>Already have an account? <a href='#/signin' data-after='#/garage/apply'>Sign in first</a>.</p>") +
      "<h2>Your business</h2>" + garageFields() +
      "<label class='inline'><input type='checkbox' name='honest' required> I will only issue honest Saaz inspections, of cars I have seen in person, and never accept payment to change a result.</label>" +
      "<p class='err' id='err' role='alert'></p><button class='btn'>Send application</button></form></div>";
    S.wireRegions();
    S.$("#f").onsubmit = function (e) {
      e.preventDefault(); var form = e.target, f = S.form(form), p = S.garagePayload(form), b = form.querySelector("button");
      ["acc_name", "acc_email", "acc_mobile", "acc_password", "honest"].forEach(function (k) { delete p[k]; });
      b.disabled = true;
      var ready = signed ? Promise.resolve() : S.db.auth.signUp({ email: f.acc_email, password: f.acc_password, options: { data: { name: f.acc_name, country: "UG", mobile: f.acc_mobile } } })
        .then(function (r) {
          if (r.error) throw r.error;
          if (!r.data.session) { try { localStorage.setItem("saaz-pending-garage", JSON.stringify(p)); } catch (x) {} throw new Error("Check your email to confirm your account, then sign in: your application will be sent then."); }
        });
      ready.then(function () { return S.rpc("apply_garage", { p: p }); }).then(function () {
        v.innerHTML = "<div class='narrow'><h1>Application sent</h1><p>Status: Applied. Saaz will tell you here, by email and by SMS once those are connected. Until then, Garage team sign-in shows your status.</p><a class='btn' href='#/garage'>See status</a></div>";
      }).catch(function (e2) { S.$("#err").textContent = S.friendly(e2); b.disabled = false; });
    };
  });

  // Garage dashboard
  S.route("/garage", function (v) {
    return S.rpc("garage_sign_in").then(function (g) {
      if (!g.ok) {
        var gar = (S.state.roles || {}).garage;
        v.innerHTML = "<div class='narrow'><h1>Garage team</h1><p class='box warn'>" + esc(g.message) + "</p>" +
          (gar && gar.status === "more_info" && gar.member_role === "owner" ? "<a class='btn' href='#/garage/resubmit'>Update and resubmit</a>" : "") +
          (!gar ? "<a class='btn' href='#/garage/apply'>Become a certified garage</a>" : "") + "</div>";
        try { var pend = localStorage.getItem("saaz-pending-garage"); if (pend && !gar) { localStorage.removeItem("saaz-pending-garage"); S.rpc("apply_garage", { p: JSON.parse(pend) }).then(function () { S.toast("Garage application sent."); S.render(); }); } } catch (x) {}
        return;
      }
      S.mode("garage");
      return S.rpc("garage_jobs").then(function (jobs) {
        var inplay = jobs.filter(function (j) { return j.conversation.status === "in_play"; }), booked = jobs.filter(function (j) { return j.conversation.status === "agreed"; }),
          past = jobs.filter(function (j) { return ["in_play", "agreed"].indexOf(j.conversation.status) < 0; });
        var owner = g.role === "owner";
        function rows(list, empty) {
          if (!list.length) return "<p class='note'>" + empty + "</p>";
          return "<ul class='rows'>" + list.map(function (j) {
            var c = j.conversation, l = j.listing;
            return "<li><a href='#/garage/job/" + c.id + "'><div class='thumb'>" + (l.photos[0] ? "<img src='" + esc(S.photo(l.photos[0])) + "' alt=''>" : "") + "</div><div class='grow'><b>" + esc(S.name(l)) + "</b> " + S.chip(c.status) +
              "<small>" + esc(l.ref) + " · " + esc(l.region) + " · " + S.km(l.mileage) + (c.status === "in_play" && !c.garage_first_message_at ? " · message by " + S.when(c.deadline) : "") +
              (c.review_date ? " · inspection " + S.day(c.review_date) : "") + (j.draft ? " · " + esc(j.draft.doc_no || "") + " draft by " + esc(j.draft.member) : "") +
              (owner && ["in_play", "agreed"].indexOf(c.status) >= 0 ? " · " + (j.inspector ? "given to " + esc(j.inspector) : "<b>not given out yet</b>") : "") + "</small></div></a></li>";
          }).join("") + "</ul>";
        }
        var openById = "<form id='oid' class='inlineform'><label>Open an inspection by its ID<input name='id' placeholder='SZR-2026-000123' required></label><button class='btn small ghost'>Open</button></form>";
        v.innerHTML = "<div class='pagehead'><h1>" + esc(g.garage) + "</h1><span class='chip'>" + esc(S.label(g.role)) + "</span></div>" + openById +
          (owner ? "<section><h2>Offered to you</h2><p class='note'>Only your garage can contact these sellers right now, inside Saaz. Give each car to a team member, or handle it yourself. Message within the time shown or the next garage comes in.</p>" + rows(inplay, "Nothing offered right now.") + "</section>" +
            "<section><h2>Booked jobs</h2>" + rows(booked, "No booked jobs.") + "</section>"
          : "<section><h2>My jobs</h2><p class='note'>The jobs your garage owner gave you. You see only your own work.</p>" + rows(inplay.concat(booked), "No jobs given to you right now.") + "</section>") +
          (past.length ? "<section><h2>Past</h2>" + rows(past.slice(0, 20), "") + "</section>" : "");
        var oid = S.$("#oid"); oid.onsubmit = function (e) { e.preventDefault(); var b = oid.querySelector("button"); b.disabled = true;
          S.rpc("open_inspection", { p_id: S.form(oid).id }).then(function (r) { S.go("#/inspection/" + r.inspection_id); })
            .catch(function (e2) { b.disabled = false; S.toast(S.friendly(e2), true); }); };
      });
    });
  }, "user");

  S.route("/garage/resubmit", function (v) {
    var gid = ((S.state.roles || {}).garage || {}).id;
    return S.q(S.db.from("garages").select("*").eq("id", gid)).then(function (rows) {
      var g = rows[0];
      v.innerHTML = "<div class='narrow wide'><h1>Update your application</h1><p class='box warn'>Saaz asked: " + esc(g.status_note) + "</p><form id='f' class='stack'>" + garageFields(g) + "<button class='btn'>Resubmit</button></form></div>";
      S.wireRegions(g);
      S.$("#f").onsubmit = function (e) { e.preventDefault(); var p = S.garagePayload(e.target); S.act(e.target.querySelector("button"), function () { return S.rpc("resubmit_garage", { p_garage: gid, p: p }); }, "Resubmitted."); };
    });
  }, "user");

  S.route("/garage/job/([0-9a-f-]+)", function (v, m) {
    var cid = m[0];
    return S.rpc("garage_jobs").then(function (jobs) {
      var j = jobs.filter(function (x) { return x.conversation.id === cid; })[0];
      if (!j) throw new Error("This job isn't yours.");
      var c = j.conversation, l = j.listing;
      return S.q(S.db.from("messages").select("*").eq("conversation_id", cid).order("created_at")).then(function (msgs) {
        c.garages = { name: "Seller" };
        var acts = [], owner = ((S.state.roles || {}).garage || {}).member_role === "owner", canStart = j.mine || (owner && !c.inspector_id);
        if (c.status === "in_play" && owner) acts.push("<button class='btn ghost' id='decline'>Decline this car</button>");
        if (c.status === "agreed") {
          acts.push("<form id='df' class='inlineform'><label>Inspection date<input name='date' type='date' value='" + esc(c.review_date || "") + "'></label><button class='btn small'>Set date</button></form>");

          if (owner) acts.push("<button class='btn ghost' id='release'>Release this job</button>");
        }
        var giveTo = owner && ["in_play", "agreed"].indexOf(c.status) >= 0 ? "<form id='gf' class='inlineform'><label>Give this job to<select name='m' id='gsel'><option value=''>Loading team…</option></select></label><button class='btn small ghost'>Save</button></form>" : "";
        v.innerHTML = "<p class='crumbs'><a href='#/garage'>Garage</a> / " + esc(l.ref) + "</p><div class='pagehead'><h1>" + esc(S.name(l)) + "</h1>" + S.chip(c.status) + "</div>" +
          "<p class='lead'>" + esc(l.region) + " · seller's mileage " + S.km(l.mileage) + "</p>" +
          (c.status === "in_play" ? "<p class='box'>Message the seller to arrange the inspection. They can agree once you've messaged. " + (c.garage_first_message_at ? "" : "You have until " + S.when(c.deadline) + ".") + "</p>" : "") +
          (c.status === "agreed" ? "<p class='box good'>The seller agreed. Start the inspection when the car is in front of you.</p>" : "") +
          "<p class='note'>" + (j.inspector ? "Given to " + esc(j.inspector) + "." : "Not given out yet: only the owner sees it.") + "</p>" + giveTo +
          (c.status === "agreed" ? "<section><h2>Inspections of this car</h2><p class='note'>Each inspection has its own ID and one inspector. " + (owner ? "Give each one to a team member; only that person can start it." : "You see the ones given to you.") + "</p>" +
            "<div class='tablewrap'><table class='tbl'><thead><tr><th>Inspection ID</th><th>Type</th><th>Inspector</th><th>Status</th><th></th></tr></thead><tbody>" + (j.inspections || []).map(function (x) {
              var give = owner && x.status === "requested" ? "<select data-give='" + x.id + "'><option value=''>Not given out</option></select>" : esc(x.inspector || "");
              var act = x.status === "draft" && x.mine ? "<a class='btn small' href='#/garage/review/" + x.id + "'>Continue</a>" : x.status === "requested" && (x.mine || (owner && !x.inspector_id)) ? "<a class='btn small' href='#/inspection/" + esc(x.inspection_id) + "'>Open to start</a>" : x.verify_code ? "<a href='#/report/" + esc(x.verify_code) + "'>Report</a>" : "";
              return "<tr><td class='mono'><a href='#/inspection/" + esc(x.inspection_id) + "'>" + esc(x.inspection_id) + "</a></td><td>" + esc(x.scope_name) + "</td><td>" + give + "</td><td>" + S.inspChip(x.status) + "</td><td>" + act + "</td></tr>";
            }).join("") + "</tbody></table></div></section>" : "") +
          S.convoHtml(c, msgs, false) + "<div class='row'>" + acts.join("") + "</div>";
        var gives = S.$$("[data-give]", v);
        if (gives.length) S.rpc("garage_team", { p_garage: null }).then(function (team) {
          var opts = team.filter(function (t) { return t.kind === "member" && t.status === "active"; });
          gives.forEach(function (sel) {
            var x = (j.inspections || []).filter(function (y) { return y.id === sel.dataset.give; })[0];
            sel.innerHTML = "<option value=''>Not given out</option>" + opts.map(function (t) { return "<option value='" + t.user_id + "'" + (t.user_id === x.inspector_id ? " selected" : "") + ">" + esc(t.name || t.email) + "</option>"; }).join("");
            sel.onchange = function () { S.act(sel, function () { return S.rpc("assign_inspection", { p_review: sel.dataset.give, p_member: sel.value || null }); }, sel.value ? "Inspection given. They're told its ID." : "Inspection taken back."); };
          });
        });
        var gf = S.$("#gf"); if (gf) {
          S.rpc("garage_team", { p_garage: null }).then(function (team) {
            S.$("#gsel").innerHTML = "<option value=''>Not given out (owner)</option>" + team.filter(function (t) { return t.kind === "member" && t.status === "active"; }).map(function (t) {
              return "<option value='" + t.user_id + "'" + (t.user_id === c.inspector_id ? " selected" : "") + ">" + esc(t.name || t.email) + " · " + esc(S.label(t.role)) + "</option>"; }).join("");
          });
          gf.onsubmit = function (e) { e.preventDefault(); var mm = S.form(gf).m; S.act(gf.querySelector("button"), function () { return S.rpc("assign_job", { p_conv: cid, p_member: mm || null }); }, mm ? "Job given. They're told." : "Job taken back."); };
        }
        S.wireSend(v);
        var b;
        if ((b = S.$("#decline"))) { var db2 = b; db2.onclick = function () { S.confirmBtn(db2, function () { S.act(db2, function () { return S.rpc("garage_respond", { p_conv: cid, p_action: "decline" }); }, "Declined. The next garage comes in.").then(function () { S.go("#/garage"); }); }); }; }
        if ((b = S.$("#release"))) { var rb = b; rb.onclick = function () { S.confirmBtn(rb, function () { S.act(rb, function () { return S.rpc("garage_respond", { p_conv: cid, p_action: "release" }); }, "Released.").then(function () { S.go("#/garage"); }); }); }; }
        if ((b = S.$("#start"))) { var sb = b; sb.onclick = function () { sb.disabled = true; S.rpc("start_review", { p_listing: l.id }).then(function (rid) { S.go("#/garage/review/" + rid); }).catch(function (e) { S.toast(S.friendly(e), true); sb.disabled = false; }); }; }
        var df = S.$("#df"); if (df) df.onsubmit = function (e) { e.preventDefault(); var f = S.form(df); S.act(df.querySelector("button"), function () { return S.rpc("garage_respond", { p_conv: cid, p_action: "set_date", p_date: f.date }); }, "Inspection date set. The seller is told."); };
      });
    });
  }, "user");

  // Review editor
  function preview(checks, panels, ck, usePanels) {
    var s = 0, max = 0, verdict = "pass", missing = 0, pen = 0;
    (ck || S.CHECKS).forEach(function (c) {
      var w = c[2] ? 10 : 6, val = checks[c[0]]; max += w;
      if (!val) { missing++; return; }
      s += w * (val === "pass" ? 1 : val === "advise" ? 0.5 : 0);
      if (val === "fail" && c[2]) verdict = "fail"; else if (val !== "pass" && verdict === "pass") verdict = "conditional";
    });
    if (usePanels !== false) S.PANELS.forEach(function (p) { pen += { scratch: 1, dent: 2, repaint: 2, damage: 4 }[panels[p[0]]] || 0; });
    return { score: Math.max(0, Math.min(100, Math.round(s / max * 100) - pen)), verdict: verdict, missing: missing };
  }
  S.route("/garage/review/([0-9a-f-]+)", function (v, m) {
    var rid = m[0];
    return Promise.all([S.q(S.db.from("reviews").select("*, listings!reviews_listing_id_fkey(ref,make,model,year,mileage,plate)").eq("id", rid)), S.scopes()]).then(function (res0) {
      var rows = res0[0], r = rows[0]; if (!r) throw new Error("Inspection not found.");
      var sc = res0[1].by[r.scope] || res0[1].by.general, CK = S.CHECKS.filter(function (c) { return sc.checks.indexOf(c[0]) >= 0; });
      if (r.status !== "draft") { S.go(r.verify_code ? "#/report/" + r.verify_code : "#/inspection/" + r.doc_no); return; }
      if (r.member_id !== S.me().id) { v.innerHTML = "<div class='empty'><b>In progress</b><span>Another member of your garage is writing this inspection report.</span></div>"; return; }
      var checks = Object.assign({}, r.checks), panels = Object.assign({}, r.panels), l = r.listings;
      function paint() {
        var p = preview(checks, panels, CK, sc.panels);
        S.$("#pv").innerHTML = "<b>" + p.score + "/100</b> " + S.chip(p.verdict) + (p.missing ? " <small>" + p.missing + " check" + (p.missing === 1 ? "" : "s") + " to mark</small>" : "");
        if (!sc.panels) return;
        S.$("#map").innerHTML = S.bodyMap(panels, true);
        S.$$("#map [data-panel]").forEach(function (g) {
          var cyc = function () { var k = g.dataset.panel, i = S.MARKS.indexOf(panels[k] || "none"); panels[k] = S.MARKS[(i + 1) % S.MARKS.length]; paint(); };
          g.onclick = cyc; g.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); cyc(); } };
        });
        S.$$("#panellist select").forEach(function (s) { s.value = panels[s.name] || "none"; });
      }
      v.innerHTML = "<p class='crumbs'><a href='#/garage'>Garage</a> / " + esc(r.doc_no || "Saaz inspection") + "</p><h1>" + esc(sc.name) + ": " + esc(l.year + " " + l.make + " " + l.model) + "</h1>" +
        "<p class='lead'>Inspection ID <b class='mono'>" + esc(r.doc_no || "given at issue") + "</b> · " + esc(l.ref) + " · plate " + esc(l.plate) + " · seller's mileage " + S.km(l.mileage) + ". Draft locked to you.</p>" +
        "<div class='sticky' id='pv'></div><form id='f' class='stack'><h2>" + (sc.key === "general" ? "12-point check" : esc(sc.name) + ": " + CK.length + " checks") + "</h2><p class='note'>Brakes, steering, odometer and VIN are safety items. A Fail on any of them makes the verdict Fail, and the car can't be listed.</p>" +
        "<div class='checklist'>" + CK.map(function (c) {
          return "<fieldset class='seg three'><legend>" + esc(c[1]) + (c[2] ? " <small>safety</small>" : "") + "</legend>" + ["pass", "advise", "fail"].map(function (x) {
            return "<label><input type='radio' name='c_" + c[0] + "' value='" + x + "'" + (checks[c[0]] === x ? " checked" : "") + "><span class='m-" + x + "'>" + S.label(x) + "</span></label>";
          }).join("") + "</fieldset>";
        }).join("") + "</div>" +
        (sc.panels ? "<h2>Body map, top view</h2><p class='note'>Tap a panel to cycle: no marks, scratch, dent, repaint, damage. Or pick from the lists.</p><div class='mapwrap'><div id='map'></div><div id='panellist' class='grid2'>" +
        S.PANELS.map(function (p) { return "<label>" + p[1] + "<select name='" + p[0] + "'>" + S.MARKS.map(function (k) { return "<option value='" + k + "'>" + S.label(k === "none" ? "no marks" : k) + "</option>"; }).join("") + "</select></label>"; }).join("") + "</div></div>" : "") +
        "<label>Odometer reading (km)<input name='odometer' type='number' min='0' max='1000000' value='" + esc(r.odometer == null ? "" : r.odometer) + "' required></label>" +
        "<label>Notes <small>(required if anything is not a Pass)</small><textarea name='notes' rows='4'>" + esc(r.notes) + "</textarea></label>" +
        "<label class='inline'><input type='checkbox' name='in_person' value='1'" + (r.in_person ? " checked" : "") + "> I inspected this car in person and checked the VIN against the logbook and the car.</label>" +
        "<p class='err' id='err' role='alert'></p><div class='row'><button class='btn' name='go' value='save'>Save draft</button><button class='btn' name='go' value='issue'>Issue the Saaz inspection</button>" +
        "<button type='button' class='btn ghost' id='discard'>Discard draft</button></div><p class='note'>Once issued, an inspection report can't be edited. It carries your name and member id.</p></form>";
      S.$$("#f input[type=radio]").forEach(function (i) { i.onchange = function () { checks[i.name.slice(2)] = i.value; paint(); }; });
      S.$$("#panellist select").forEach(function (s) { s.onchange = function () { panels[s.name] = s.value; paint(); }; });
      paint();
      function payload() { var f = S.form(S.$("#f")); return { checks: checks, panels: panels, odometer: f.odometer, notes: f.notes, in_person: !!f.in_person }; }
      S.$("#f").onsubmit = function (e) {
        e.preventDefault(); var go = e.submitter ? e.submitter.value : "save", btn = e.submitter, err = S.$("#err"); err.textContent = "";
        var doit = function () {
          btn.disabled = true;
          S.rpc("save_review", { p_review: rid, p: payload() }).then(function () {
            if (go !== "issue") { S.toast("Draft saved."); btn.disabled = false; return; }
            return S.rpc("issue_review", { p_review: rid }).then(function (res) { S.toast("Issued " + res.doc_no + "."); S.go("#/report/" + res.verify_code); });
          }).catch(function (e2) { err.textContent = S.friendly(e2); btn.disabled = false; });
        };
        if (go === "issue") S.confirmBtn(btn, doit); else doit();
      };
      var d = S.$("#discard"); d.onclick = function () { S.confirmBtn(d, function () { S.rpc("discard_review", { p_review: rid }).then(function () { S.toast("Draft discarded."); S.go("#/garage"); }); }); };
    });
  }, "user");

  // Team
  S.route("/garage/team", function (v) {
    return S.rpc("garage_team", { p_garage: null }).then(function (team) {
      var owner = ((S.state.roles || {}).garage || {}).member_role === "owner";
      v.innerHTML = "<p class='crumbs'><a href='#/garage'>Garage</a> / Team</p><h1>Team</h1>" + (team[0] ? "<p class='lead'>Garage: <b>" + esc(S.garageStage(team[0].garage_status)) + "</b></p>" : "") + "<ul class='list team'>" + team.map(function (t) {
        var info = S.inviteInfo(t);
        return "<li><div><b>" + esc(t.name || t.email) + "</b> <span class='chip'>" + esc(S.label(t.role)) + "</span> " + S.inviteStage(t) + "<small>" + esc(t.email) + "</small>" + (info ? "<small class='inv'>" + info + "</small>" : "") + "</div>" +
          "<div class='row'>" + S.teamActions(t, owner) + "</div></li>";
      }).join("") + "</ul>" +
        (owner ? "<h2>Add a member</h2><form id='f' class='stack'><div class='grid2'><label>Name<input name='name' required></label><label>Email<input name='email' type='email' required></label>" +
          "<label>Mobile<input name='mobile' type='tel'></label><label>Role<select name='role'><option value='inspector'>Inspector</option><option value='owner'>Owner</option></select></label></div>" +
          "<button class='btn'>Add member</button><p class='note'>New people get an invite email with a link to set their password; the link works for 24 hours, and you can resend or revoke it here. Anyone who already has a Saaz account just signs in. They show as Invited until they set their password, then Accepted. Removing a member ends their access at once and discards their drafts.</p></form>" : "");
      S.wireTeam(v);
      var f = S.$("#f"); if (f) f.onsubmit = function (e) {
        e.preventDefault(); var x = S.form(f);
        S.act(f.querySelector("button"), function () { return S.rpc("add_garage_member", { p_email: x.email, p_name: x.name, p_mobile: x.mobile, p_role: x.role }); },
          function (r) { return r === "invited" ? "Added. They show as Invited until they sign in, then Accepted." : "Invite saved. Sending the invite email…"; })
          .then(function (r) { if (r === "invite_waiting_for_signup") S.sendInvite(x.email).then(function (m) { S.toast(m); }).catch(function (e) { S.toast(S.friendly(e), true); }); });
      };
    });
  }, "user");
})();
