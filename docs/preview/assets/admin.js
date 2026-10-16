/* admin.js: Saaz staff sign-in and car management, backed by Supabase.
   Security lives in the database (supabase/schema.sql): row-level rules decide who can read or write.
   This page only offers the screens. */
(function () {
  var C = window.SAAZ || {};
  var $ = function (id) { return document.getElementById(id); };
  var show = function (id) { ["a-config", "a-login", "a-denied", "a-app"].forEach(function (x) { $(x).hidden = x !== id; }); };
  if (!C.supabaseUrl || !C.supabaseAnonKey || !window.supabase) { show("a-config"); return; }
  var db = window.supabase.createClient(C.supabaseUrl, C.supabaseAnonKey);
  var cars = [], editing = null, photos = [];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function msg(t) { $("a-msg").textContent = t || ""; }
  function photoUrl(p) { return C.supabaseUrl + "/storage/v1/object/public/car-photos/" + p; }
  function mask(ch) {
    ch = ch.toUpperCase().replace(/\s/g, "");
    if (ch.indexOf("•") >= 0) return ch;
    var i = ch.indexOf("-"), head = i > 0 ? ch.slice(0, i + 1) : ch.slice(0, 3);
    return head + "•••" + ch.slice(-4);
  }
  function friendly(e) {
    var m = (e && e.message) || String(e);
    if (/publish_needs_review/.test(m)) return "Can't publish: the car needs a Passed review with a date and shop, and plates confirmed hidden.";
    if (/duplicate key.*ref/.test(m)) return "That Saaz ref is already used.";
    if (/row-level security/.test(m)) return "Your account isn't allowed to do that.";
    return m;
  }

  async function start() {
    var s = (await db.auth.getSession()).data.session;
    if (!s) { show("a-login"); return; }
    var r = await db.from("admins").select("name").eq("user_id", s.user.id).maybeSingle();
    if (r.error || !r.data) { show("a-denied"); return; }
    $("a-who").textContent = r.data.name;
    show("a-app");
    load();
  }

  async function load() {
    var r = await db.from("cars").select("*").order("created_at", { ascending: false });
    if (r.error) { msg(friendly(r.error)); return; }
    cars = r.data;
    $("a-rows").innerHTML = cars.length ? cars.map(function (c) {
      return "<tr><td>" + esc(c.ref) + "</td><td>" + esc(c.year + " " + c.make + " " + c.model) + "</td><td class=n>" + Number(c.price_ugx).toLocaleString() +
        "</td><td>" + (c.source === "import" ? "Saaz import" : "Local") + "</td><td>" + esc(c.review_result || "Not reviewed") +
        "</td><td><span class='a-st " + c.status + "'>" + esc(c.status) + "</span></td><td class=a-row-act>" +
        "<button type=button data-edit='" + c.id + "'>Edit</button>" +
        (c.status === "published" ? "<button type=button data-set='" + c.id + "|sold'>Mark sold</button><button type=button data-set='" + c.id + "|draft'>Unpublish</button>" : "") +
        (c.status === "sold" ? "<button type=button data-set='" + c.id + "|draft'>Back to draft</button>" : "") +
        "<button type=button data-del='" + c.id + "'>Delete</button></td></tr>";
    }).join("") : "<tr><td colspan=7>No cars yet. Use Add a car.</td></tr>";
  }

  function nextRef() {
    var n = cars.reduce(function (m, c) { var k = parseInt(String(c.ref).replace(/\D/g, ""), 10); return isNaN(k) ? m : Math.max(m, k); }, 0);
    return "SZ-" + String(n + 1).padStart(4, "0");
  }
  function openForm(c) {
    editing = c || null; var f = $("a-form"); f.reset(); $("a-form-err").textContent = "";
    $("a-form-title").textContent = c ? "Edit " + c.ref : "Add a car";
    photos = c ? c.photos.slice() : [];
    if (c) {
      ["ref", "source", "make", "model", "year", "body", "fuel", "gearbox", "drive", "km", "cc", "colour", "price_ugx", "area", "seller", "chassis", "review_result", "review_date", "review_garage"]
        .forEach(function (k) { if (f.elements[k]) f.elements[k].value = c[k] == null ? "" : c[k]; });
      f.elements.findings.value = (c.findings || []).map(function (x) { return x.area + " | " + x.level + " | " + x.note; }).join("\n");
      f.elements.plates_hidden.checked = !!c.plates_hidden;
    } else f.elements.ref.value = nextRef();
    drawThumbs(); f.hidden = false; f.scrollIntoView({ behavior: "smooth" });
  }
  function drawThumbs() {
    $("a-thumbs").innerHTML = photos.map(function (p, i) {
      return "<figure><img src='" + esc(photoUrl(p)) + "' alt=''><button type=button data-rm='" + i + "' aria-label='Remove photo'>×</button></figure>";
    }).join("");
  }
  function toWebp(file) {
    return new Promise(function (ok, bad) {
      var img = new Image(); img.onload = function () {
        var s = Math.min(1, 1600 / Math.max(img.width, img.height)), cv = document.createElement("canvas");
        cv.width = Math.round(img.width * s); cv.height = Math.round(img.height * s);
        cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
        cv.toBlob(function (b) { b ? ok(b) : bad(new Error("Could not convert the photo")); }, "image/webp", 0.8);
      }; img.onerror = function () { bad(new Error("Could not read " + file.name)); };
      img.src = URL.createObjectURL(file);
    });
  }
  async function upload(files) {
    var ref = $("a-form").elements.ref.value || "unsorted";
    for (var i = 0; i < files.length; i++) {
      $("a-form-err").textContent = "Uploading photo " + (i + 1) + " of " + files.length + "…";
      try {
        var blob = await toWebp(files[i]);
        var path = ref + "/" + Date.now() + "-" + i + ".webp";
        var r = await db.storage.from("car-photos").upload(path, blob, { contentType: "image/webp" });
        if (r.error) throw r.error;
        photos.push(path); drawThumbs();
      } catch (e) { $("a-form-err").textContent = friendly(e); return; }
    }
    $("a-form-err").textContent = "";
  }
  function parseFindings(t) {
    return t.split("\n").map(function (l) { return l.trim(); }).filter(Boolean).map(function (l) {
      var p = l.split("|").map(function (x) { return x.trim(); });
      return { area: p[0] || "", level: /att/i.test(p[1] || "") ? "attention" : "note", note: p[2] || "" };
    });
  }
  async function save(status) {
    var f = $("a-form"), e = f.elements, num = function (k) { return e[k].value === "" ? null : Number(e[k].value); };
    var row = {
      ref: e.ref.value.trim().toUpperCase(), source: e.source.value, status: status, make: e.make.value.trim(), model: e.model.value.trim(),
      year: num("year"), body: e.body.value, fuel: e.fuel.value, gearbox: e.gearbox.value, drive: e.drive.value, km: num("km"), cc: num("cc"),
      colour: e.colour.value.trim() || null, price_ugx: num("price_ugx"), area: e.area.value.trim(), seller: e.seller.value, chassis: mask(e.chassis.value),
      review_result: e.review_result.value || null, review_date: e.review_date.value || null, review_garage: e.review_garage.value.trim() || null,
      findings: parseFindings(e.findings.value), photos: photos, plates_hidden: e.plates_hidden.checked
    };
    var r = editing ? await db.from("cars").update(row).eq("id", editing.id) : await db.from("cars").insert(row);
    if (r.error) { $("a-form-err").textContent = friendly(r.error); return; }
    f.hidden = true; msg(row.ref + (status === "published" ? " published." : " saved as draft.")); load();
  }

  $("a-login").addEventListener("submit", async function (ev) {
    ev.preventDefault(); $("a-login-err").textContent = "";
    var r = await db.auth.signInWithPassword({ email: $("a-email").value.trim(), password: $("a-pass").value });
    if (r.error) { $("a-login-err").textContent = "Email or password is wrong."; return; }
    start();
  });
  document.querySelectorAll("[data-signout]").forEach(function (b) { b.addEventListener("click", async function () { await db.auth.signOut(); show("a-login"); }); });
  $("a-new").addEventListener("click", function () { openForm(null); });
  $("a-cancel").addEventListener("click", function () { $("a-form").hidden = true; });
  $("a-files").addEventListener("change", function (ev) { upload(Array.prototype.slice.call(ev.target.files)); ev.target.value = ""; });
  $("a-thumbs").addEventListener("click", function (ev) { var i = ev.target.getAttribute("data-rm"); if (i != null) { photos.splice(+i, 1); drawThumbs(); } });
  $("a-form").addEventListener("submit", function (ev) { ev.preventDefault(); save(ev.submitter ? ev.submitter.getAttribute("data-status") : "draft"); });
  $("a-rows").addEventListener("click", async function (ev) {
    var t = ev.target, id;
    if ((id = t.getAttribute("data-edit"))) openForm(cars.find(function (c) { return c.id === id; }));
    if ((id = t.getAttribute("data-set"))) { var p = id.split("|"); var r = await db.from("cars").update({ status: p[1] }).eq("id", p[0]); msg(r.error ? friendly(r.error) : "Updated."); load(); }
    if ((id = t.getAttribute("data-del"))) {
      if (t.textContent !== "Confirm delete") { t.textContent = "Confirm delete"; return; }
      var r2 = await db.from("cars").delete().eq("id", id); msg(r2.error ? friendly(r2.error) : "Deleted."); load();
    }
  });
  start();
})();
