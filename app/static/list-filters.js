(function () {
  function root() {
    return document.getElementById("list-filters");
  }

  function cards() {
    return Array.from(document.querySelectorAll("#property-list .property-card"));
  }

  function parseNum(value) {
    if (value == null || String(value).trim() === "") return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function selectedPortals(form) {
    return Array.from(form.querySelectorAll('[data-list-filter="portal"]:checked')).map(function (el) {
      return el.value;
    });
  }

  function activeCount(form) {
    var count = selectedPortals(form).length > 0 ? 1 : 0;
    if ((form.querySelector('[data-list-filter="town"]') || {}).value) count += 1;
    if ((form.querySelector('[data-list-filter="price_min"]') || {}).value) count += 1;
    if ((form.querySelector('[data-list-filter="price_max"]') || {}).value) count += 1;
    if ((form.querySelector('[data-list-filter="size_min"]') || {}).value) count += 1;
    var withdrawn = form.querySelector('[data-list-filter="withdrawn_only"]');
    if (withdrawn && withdrawn.checked) count += 1;
    return count;
  }

  function updateHint(form) {
    var hint = document.querySelector("[data-list-filters-hint]");
    var countEl = document.querySelector("[data-list-filters-count]");
    var n = activeCount(form);
    var base = hint ? hint.getAttribute("data-default-hint") : "";
    if (!base && hint) {
      base = hint.textContent.trim();
      hint.setAttribute("data-default-hint", base);
    }
    if (hint) {
      hint.textContent = n
        ? n + (n === 1 ? " filtro activo" : " filtros activos")
        : base;
    }
    if (countEl) {
      var visible = cards().filter(function (card) { return !card.hidden; }).length;
      var total = cards().length;
      countEl.textContent = n ? ("Mostrando " + visible + " de " + total) : "";
    }
  }

  function applyFilters() {
    var panel = root();
    if (!panel) return;
    var form = document.getElementById("list-filters-form");
    if (!form) return;

    var portals = selectedPortals(form);
    var town = (form.querySelector('[data-list-filter="town"]') || {}).value || "";
    var priceMin = parseNum((form.querySelector('[data-list-filter="price_min"]') || {}).value);
    var priceMax = parseNum((form.querySelector('[data-list-filter="price_max"]') || {}).value);
    var sizeMin = parseNum((form.querySelector('[data-list-filter="size_min"]') || {}).value);
    var withdrawnOnly = !!(form.querySelector('[data-list-filter="withdrawn_only"]') || {}).checked;

    var visibleCount = 0;
    cards().forEach(function (card) {
      var cardPortals = String(card.getAttribute("data-filter-portals") || "")
        .split(",")
        .map(function (x) { return x.trim(); })
        .filter(Boolean);
      var cardTown = card.getAttribute("data-filter-town") || "";
      var price = parseNum(card.getAttribute("data-filter-price"));
      var size = parseNum(card.getAttribute("data-filter-size"));
      var withdrawn = card.getAttribute("data-filter-withdrawn") === "1";

      var ok = true;
      if (portals.length) {
        ok = portals.some(function (p) { return cardPortals.indexOf(p) !== -1; });
      }
      if (ok && town) ok = cardTown === town;
      if (ok && priceMin != null) ok = price != null && price >= priceMin;
      if (ok && priceMax != null) ok = price != null && price <= priceMax;
      if (ok && sizeMin != null) ok = size != null && size >= sizeMin;
      if (ok && withdrawnOnly) ok = withdrawn;

      card.hidden = !ok;
      if (ok) visibleCount += 1;
    });

    var empty = document.getElementById("list-filters-empty");
    var grid = document.querySelector("#property-list .property-grid");
    var nativeEmpty = document.querySelector("#property-list .empty:not(.list-filters-empty)");
    if (empty) {
      var showFilteredEmpty = cards().length > 0 && visibleCount === 0;
      empty.hidden = !showFilteredEmpty;
    }
    if (grid) grid.hidden = cards().length > 0 && visibleCount === 0;
    if (nativeEmpty && cards().length > 0) nativeEmpty.hidden = true;

    updateHint(form);
  }

  function clearFilters() {
    var form = document.getElementById("list-filters-form");
    if (!form) return;
    form.querySelectorAll("input[type=checkbox]").forEach(function (el) { el.checked = false; });
    form.querySelectorAll("input[type=number], select").forEach(function (el) { el.value = ""; });
    applyFilters();
  }

  function bind() {
    var form = document.getElementById("list-filters-form");
    if (!form || form.dataset.bound === "1") {
      applyFilters();
      return;
    }
    form.dataset.bound = "1";
    form.addEventListener("input", applyFilters);
    form.addEventListener("change", applyFilters);
    var clearBtn = document.querySelector("[data-list-filters-clear]");
    if (clearBtn) clearBtn.addEventListener("click", clearFilters);
    applyFilters();
  }

  document.addEventListener("DOMContentLoaded", bind);
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.target && (event.target.id === "property-list" || event.target.querySelector("#property-list"))) {
      bind();
    }
    applyFilters();
  });
})();
