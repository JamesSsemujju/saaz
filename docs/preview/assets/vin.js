/* vin.js: free VIN decoder on the Vehicle history page.
   Source: the US NHTSA vPIC public API (no key, no cost). The VIN goes from the visitor's browser
   straight to NHTSA; Saaz stores nothing. Japanese frame numbers and number plates are not supported
   by this API, so they get a clear message instead of a wrong answer.
   To switch to a paid decoder later, replace decode() and keep the same field list. */
(function () {
  var API = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/";
  var FIELDS = [
    ["Make", "Make"], ["Model", "Model"], ["ModelYear", "Model year"], ["Trim", "Trim"], ["Series", "Series"],
    ["BodyClass", "Body"], ["FuelTypePrimary", "Fuel"], ["DisplacementL", "Engine (litres)"],
    ["DriveType", "Drive"], ["TransmissionStyle", "Gearbox"], ["PlantCountry", "Built in"]
  ];
  var form = document.getElementById("vinform");
  if (!form) return;
  var input = document.getElementById("vin");
  var out = document.getElementById("vinresult");
  var btn = form.querySelector("button");

  function clean(s) { return (s || "").toUpperCase().replace(/[\s.]/g, ""); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function say(kind, title, body) {
    out.innerHTML = "";
    var box = el("div", "vin-msg " + kind);
    box.appendChild(el("b", null, title));
    if (body) box.appendChild(el("span", null, body));
    out.appendChild(box);
  }
  // ISO 3779 check digit (position 9). Many cars built for markets outside North America do not use it.
  function checkDigitOk(v) {
    var map = { A:1,B:2,C:3,D:4,E:5,F:6,G:7,H:8,J:1,K:2,L:3,M:4,N:5,P:7,R:9,S:2,T:3,U:4,V:5,W:6,X:7,Y:8,Z:9 };
    var w = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2], sum = 0;
    for (var i = 0; i < 17; i++) { var c = v[i]; sum += (/\d/.test(c) ? +c : map[c]) * w[i]; }
    var r = sum % 11; return (r === 10 ? "X" : String(r)) === v[8];
  }
  function classify(v) {
    if (/^[A-HJ-NPR-Z0-9]{17}$/.test(v)) return "vin";
    if (v.length === 17 && /[IOQ]/.test(v)) return "ioq";
    if (/^[A-Z0-9]{2,8}-\d{3,8}$/.test(v)) return "frame";
    if (/^U[A-Z]{1,3}\d{2,4}[A-Z]{0,2}$/.test(v)) return "plate";
    return "unknown";
  }
  function show(v, r) {
    out.innerHTML = "";
    var head = el("div", "vin-head");
    head.appendChild(el("span", "vin-code", v));
    head.appendChild(el("b", null, [r.ModelYear, r.Make, r.Model].filter(Boolean).join(" ") || "Decoded"));
    out.appendChild(head);
    var dl = el("dl", "specs");
    FIELDS.forEach(function (f) {
      var val = (r[f[0]] || "").trim();
      if (!val || val === "Not Applicable") return;
      var d = el("div"); d.appendChild(el("dt", null, f[1])); d.appendChild(el("dd", null, val)); dl.appendChild(d);
    });
    out.appendChild(dl);
    if (!checkDigitOk(v)) out.appendChild(el("p", "note", "The check digit (9th character) does not add up. That is common on cars built for markets outside North America, but check the VIN was typed correctly."));
    out.appendChild(el("p", "note", "Source: NHTSA vPIC public decoder, " + new Date().toLocaleString() + ". This is the factory specification for this VIN, not the car's history, condition or ownership."));
  }
  function decode(v) {
    var ctl = "AbortController" in window ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 12000);
    return fetch(API + encodeURIComponent(v) + "?format=json", ctl ? { signal: ctl.signal } : {})
      .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function (j) { clearTimeout(t); return (j.Results || [])[0] || {}; });
  }
  function run(raw) {
    var v = clean(raw);
    input.value = v;
    if (!v) return;
    var kind = classify(v);
    if (kind === "ioq") return say("warn", "That can't be a VIN", "VINs never use the letters I, O or Q. Check for a 1 or a 0 instead.");
    if (kind === "frame") return say("info", "This looks like a Japanese frame number", "Cars built for Japan carry a frame number such as ZSU60-0012345 instead of a 17-character VIN. The free decoder can't read these yet. A Saaz review will record it.");
    if (kind === "plate") return say("info", "This looks like a number plate", "Plate lookups are not available. Enter the 17-character VIN from the car or its logbook.");
    if (kind !== "vin") return say("warn", "Not a VIN", "A VIN has exactly 17 letters and numbers. You entered " + v.length + ".");
    btn.disabled = true;
    say("info", "Decoding " + v + "...", "");
    decode(v).then(function (r) {
      if (!r.Make && !r.Model) return say("warn", "No match found", "The decoder has no record of this VIN. Check it against the logbook.");
      show(v, r);
    }).catch(function () {
      say("warn", "The decoder didn't answer", "The free decoder is busy or your connection dropped. Try again in a minute.");
    }).then(function () { btn.disabled = false; });
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var v = clean(input.value);
    try { history.replaceState(null, "", "?vin=" + encodeURIComponent(v) + "#decode"); } catch (err) {}
    run(v);
  });
  var q = new URLSearchParams(location.search).get("vin");
  if (q) {
    run(q);
    var sec = document.getElementById("decode");
    if (sec) window.addEventListener("load", function () { setTimeout(function () { sec.scrollIntoView(); }, 50); });
  }
})();
