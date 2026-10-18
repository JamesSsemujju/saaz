/* cars.js: filter and sort the car list on the /cars/ page (same filter bar, grid and card as the marketplace).
   The cards are already in the HTML; this only shows, hides and reorders them, so the page works without JavaScript. */
(function () {
  var form = document.getElementById("carfilter");
  var list = document.getElementById("carlist");
  if (!form || !list) return;
  var cards = Array.prototype.slice.call(list.querySelectorAll(".car"));
  if (!cards.length) return;
  var count = document.getElementById("carcount");
  var none = document.getElementById("nomatch");
  var sort = document.getElementById("carsort");
  form.hidden = false;

  function inBand(v, band) {
    if (!band) return true;
    var p = band.split("-"), lo = +p[0], hi = p[1] === "" ? Infinity : +p[1];
    return v >= lo && v <= hi;
  }
  function apply() {
    var f = {};
    Array.prototype.forEach.call(form.elements, function (el) { if (el.name) f[el.name] = el.value; });
    var shown = 0;
    cards.forEach(function (c) {
      var d = c.dataset;
      var ok = (!f.make || d.make === f.make) && (!f.body || d.body === f.body) &&
               (!f.fuel || d.fuel === f.fuel) && (!f.gearbox || d.gearbox === f.gearbox) &&
               inBand(+d.price, f.price) && inBand(+d.year, f.year);
      c.hidden = !ok;
      if (ok) shown++;
    });
    count.textContent = shown === 1 ? "1 car" : shown + " cars";
    none.hidden = shown !== 0;
    var key = sort.value;
    cards.slice().sort(function (a, b) {
      var A = a.dataset, B = b.dataset;
      if (key === "price-asc") return A.price - B.price;
      if (key === "price-desc") return B.price - A.price;
      if (key === "km") return A.km - B.km;
      if (key === "year") return B.year - A.year;
      return B.date.localeCompare(A.date);
    }).forEach(function (c) { list.appendChild(c); });
  }
  form.addEventListener("change", apply);
  form.addEventListener("reset", function () { setTimeout(apply, 0); });
  sort.addEventListener("change", apply);
  apply();
})();
