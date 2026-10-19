/* app-reports.js: Admin > Reports. Each report answers one question.
   Same layout for every report: the question, the control bar, the key numbers, the trend, the table.
   Every number is computed in the database (admin_report, parts 16 and 17); this page only shows it.
   Every key number and every group count opens the rows behind it. Every table sorts, pages and exports to CSV. */
(function () {
  var S = window.Saaz, esc = S.esc;
  // id, name, question, filters on the control bar, groupings, trend measures, note under the heading
  var REPORTS = [
    { id: "inventory", name: "Inventory", q: "What is on the site right now, and is it healthy?", filters: ["make", "price_band", "status_group", "seller_type", "age_band"],
      groups: [["status_group", "Status"], ["make", "Make"], ["price_band", "Price band"], ["age_band", "Age on site"]], note: "Counts are right now; Added, Sold and Removed use the period. " },
    { id: "funnel", name: "Listing funnel", q: "Do listings get seen and acted on?", filters: ["make", "price_band", "status_group", "seller_type"], trend: [["views", "Views"], ["enquiries", "Enquiries"]] },
    { id: "inspections", name: "Inspections and garages", q: "Are cars inspected quickly, and which garages need attention?", filters: ["make", "price_band", "garage", "scope"],
      groups: [["garage", "Garage"], ["scope", "Scope"]], trend: [["requested", "Inspections requested"], ["issued", "Reports issued"]] },
    { id: "deals", name: "Deals and sales", q: "Do offers become sales, and how far below asking do they agree?", filters: ["make", "model", "price_band"],
      groups: [["model", "Model"], ["make", "Make"], ["price_band", "Price band"]], groupLabel: "What Saaz has learned, by", trend: [["offers", "Offers"], ["agreed", "Deals agreed"]],
      note: "The usual gap below asking is learned from every deal agreed so far, by model, make and price band. " }
  ];
  var FILTERS = ["make", "model", "price_band", "status_group", "seller_type", "age_band", "garage", "scope", "q"];
  var KEEP = ["range", "from", "to", "cmp"].concat(FILTERS);  // these follow you between reports
  var STATUS = { draft: "Draft", pending: "Pending", live: "Live", sold: "Sold", expired: "Expired", removed: "Removed" };
  var FLAG_TEXT = { live_now: "Live now", pending_now: "Pending now", draft_now: "Drafts", expired_now: "Expired now", added: "Added in the period", sold: "Sold in the period",
    removed: "Removed in the period", stale: "Not updated in 30 days", no_photos: "No photos", has_views: "Viewed in the period",
    has_saves: "Saved in the period", has_enquiries: "With enquiries in the period", first_enquiry: "First enquiry in the period",
    requested: "Requested in the period", issued: "Issued in the period", open_now: "Open now", waiting_7d: "Waiting over 7 days", objected: "Saaz objected",
    pass: "Passed in the period", conditional: "Conditional in the period", fail: "Failed in the period",
    line_offers: "Offered to garages in the period", timeouts: "Time-outs in the period", line_ended: "Garage line turns ended in the period",
    offered: "Offers made in the period", agreed: "Agreed in the period", completed: "Completed in the period", lost: "Ended without a deal in the period",
    agreed_ever: "Every agreed deal so far", expected: "Cars on sale: expected agreed price" };
  var ROWS = { listings: ["listing", "listings"], inspections: ["inspection", "inspections"], garage_line: ["garage line turn", "garage line turns"],
    deals: ["deal", "deals"], expected: ["car on sale", "cars on sale"] };
  var MONEY = ["price", "similar_median", "first_offer", "asking", "agreed_amount", "expected_price"];
  var PCT = ["gap_pct", "typical_gap", "median_gap", "gap_p25", "gap_p75", "timeout_rate", "pass_rate", "agree_rate"];
  var DATES = ["updated_at", "created_at", "requested_at", "issued_at", "opened_at", "offer_at"];
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
  function optLabel(list, v) { var o = (list || []).filter(function (x) { return x.value === v; })[0]; return o ? o.label : v; }
  function fmt(k, v, row) {
    if (k === "learned" && v === false) return "Not yet: fewer than 3 deals";
    if (v == null || v === "") return "";
    if (MONEY.indexOf(k) >= 0) return S.money(row && row.currency, v);
    if (PCT.indexOf(k) >= 0) return v + "%";
    if (DATES.indexOf(k) >= 0) return S.day(v);
    if (k === "status_group") return STATUS[v] || v;
    if (["status", "insp_status", "deal_status", "line_status", "verdict", "scope"].indexOf(k) >= 0) return k === "insp_status" && v === "draft" ? "In progress" : S.label(v);
    if (k === "price_vs_similar") return (v > 0 ? "+" : "") + v + "%";
    if (k === "gap_vs_typical") return (v > 0 ? "+" : "") + v + " points";
    if (k === "enquiry_rate") return v + " per 100";
    if (k === "objected") return v ? "Yes" : "";
    if (k === "learned") return v ? "Yes" : "Not yet: fewer than 3 deals";
    if (k === "garage") return optLabel(opts.garages, v);
    if (k === "model") return optLabel(opts.models, v);
    return typeof v === "number" ? v.toLocaleString("en-US") : String(v);
  }
  function plain(k, v, row) { return MONEY.indexOf(k) >= 0 ? (v == null ? "" : String(v)) : fmt(k, v, row); }  // CSV keeps money as plain numbers
  function cfg(report) { return REPORTS.filter(function (r) { return r.id === report; })[0]; }
  function link(report, p) { return "#/admin/reports/" + report + "?" + p.toString(); }

  // ---------- the page shell: report rail on the left, the report on the right ----------
  S.reportShell = function (v, at, q, html) { shell(v, at, q, html); };  // the core shows a failing report inside the reports layout
  function shell(v, at, q, html) {
    var qs = keepQuery(q);
    var rail = "<nav class='adminside' data-ref='report-menu' aria-label='Reports'><div class='navgroup'><a href='#/admin'>‹ Admin</a></div><div class='navgroup'><b>Reports</b>" +
      REPORTS.map(function (r) { return "<a href='#/admin/reports/" + r.id + (qs ? "?" + qs : "") + "'" + (r.id === at ? " aria-current='page'" : "") + ">" + r.name + "</a>"; }).join("") +
      "</div><div class='navgroup'><a href='#/admin/reports/glossary" + (qs ? "?" + qs : "") + "'" + (at === "glossary" ? " aria-current='page'" : "") + ">Glossary</a></div></nav>";
    var phone = "<label class='adminjump'>Report<select onchange='location.hash=this.value'>" + REPORTS.map(function (r) { return [r.id, r.name]; }).concat([["glossary", "Glossary"]]).map(function (r) {
      return "<option value='#/admin/reports/" + r[0] + (qs ? "?" + qs : "") + "'" + (r[0] === at ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "<option value='#/admin'>Back to Admin</option></select></label>";
    v.innerHTML = "<div class='adminwrap'>" + rail + "<div class='adminmain'>" + phone + html + "</div></div>";
  }

  // ---------- the control bar: one for every report, with that report's filters ----------
  function controlBar(c, q, p) {
    var sel = function (name, label, list, all) {
      return "<label>" + label + "<select name='" + name + "'><option value=''>" + all + "</option>" + list.map(function (x) {
        var val = typeof x === "object" ? x.value : x, lab = typeof x === "object" ? x.label : x;
        return "<option value='" + esc(val) + "'" + (q.get(name) === String(val) ? " selected" : "") + ">" + esc(lab) + "</option>"; }).join("") + "</select></label>";
    };
    var F = {
      make: function () { return sel("make", "Make", opts.makes, "Any make"); },
      model: function () { return sel("model", "Model", opts.models, "Any model"); },
      price_band: function () { return sel("price_band", "Price band", opts.price_bands, "Any price"); },
      status_group: function () { return sel("status_group", "Status", opts.status_groups.map(function (x) { return { value: x, label: STATUS[x] }; }), "Any status"); },
      seller_type: function () { return sel("seller_type", "Seller", [{ value: "private", label: "Private sellers" }, { value: "saaz", label: "Saaz-owned" }], "Any seller"); },
      age_band: function () { return sel("age_band", "Age on site", opts.age_bands, "Any age"); },
      garage: function () { return sel("garage", "Garage", opts.garages, "Any garage"); },
      scope: function () { return sel("scope", "Scope", opts.scopes.map(function (x) { return { value: x, label: S.label(x) }; }), "Any scope"); }
    };
    var ranges = [["today", "Today"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["custom", "Custom"]];
    return "<form id='rbar' class='filters' data-ref='report-controls' aria-label='Report controls'>" +
      "<label>Period<select name='range'>" + ranges.map(function (r) { return "<option value='" + r[0] + "'" + (p.range === r[0] || (q.get("range") === "custom" && r[0] === "custom") ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "</select></label>" +
      "<label class='rcustom'" + (q.get("range") === "custom" ? "" : " hidden") + ">From<input type='date' name='from' value='" + p.from + "' max='" + opts.today + "'></label>" +
      "<label class='rcustom'" + (q.get("range") === "custom" ? "" : " hidden") + ">To<input type='date' name='to' value='" + p.to + "' max='" + opts.today + "'></label>" +
      c.filters.map(function (k) { return F[k](); }).join("") +
      "<label>Search<input name='q' value='" + esc(q.get("q") || "") + "' placeholder='Ref, car or name'></label>" +
      "<label class='inline'><input type='checkbox' name='cmp' value='1'" + (q.get("cmp") === "1" ? " checked" : "") + "> Compare to previous period</label>" +
      "<button class='btn'>Apply</button></form>";
  }

  // ---------- key numbers: one row; each opens its rows ----------
  function kpis(c, r, q) {
    return "<div class='stats rkpis' data-ref='report-numbers'>" + r.kpis.map(function (k) {
      var g = G(k.key), p = new URLSearchParams(q.toString()); p.set("flag", k.flag); p.delete("page"); p.delete("group"); p.delete("sort"); p.delete("desc");
      var change = "";
      if (r.compare && k.prev !== undefined) {
        var d = k.value == null || k.prev == null ? null : Math.round((k.value - k.prev) * 10) / 10;
        change = "<small>Previous: " + (k.prev == null ? "none" : fmt(k.key, k.prev)) + (d == null || d === 0 ? "" : " (" + (d > 0 ? "+" : "") + d.toLocaleString("en-US") + ")") + "</small>";
      }
      return "<a href='" + link(c.id, p) + "' title='" + esc(g.def) + "'" + (q.get("flag") === k.flag ? " aria-current='true'" : "") + ">" +
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
      return "<rect class='hit' x='" + (X(i) - w / 2).toFixed(1) + "' y='0' width='" + w.toFixed(1) + "' height='" + H + "' tabindex='0'><title>" + esc(S.day(x.day)) + ": " + x[key] + " " + esc(title.toLowerCase()) +
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

  // ---------- the table: grouped numbers, or the rows ----------
  function rowLink(c, row) {
    var lid = row.listing_id || row.id;
    if (c === "ref") return "#/admin/car/" + lid;
    if (c === "doc_no" && lid) return "#/admin/car/" + lid;  // the car's admin page lists its inspections
    return null;
  }
  function groupCols(r) { return r.group_columns || [{ key: "count", label: "Listings", def: G("listings").def, flag: "" }]; }
  function table(c, r, q) {
    var groupBy = q.get("group") || "", flag = q.get("flag") || "", kind = r.rows_kind || "listings";
    var drill = flag ? "<p class='rdrill'>Showing: <b>" + esc(FLAG_TEXT[flag] || flag) + "</b> <a class='btn text' href='" + link(c.id, (function () { var p = new URLSearchParams(q.toString()); p.delete("flag"); p.delete("page"); p.delete("sort"); p.delete("desc"); return p; })()) + "'>Show all</a></p>" : "";
    var groupSel = c.groups ? "<label>" + (c.groupLabel || "Group by") + "<select id='rgroup'><option value=''>No grouping (rows)</option>" +
      c.groups.map(function (g) { return "<option value='" + g[0] + "'" + (groupBy === g[0] ? " selected" : "") + ">" + g[1] + "</option>"; }).join("") + "</select></label>" : "";
    var extra = c.id === "deals" && flag !== "expected" ? "<a class='btn ghost' href='" + link(c.id, (function () { var p = new URLSearchParams(q.toString()); p.set("flag", "expected"); p.delete("group"); p.delete("page"); p.delete("sort"); p.delete("desc"); return p; })()) + "'>Expected prices for cars on sale</a>" : "";
    // phones have no table headers to tap, so sorting is a menu there
    var sortSel = r.groups ? "" : "<label class='show-s rsort'>Sort by<select id='rsort'>" + r.columns.map(function (col) {
      return [true, false].map(function (d) { return "<option value='" + col + (d ? ":1" : ":0") + "'" + (r.sort === col && r.desc === d ? " selected" : "") + ">" + esc(G(col).label) + (d ? ", highest first" : ", lowest first") + "</option>"; }).join(""); }).join("") + "</select></label>";
    var tools = "<div class='rtools'>" + groupSel + sortSel + extra + "<button type='button' class='btn ghost' id='rexport'>Export CSV</button></div>";
    var body, count;
    if (r.groups) {
      var gk = groupBy, gcols = groupCols(r);
      count = r.groups.length + " group" + (r.groups.length === 1 ? "" : "s");
      body = r.groups.length ? "<div class='tablewrap'><table class='tbl cards'><thead><tr><th scope='col'>" + esc((c.groups.filter(function (g) { return g[0] === gk; })[0] || [0, gk])[1]) + "</th>" +
        gcols.map(function (col) { return "<th scope='col' title='" + esc(col.def || G(col.key).def) + "'>" + esc(col.label || G(col.key).label) + "</th>"; }).join("") + "</tr></thead><tbody>" +
        r.groups.map(function (g) {
          var name = g.label || fmt(gk, g.value) || "None";
          return "<tr><td data-label='" + esc((c.groups.filter(function (x) { return x[0] === gk; })[0] || [0, gk])[1]) + "'>" + esc(name) + "</td>" + gcols.map(function (col) {
            var v = g[col.key], t = esc(fmt(col.key, v));
            if (col.flag !== undefined && v) {  // a count: open the rows behind it
              var p = new URLSearchParams(q.toString()); p.delete("group"); p.delete("page"); p.delete("sort"); p.delete("desc");
              if (g.value != null) p.set(gk, g.value); if (col.flag) p.set("flag", col.flag); else p.delete("flag");
              t = "<a href='" + link(c.id, p) + "'>" + t + "</a>";
            }
            return "<td data-label='" + esc(col.label || G(col.key).label) + "'>" + t + "</td>";
          }).join("") + "</tr>";
        }).join("") + "</tbody></table></div>" : "<div class='empty'><b>Nothing to group with these filters</b><span>" + (c.id === "deals" ? "No deal has been agreed yet for these cars, so there is nothing to learn from." : "Change the filters or the period.") + "</span></div>";
    } else {
      count = r.total.toLocaleString("en-US") + " " + ROWS[kind][r.total === 1 ? 0 : 1];
      if (!r.rows.length) {
        body = "<div class='empty'><b>No " + ROWS[kind][1] + (flag ? ": " + esc((FLAG_TEXT[flag] || flag).toLowerCase()) : " in this period") + "</b><span>Change the filters or the period.</span></div>";
      } else {
        body = "<div class='tablewrap'><table class='tbl cards'><thead><tr>" + r.columns.map(function (col) {
          var on = r.sort === col, p = new URLSearchParams(q.toString()); p.set("sort", col); p.set("desc", on && r.desc ? "0" : "1"); p.delete("page");
          return "<th scope='col'" + (on ? " aria-sort='" + (r.desc ? "descending" : "ascending") + "'" : "") + "><a href='" + link(c.id, p) + "' title='" + esc(G(col).def) + "'>" + esc(G(col).label) + (on ? (r.desc ? " ▼" : " ▲") : "") + "</a></th>";
        }).join("") + "</tr></thead><tbody>" + r.rows.map(function (row) {
          return "<tr>" + r.columns.map(function (col) {
            var t = esc(fmt(col, row[col], row)), h = t && rowLink(col, row);
            return "<td data-label='" + esc(G(col).label) + "'>" + (h ? "<a href='" + h + "'>" + t + "</a>" : t) + "</td>";
          }).join("") + "</tr>";
        }).join("") + "</tbody></table></div>" + pager(c, r, q);
      }
    }
    return "<section class='rtable' data-ref='report-table' aria-label='Records'>" + drill + tools + "<p class='count'>" + count + "</p>" + body + "</section>";
  }
  function pager(c, r, q) {
    var pages = Math.ceil(r.total / r.size); if (pages < 2) return "";
    var href = function (n) { var p = new URLSearchParams(q.toString()); p.set("page", n); return link(c.id, p); };
    var out = [], last = 0;
    for (var n = 1; n <= pages; n++) if (n === 1 || n === pages || Math.abs(n - r.page) <= 1) {
      if (n - last > 1) out.push("<span class='gap'>…</span>");
      out.push(n === r.page ? "<span aria-current='page'>" + n + "</span>" : "<a href='" + href(n) + "'>" + n + "</a>"); last = n;
    }
    return "<nav class='pager' aria-label='Pages'>" + (r.page > 1 ? "<a href='" + href(r.page - 1) + "'>Previous</a>" : "") + out.join("") + (r.page < pages ? "<a href='" + href(r.page + 1) + "'>Next</a>" : "") + "</nav>";
  }

  // ---------- CSV: same columns and names as the screen, period and filters in the name and the first row ----------
  var FILTER_LABEL = { make: "Make", model: "Model", price_band: "Price band", status_group: "Status", seller_type: "Seller", age_band: "Age on site", garage: "Garage", scope: "Scope", q: "Search", flag: "Showing" };
  function filtersText(f) { return Object.keys(f).map(function (k) { return (FILTER_LABEL[k] || k) + "=" + (k === "flag" ? FLAG_TEXT[f[k]] || f[k] : k === "status_group" ? STATUS[f[k]] : fmt(k, f[k])); }).join("; ") || "none"; }
  function exportCsv(c, args, btn) {
    btn.disabled = true;
    S.rpc("admin_report", Object.assign({}, args, { p_export: true })).then(function (r) {
      var cell = function (s) { s = s == null ? "" : String(s); return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
      var lines = [[ "Saaz report: " + c.name, "Period " + r.from + " to " + r.to + " (East Africa Time)", "Filters: " + filtersText(r.filters), "Exported " + new Date(r.generated_at).toISOString() ].map(cell).join(",")];
      if (r.groups) {
        var gk = args.p_group, gcols = groupCols(r);
        lines.push([(c.groups.filter(function (g) { return g[0] === gk; })[0] || [0, gk])[1]].concat(gcols.map(function (col) { return col.label || G(col.key).label; })).map(cell).join(","));
        r.groups.forEach(function (g) { lines.push([g.label || fmt(gk, g.value) || "None"].concat(gcols.map(function (col) { return plain(col.key, g[col.key]); })).map(cell).join(",")); });
      } else {
        lines.push(r.columns.map(function (col) { return cell(G(col).label); }).join(","));
        r.rows.forEach(function (row) { lines.push(r.columns.map(function (col) { return cell(plain(col, row[col], row)); }).join(",")); });
      }
      var slug = Object.keys(r.filters).map(function (k) { return k + "-" + String(k === "garage" ? fmt(k, r.filters[k]) : r.filters[k]).replace(/[^A-Za-z0-9]+/g, ""); }).join("_");
      var file = "Saaz_" + c.name.split(" ").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join("") + "_" + r.from + "_to_" + r.to + (slug ? "_" + slug : "") + (args.p_group ? "_by-" + args.p_group : "") + ".csv";
      var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" })); a.download = file;
      document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      S.toast("Exported " + (r.groups ? r.groups.length + " groups" : r.rows.length + " rows") + ". The export is recorded."); btn.disabled = false;
    }).catch(function (e) { S.toast(S.friendly(e), true); btn.disabled = false; });
  }

  // ---------- one report page ----------
  function reportPage(c) {
    return function (v, m, q) {
      return options().then(function () {
        if (!location.hash.split("?")[1]) {  // came from the rail or a link with no filters: bring back the ones in use
          var keep = recall(); if (Object.keys(keep).length) { S.go("#/admin/reports/" + c.id + "?" + new URLSearchParams(keep).toString()); return; }
        }
        store(q);
        var p = period(q), f = {};
        c.filters.concat(["q", "flag"]).forEach(function (k) { if (q.get(k)) f[k] = q.get(k); });
        var group = c.groups && q.get("group") && c.groups.some(function (g) { return g[0] === q.get("group"); }) ? q.get("group") : null;
        var args = { p_report: c.id, p_from: p.from, p_to: p.to, p_compare: q.get("cmp") === "1", p_filters: f, p_group: group,
          p_sort: q.get("sort") || null, p_desc: q.get("desc") !== "0", p_page: +(q.get("page") || 1), p_size: 25, p_export: false };
        return S.rpc("admin_report", args).then(function (r) {
          shell(v, c.id, q, "<div class='sechead'><h1>" + esc(c.q) + "</h1><p>" + esc(c.name) + " · " + esc(c.note || "") +
            "Period " + esc(S.day(r.from)) + " to " + esc(S.day(r.to)) + (r.compare ? " compared with " + esc(S.day(r.prev_from)) + " to " + esc(S.day(r.prev_to)) : "") +
            ". All dates East Africa Time. Live data, worked out " + new Date(r.generated_at).toLocaleTimeString("en-GB", { timeZone: "Africa/Kampala", hour: "2-digit", minute: "2-digit" }) + ".</p></div>" +
            controlBar(c, q, p) + kpis(c, r, q) +
            (r.trend && c.trend ? "<div class='rtrend' data-ref='report-trend'>" + c.trend.map(function (t) { return chart(t[1], t[0], r.trend, r.compare); }).join("") + "</div>" : "") +
            table(c, r, q));
          var bar = S.$("#rbar");
          bar.range.onchange = function () { S.$$(".rcustom", bar).forEach(function (x) { x.hidden = bar.range.value !== "custom"; }); };
          bar.onsubmit = function (e) {
            e.preventDefault(); var o = S.form(bar), np = new URLSearchParams();
            // filters this report doesn't show are kept as they were, so they still apply when you go back to a report that has them
            KEEP.forEach(function (k) { if (o[k] !== undefined) { if (o[k]) np.set(k, o[k]); } else if (q.get(k)) np.set(k, q.get(k)); });
            if (o.range !== "custom") { np.delete("from"); np.delete("to"); }
            else if (!o.from || !o.to || o.to < o.from) { S.toast("Choose a start and an end date, the end on or after the start.", true); return; }
            if (!o.cmp) np.delete("cmp");
            ["group", "sort", "desc", "flag"].forEach(function (k) { if (q.get(k)) np.set(k, q.get(k)); });
            S.go("#/admin/reports/" + c.id + "?" + np.toString());
          };
          var gs = S.$("#rgroup"); if (gs) gs.onchange = function () { var np = new URLSearchParams(q.toString()); ["page", "sort", "desc", "flag"].forEach(function (k) { np.delete(k); }); if (gs.value) np.set("group", gs.value); else np.delete("group"); S.go(link(c.id, np)); };
          var ss = S.$("#rsort"); if (ss) ss.onchange = function () { var v2 = ss.value.split(":"), np = new URLSearchParams(q.toString()); np.set("sort", v2[0]); np.set("desc", v2[1]); np.delete("page"); S.go(link(c.id, np)); };
          S.$("#rexport").onclick = function () { exportCsv(c, args, S.$("#rexport")); };
        });
      });
    };
  }
  S.route("/admin/reports", function () { S.go("#/admin/reports/inventory"); }, "admin");
  REPORTS.forEach(function (c) { S.route("/admin/reports/" + c.id, reportPage(c), "admin"); });
  S.route("/admin/reports/glossary", function (v, m, q) {
    return options().then(function () {
      var keys = Object.keys(opts.glossary).sort(function (a, b) { return G(a).label.localeCompare(G(b).label); });
      shell(v, "glossary", q, "<div class='sechead'><h1>What each number means</h1><p>Every report uses these definitions. Each one is worked out in one place in the database, so the same number never has two formulas.</p></div>" +
        "<dl class='rgloss'>" + keys.map(function (k) { return "<div><dt>" + esc(G(k).label) + "</dt><dd>" + esc(G(k).def) + "</dd></div>"; }).join("") + "</dl>");
    });
  }, "admin");
})();
