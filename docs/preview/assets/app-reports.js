/* app-reports.js: Admin > Reports. Each report answers one question.
   Same layout for every report: the question, the control bar, the key numbers, the trend (if any), the table.
   Every number is computed in the database (admin_report, part 16); this page only shows it.
   Every key number and every group count opens the rows behind it. Every table sorts, pages and exports to CSV. */
(function () {
  var S = window.Saaz, esc = S.esc;
  var REPORTS = [
    ["inventory", "Inventory", "What is on the site right now, and is it healthy?"],
    ["funnel", "Listing funnel", "Do listings get seen and acted on?"]
  ];
  var KEEP = ["range", "from", "to", "cmp", "make", "price_band", "status_group", "seller_type", "age_band", "q"];  // filters that follow you between reports
  var STATUS = { draft: "Draft", pending: "Pending", live: "Live", sold: "Sold", expired: "Expired", removed: "Removed" };
  var FLAG_TEXT = { live_now: "Live now", pending_now: "Pending now", draft_now: "Drafts", expired_now: "Expired now", added: "Added in the period", sold: "Sold in the period",
    removed: "Removed in the period", stale: "Not updated in 30 days", no_photos: "No photos", no_price: "No price", has_views: "Viewed in the period",
    has_saves: "Saved in the period", has_enquiries: "With enquiries in the period", first_enquiry: "First enquiry in the period" };
  var opts = null;  // filter options and the glossary, loaded once
  function options() { return opts ? Promise.resolve(opts) : S.rpc("admin_report_options").then(function (o) { opts = o; return o; }); }
  function G(k) { return (opts.glossary[k] || { label: k, def: "" }); }
  function store(q) { try { var o = {}; KEEP.forEach(function (k) { if (q.get(k)) o[k] = q.get(k); }); sessionStorage.setItem("saaz-report-filters", JSON.stringify(o)); } catch (e) {} }
  function recall() { try { return JSON.parse(sessionStorage.getItem("saaz-report-filters") || "{}"); } catch (e) { return {}; } }
  function keepQuery(q) { var p = new URLSearchParams(); KEEP.forEach(function (k) { if (q.get(k)) p.set(k, q.get(k)); }); return p.toString(); }
  function addDays(iso, n) { var d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function period(q) {
    var today = opts.today, r = q.get("range") || "30";
    if (r === "custom" && q.get("from") && q.get("to")) return { from: q.get("from"), to: q.get("to"), range: r };
    var n = { today: 1, "7": 7, "30": 30, "90": 90 }[r] || 30;
    return { from: addDays(today, 1 - n), to: today, range: r === "custom" ? "30" : r };
  }
  function fmt(k, v, row) {
    if (v == null || v === "") return "";
    if (k === "price" || k === "similar_median") return S.money(row && row.currency, v);
    if (k === "status_group") return STATUS[v] || v;
    if (k === "status") return S.label(v);
    if (k === "updated_at" || k === "created_at") return S.day(v);
    if (k === "price_vs_similar") return (v > 0 ? "+" : "") + v + "%";
    if (k === "enquiry_rate") return v + " per 100";
    return typeof v === "number" ? v.toLocaleString("en-US") : String(v);
  }
  function plain(k, v, row) { var t = fmt(k, v, row); return k === "price" || k === "similar_median" ? (v == null ? "" : String(v)) : t; }  // CSV keeps numbers as numbers
  function head(report) { return REPORTS.filter(function (r) { return r[0] === report; })[0]; }

  // ---------- the page shell: report rail on the left, the report on the right ----------
  function shell(v, at, q, html) {
    var qs = keepQuery(q);
    var rail = "<nav class='adminside' aria-label='Reports'><div class='navgroup'><a href='#/admin'>‹ Admin</a></div><div class='navgroup'><b>Reports</b>" +
      REPORTS.map(function (r) { return "<a href='#/admin/reports/" + r[0] + (qs ? "?" + qs : "") + "'" + (r[0] === at ? " aria-current='page'" : "") + ">" + r[1] + "</a>"; }).join("") +
      "</div><div class='navgroup'><a href='#/admin/reports/glossary" + (qs ? "?" + qs : "") + "'" + (at === "glossary" ? " aria-current='page'" : "") + ">Glossary</a></div></nav>";
    var phone = "<label class='adminjump'>Report<select onchange='location.hash=this.value'>" + REPORTS.concat([["glossary", "Glossary"]]).map(function (r) {
      return "<option value='#/admin/reports/" + r[0] + (qs ? "?" + qs : "") + "'" + (r[0] === at ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "<option value='#/admin'>Back to Admin</option></select></label>";
    v.innerHTML = "<div class='adminwrap'>" + rail + "<div class='adminmain'>" + phone + html + "</div></div>";
  }

  // ---------- the control bar: one for every report ----------
  function controlBar(report, q, p) {
    var sel = function (name, label, list, all, lab) {
      return "<label>" + label + "<select name='" + name + "'><option value=''>" + all + "</option>" + list.map(function (x) {
        return "<option value='" + esc(x) + "'" + (q.get(name) === x ? " selected" : "") + ">" + esc(lab ? lab(x) : x) + "</option>"; }).join("") + "</select></label>";
    };
    var ranges = [["today", "Today"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["custom", "Custom"]];
    return "<form id='rbar' class='filters' aria-label='Report controls'>" +
      "<label>Period<select name='range'>" + ranges.map(function (r) { return "<option value='" + r[0] + "'" + (p.range === r[0] || (q.get("range") === "custom" && r[0] === "custom") ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "</select></label>" +
      "<label class='rcustom'" + (q.get("range") === "custom" ? "" : " hidden") + ">From<input type='date' name='from' value='" + p.from + "' max='" + opts.today + "'></label>" +
      "<label class='rcustom'" + (q.get("range") === "custom" ? "" : " hidden") + ">To<input type='date' name='to' value='" + p.to + "' max='" + opts.today + "'></label>" +
      sel("make", "Make", opts.makes, "Any make") + sel("price_band", "Price band", opts.price_bands, "Any price") +
      sel("status_group", "Status", opts.status_groups, "Any status", function (x) { return STATUS[x]; }) +
      sel("seller_type", "Seller", ["private", "saaz"], "Any seller", function (x) { return x === "saaz" ? "Saaz-owned" : "Private sellers"; }) +
      (report === "inventory" ? sel("age_band", "Age on site", opts.age_bands, "Any age") : "") +
      "<label>Search<input name='q' value='" + esc(q.get("q") || "") + "' placeholder='Ref, car or seller'></label>" +
      "<label class='inline'><input type='checkbox' name='cmp' value='1'" + (q.get("cmp") === "1" ? " checked" : "") + "> Compare to previous period</label>" +
      "<button class='btn'>Apply</button></form>";
  }

  // ---------- key numbers: one row; each opens its rows ----------
  function kpis(report, r, q) {
    return "<div class='stats rkpis'>" + r.kpis.map(function (k) {
      var g = G(k.key), p = new URLSearchParams(q.toString()); p.set("flag", k.flag); p.delete("page"); p.delete("group");
      var change = "";
      if (r.compare && k.prev !== undefined) {
        var d = k.value == null || k.prev == null ? null : Math.round((k.value - k.prev) * 10) / 10;
        change = "<small>Previous: " + (k.prev == null ? "none" : fmt(k.key, k.prev)) + (d == null || d === 0 ? "" : " (" + (d > 0 ? "+" : "") + d.toLocaleString("en-US") + ")") + "</small>";
      }
      return "<a href='#/admin/reports/" + report + "?" + p.toString() + "' title='" + esc(g.def) + "'" + (q.get("flag") === k.flag ? " aria-current='true'" : "") + ">" +
        "<b>" + (k.value == null ? "–" : esc(fmt(k.key, k.value))) + "</b><span>" + esc(g.label) + "</span>" + change + "</a>";
    }).join("") + "</div>";
  }

  // ---------- trend: small line charts, one measure each (never two scales on one axis) ----------
  function chart(title, key, trend, compare) {
    // drawn at about the size it is shown, so the 12 px labels stay 12 px on a phone
    var W = window.innerWidth < 768 ? Math.max(280, window.innerWidth - 66) : Math.round(Math.min(1240, window.innerWidth) * (window.innerWidth < 1024 ? 1 : 0.75) / 2 - 50), H = 160, L = 40, R = 8, T = 8, B = 24, n = trend.length;
    var vals = trend.map(function (x) { return x[key]; }), prev = compare ? trend.map(function (x) { return x["prev_" + key]; }) : [];
    var max = Math.max(1, Math.max.apply(null, vals.concat(prev)));
    var X = function (i) { return L + (n === 1 ? (W - L - R) / 2 : i * (W - L - R) / (n - 1)); }, Y = function (v) { return T + (H - T - B) * (1 - v / max); };
    var line = function (arr) { return arr.map(function (v, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); }).join(" "); };
    var ticks = [0, Math.round(max / 2), max].filter(function (v, i, a) { return a.indexOf(v) === i; });
    var lab = [0, Math.floor((n - 1) / 2), n - 1].filter(function (v, i, a) { return a.indexOf(v) === i; });
    var hit = trend.map(function (x, i) {
      var w = (W - L - R) / Math.max(n - 1, 1);
      return "<rect class='hit' x='" + (X(i) - w / 2).toFixed(1) + "' y='0' width='" + w.toFixed(1) + "' height='" + H + "' tabindex='0'><title>" + esc(S.day(x.day)) + ": " + x[key] + " " + title.toLowerCase() +
        (compare ? " (previous period, " + S.day(x.prev_day) + ": " + x["prev_" + key] + ")" : "") + "</title></rect>";
    }).join("");
    var total = vals.reduce(function (a, b) { return a + b; }, 0);
    return "<figure class='rchart'><figcaption><b>" + esc(title) + " per day</b>" + (compare ? "<span class='rlegend'><i class='now'></i>This period<i class='prev'></i>Previous period</span>" : "") + "</figcaption>" +
      (total === 0 && !(compare && prev.some(function (v) { return v; })) ? "<p class='note'>No " + esc(title.toLowerCase()) + " in this period.</p>" :
      "<svg viewBox='0 0 " + W + " " + H + "' role='img' aria-label='" + esc(title) + " per day, " + total + " in the period'>" +
      ticks.map(function (t) { return "<line class='grid' x1='" + L + "' x2='" + (W - R) + "' y1='" + Y(t).toFixed(1) + "' y2='" + Y(t).toFixed(1) + "'/><text class='ylab' x='" + (L - 6) + "' y='" + (Y(t) + 4).toFixed(1) + "'>" + t + "</text>"; }).join("") +
      lab.map(function (i) { return "<text class='xlab' x='" + X(i).toFixed(1) + "' y='" + (H - 6) + "'>" + esc(S.day(trend[i].day).replace(/ \d{4}$/, "")) + "</text>"; }).join("") +
      (compare ? "<path class='prev' d='" + line(prev) + "'/>" : "") + "<path class='now' d='" + line(vals) + "'/>" + hit + "</svg>") + "</figure>";
  }

  // ---------- the table: grouped counts, or the rows ----------
  function table(report, r, q) {
    var groupBy = q.get("group") || "", flag = q.get("flag") || "";
    var drill = flag ? "<p class='rdrill'>Showing: <b>" + esc(FLAG_TEXT[flag] || flag) + "</b> <a class='btn text' href='#/admin/reports/" + report + "?" + (function () { var p = new URLSearchParams(q.toString()); p.delete("flag"); p.delete("page"); return p.toString(); })() + "'>Show all</a></p>" : "";
    var groupSel = report === "inventory" ? "<label>Group by<select id='rgroup'><option value=''>No grouping (rows)</option>" +
      [["status_group", "Status"], ["make", "Make"], ["price_band", "Price band"], ["age_band", "Age on site"]].map(function (g) { return "<option value='" + g[0] + "'" + (groupBy === g[0] ? " selected" : "") + ">" + g[1] + "</option>"; }).join("") + "</select></label>" : "";
    // phones have no table headers to tap, so sorting is a menu there
    var sortSel = r.groups ? "" : "<label class='show-s rsort'>Sort by<select id='rsort'>" + r.columns.map(function (c) {
      return [true, false].map(function (d) { return "<option value='" + c + (d ? ":1" : ":0") + "'" + (r.sort === c && r.desc === d ? " selected" : "") + ">" + esc(G(c).label) + (d ? ", highest first" : ", lowest first") + "</option>"; }).join(""); }).join("") + "</select></label>";
    var tools = "<div class='rtools'>" + groupSel + sortSel + "<button type='button' class='btn ghost' id='rexport'>Export CSV</button></div>";
    var body;
    if (r.groups) {
      var gk = groupBy;
      body = r.groups.length ? "<div class='tablewrap'><table class='tbl cards'><thead><tr><th scope='col'>" + esc(G(gk).label) + "</th><th scope='col' title='" + esc(G("listings").def) + "'>Listings</th></tr></thead><tbody>" +
        r.groups.map(function (g) {
          var p = new URLSearchParams(q.toString()); p.delete("group"); p.delete("page"); if (g.value != null) p.set(gk, g.value);
          return "<tr><td data-label='" + esc(G(gk).label) + "'>" + esc(fmt(gk, g.value) || "None") + "</td><td data-label='Listings'><a href='#/admin/reports/" + report + "?" + p.toString() + "'>" + g.count.toLocaleString("en-US") + "</a></td></tr>";
        }).join("") + "</tbody></table></div>" : "<div class='empty'><b>No listings match these filters</b></div>";
    } else if (!r.rows.length) {
      body = "<div class='empty'><b>" + (report === "funnel" ? "No listings that have been live match these filters" : "No listings match these filters") + "</b><span>" +
        (flag ? "Nothing is " + esc((FLAG_TEXT[flag] || flag).toLowerCase()) + " with these filters." : "Change the filters or the period.") + "</span></div>";
    } else {
      body = "<div class='tablewrap'><table class='tbl cards'><thead><tr>" + r.columns.map(function (c) {
        var on = r.sort === c, p = new URLSearchParams(q.toString()); p.set("sort", c); p.set("desc", on && r.desc ? "0" : "1"); p.delete("page");
        return "<th scope='col'" + (on ? " aria-sort='" + (r.desc ? "descending" : "ascending") + "'" : "") + "><a href='#/admin/reports/" + report + "?" + p.toString() + "' title='" + esc(G(c).def) + "'>" + esc(G(c).label) + (on ? (r.desc ? " ▼" : " ▲") : "") + "</a></th>";
      }).join("") + "</tr></thead><tbody>" + r.rows.map(function (row) {
        return "<tr>" + r.columns.map(function (c) {
          var t = esc(fmt(c, row[c], row));
          if (c === "ref") t = "<a href='#/admin/car/" + row.id + "'>" + t + "</a>";
          return "<td data-label='" + esc(G(c).label) + "'>" + t + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>" + pager(report, r, q);
    }
    return "<section class='rtable' aria-label='Records'>" + drill + tools + "<p class='count'>" + (r.groups ? r.groups.length + " groups, " : "") + r.total.toLocaleString("en-US") + " listing" + (r.total === 1 ? "" : "s") + "</p>" + body + "</section>";
  }
  function pager(report, r, q) {
    var pages = Math.ceil(r.total / r.size); if (pages < 2) return "";
    var href = function (n) { var p = new URLSearchParams(q.toString()); p.set("page", n); return "#/admin/reports/" + report + "?" + p.toString(); };
    var out = [], last = 0;
    for (var n = 1; n <= pages; n++) if (n === 1 || n === pages || Math.abs(n - r.page) <= 1) {
      if (n - last > 1) out.push("<span class='gap'>…</span>");
      out.push(n === r.page ? "<span aria-current='page'>" + n + "</span>" : "<a href='" + href(n) + "'>" + n + "</a>"); last = n;
    }
    return "<nav class='pager' aria-label='Pages'>" + (r.page > 1 ? "<a href='" + href(r.page - 1) + "'>Previous</a>" : "") + out.join("") + (r.page < pages ? "<a href='" + href(r.page + 1) + "'>Next</a>" : "") + "</nav>";
  }

  // ---------- CSV: same columns and names as the screen, period and filters in the name and the first row ----------
  var FILTER_LABEL = { make: "Make", price_band: "Price band", status_group: "Status", seller_type: "Seller", age_band: "Age on site", q: "Search", flag: "Showing" };
  function filtersText(f) { return Object.keys(f).map(function (k) { return (FILTER_LABEL[k] || k) + "=" + (k === "flag" ? FLAG_TEXT[f[k]] || f[k] : k === "status_group" ? STATUS[f[k]] : f[k]); }).join("; ") || "none"; }
  function exportCsv(report, args, btn) {
    btn.disabled = true;
    S.rpc("admin_report", Object.assign({}, args, { p_export: true })).then(function (r) {
      var cell = function (s) { s = s == null ? "" : String(s); return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
      var name = head(report)[1];
      var lines = [[ "Saaz report: " + name, "Period " + r.from + " to " + r.to + " (East Africa Time)", "Filters: " + filtersText(r.filters), "Exported " + new Date(r.generated_at).toISOString() ].map(cell).join(",")];
      if (r.groups) {
        var gk = args.p_group;
        lines.push([G(gk).label, "Listings"].map(cell).join(","));
        r.groups.forEach(function (g) { lines.push([fmt(gk, g.value) || "None", g.count].map(cell).join(",")); });
      } else {
        lines.push(r.columns.map(function (c) { return cell(G(c).label); }).join(","));
        r.rows.forEach(function (row) { lines.push(r.columns.map(function (c) { return cell(plain(c, row[c], row)); }).join(",")); });
      }
      var slug = Object.keys(r.filters).map(function (k) { return k + "-" + String(r.filters[k]).replace(/[^A-Za-z0-9]+/g, ""); }).join("_");
      var file = "Saaz_" + name.replace(/ /g, "") + "_" + r.from + "_to_" + r.to + (slug ? "_" + slug : "") + (args.p_group ? "_by-" + args.p_group : "") + ".csv";
      var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" })); a.download = file;
      document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      S.toast("Exported " + (r.groups ? r.groups.length + " groups" : r.rows.length + " rows") + ". The export is recorded."); btn.disabled = false;
    }).catch(function (e) { S.toast(S.friendly(e), true); btn.disabled = false; });
  }

  // ---------- one report page ----------
  function reportPage(report) {
    return function (v, m, q) {
      return options().then(function () {
        if (!location.hash.split("?")[1]) {  // came from the rail or a link with no filters: bring back the ones in use
          var keep = recall(); if (Object.keys(keep).length) { S.go("#/admin/reports/" + report + "?" + new URLSearchParams(keep).toString()); return; }
        }
        store(q);
        var p = period(q), f = {};
        ["make", "price_band", "status_group", "seller_type", "age_band", "q", "flag"].forEach(function (k) { if (q.get(k)) f[k] = q.get(k); });
        var args = { p_report: report, p_from: p.from, p_to: p.to, p_compare: q.get("cmp") === "1", p_filters: f, p_group: report === "inventory" && q.get("group") ? q.get("group") : null,
          p_sort: q.get("sort") || null, p_desc: q.get("desc") !== "0", p_page: +(q.get("page") || 1), p_size: 25, p_export: false };
        return S.rpc("admin_report", args).then(function (r) {
          var h = head(report);
          shell(v, report, q, "<div class='sechead'><h1>" + esc(h[2]) + "</h1><p>" + esc(h[1]) + " · " + (report === "inventory" ? "Counts are right now; Added, Sold and Removed use the period. " : "") +
            "Period " + esc(S.day(r.from)) + " to " + esc(S.day(r.to)) + (r.compare ? " compared with " + esc(S.day(r.prev_from)) + " to " + esc(S.day(r.prev_to)) : "") +
            ". All dates East Africa Time. Live data, worked out " + new Date(r.generated_at).toLocaleTimeString("en-GB", { timeZone: "Africa/Kampala", hour: "2-digit", minute: "2-digit" }) + ".</p></div>" +
            controlBar(report, q, p) + kpis(report, r, q) +
            (r.trend ? "<div class='rtrend'>" + chart("Views", "views", r.trend, r.compare) + chart("Enquiries", "enquiries", r.trend, r.compare) + "</div>" : "") +
            table(report, r, q));
          var bar = S.$("#rbar");
          bar.range.onchange = function () { S.$$(".rcustom", bar).forEach(function (x) { x.hidden = bar.range.value !== "custom"; }); };
          bar.onsubmit = function (e) {
            e.preventDefault(); var o = S.form(bar), np = new URLSearchParams();
            KEEP.forEach(function (k) { if (o[k]) np.set(k, o[k]); });
            if (o.range !== "custom") { np.delete("from"); np.delete("to"); }
            else if (!o.from || !o.to || o.to < o.from) { S.toast("Choose a start and an end date, the end on or after the start.", true); return; }
            ["group", "sort", "desc"].forEach(function (k) { if (q.get(k)) np.set(k, q.get(k)); });
            S.go("#/admin/reports/" + report + "?" + np.toString());
          };
          var gs = S.$("#rgroup"); if (gs) gs.onchange = function () { var np = new URLSearchParams(q.toString()); np.delete("page"); if (gs.value) np.set("group", gs.value); else np.delete("group"); S.go("#/admin/reports/" + report + "?" + np.toString()); };
          var ss = S.$("#rsort"); if (ss) ss.onchange = function () { var v2 = ss.value.split(":"), np = new URLSearchParams(q.toString()); np.set("sort", v2[0]); np.set("desc", v2[1]); np.delete("page"); S.go("#/admin/reports/" + report + "?" + np.toString()); };
          S.$("#rexport").onclick = function () { exportCsv(report, args, S.$("#rexport")); };
        });
      });
    };
  }
  S.route("/admin/reports", function () { S.go("#/admin/reports/inventory"); }, "admin");
  REPORTS.forEach(function (r) { S.route("/admin/reports/" + r[0], reportPage(r[0]), "admin"); });
  S.route("/admin/reports/glossary", function (v, m, q) {
    return options().then(function () {
      var keys = Object.keys(opts.glossary).sort(function (a, b) { return G(a).label.localeCompare(G(b).label); });
      shell(v, "glossary", q, "<div class='sechead'><h1>What each number means</h1><p>Every report uses these definitions. Each one is worked out in one place in the database, so the same number never has two formulas.</p></div>" +
        "<dl class='rgloss'>" + keys.map(function (k) { return "<div><dt>" + esc(G(k).label) + "</dt><dd>" + esc(G(k).def) + "</dd></div>"; }).join("") + "</dl>");
    });
  }, "admin");
})();
