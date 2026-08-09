// ============================================================
// app/static/js/app.js
// Extracted from inline <script> blocks in home.html.
// ============================================================

(function () {
  "use strict";

  // ----------------------------------------------------------
  // 1. syncSortDropdown – dynamically swaps the <option> list
  //    inside #library-sort to match the active view context.
  // ----------------------------------------------------------
  function syncSortDropdown(viewType) {
    var sortSelect = document.getElementById("library-sort");
    if (!sortSelect) return;

    var currentValue = sortSelect.value;
    var master = document.getElementById("master-stream");
    var hasFilter =
      master &&
      (master.querySelector('[name="publisher"]') ||
        master.querySelector('[name="bundle_id"]'));

    if (viewType === "books") {
      if (hasFilter) {
        sortSelect.innerHTML =
          '<option value="title_asc">Title (A to Z)</option>' +
          '<option value="title_desc">Title (Z to A)</option>';
      } else {
        sortSelect.innerHTML =
          '<option value="title_asc">Title (A to Z)</option>' +
          '<option value="title_desc">Title (Z to A)</option>' +
          '<option value="publisher_asc">Publisher (A to Z)</option>';
      }
      if (
        currentValue === "count_desc" ||
        currentValue === "count_asc" ||
        currentValue === "publisher_asc"
      ) {
        sortSelect.value = "title_asc";
      } else {
        sortSelect.value = currentValue;
      }
    } else if (viewType === "publishers") {
      sortSelect.innerHTML =
        '<option value="title_asc">Name (A to Z)</option>' +
        '<option value="title_desc">Name (Z to A)</option>' +
        '<option value="count_desc">Most Items</option>' +
        '<option value="count_asc">Least Items</option>';
      if (
        currentValue === "publisher_asc" ||
        currentValue === "date_desc" ||
        currentValue === "date_asc"
      ) {
        sortSelect.value = "title_asc";
      } else {
        sortSelect.value = currentValue;
      }
    } else if (viewType === "bundles") {
      sortSelect.innerHTML =
        '<option value="title_asc">Name (A to Z)</option>' +
        '<option value="title_desc">Name (Z to A)</option>' +
        '<option value="count_desc">Most Items</option>' +
        '<option value="count_asc">Least Items</option>' +
        '<option value="date_desc">Newest Purchase</option>' +
        '<option value="date_asc">Oldest Purchase</option>';
      if (currentValue === "publisher_asc") {
        sortSelect.value = "title_asc";
      } else {
        sortSelect.value = currentValue;
      }
    }
    htmx.process(sortSelect);
  }
  // Expose globally so the htmx:afterSwap handler can reach it.
  window.syncSortDropdown = syncSortDropdown;

  // ----------------------------------------------------------
  // 2. Search input clear button synchronization.
  // ----------------------------------------------------------
  function initSearchClearButton() {
    var input = document.getElementById("library-search");
    var btn = document.querySelector(".search-clear");
    if (!input || !btn) return;

    function syncVisibility() {
      btn.hidden = input.value.length === 0;
    }

    input.addEventListener("input", syncVisibility);
    input.addEventListener("search", syncVisibility);
    syncVisibility();

    btn.addEventListener("click", function () {
      input.value = "";
      syncVisibility();
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  // ----------------------------------------------------------
  // 3. Mode pill click handlers + endpoint mapping.
  // ----------------------------------------------------------
  function initModePills() {
    var pills = document.querySelectorAll(".mode-pill");
    var input = document.getElementById("library-search");
    var sortSelect = document.getElementById("library-sort");
    if (!input) return;

    pills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        pills.forEach(function (p) {
          p.classList.remove("active");
          p.setAttribute("aria-selected", "false");
        });
        this.classList.add("active");
        this.setAttribute("aria-selected", "true");

        var endpoint = this.getAttribute("data-endpoint");
        var placeholder = this.getAttribute("data-placeholder");

        var filterClear = document.querySelector(".filter-clear-btn");
        if (filterClear) {
          var filterBar = document.querySelector(".filter-bar");
          if (filterBar) filterBar.remove();
        }

        input.setAttribute("hx-get", endpoint);
        input.setAttribute("placeholder", placeholder);

        var viewType = "books";
        if (endpoint === "/library/publishers") viewType = "publishers";
        else if (endpoint === "/library/bundles") viewType = "bundles";

        syncSortDropdown(viewType);
        if (sortSelect) {
          sortSelect.setAttribute("hx-get", endpoint);
        }

        htmx.process(input);
      });
    });
  }

  // ----------------------------------------------------------
  // 4. Global Escape key shortcut (4-tier cascade).
  // ----------------------------------------------------------
  function initEscapeKey() {
    document.addEventListener("keydown", function (event) {
      var key = event.key;
      if (key !== "Escape" && key !== "Esc") return;

      // Tier 0: sync modal is open
      var syncModal = document.getElementById("sync-modal-overlay");
      if (syncModal) {
        var container = document.getElementById("sync-modal-container");
        if (container) container.innerHTML = "";
        return;
      }

      // Tier 1: inspector drawer is open
      var drawerClose = document.querySelector(
        "#inspector-drawer .drawer-close"
      );
      if (drawerClose) {
        drawerClose.click();
        return;
      }

      var searchInput = document.getElementById("library-search");

      // Tier 2: search input has value or is focused
      if (
        searchInput &&
        (searchInput.value.length > 0 ||
          document.activeElement === searchInput)
      ) {
        searchInput.value = "";
        searchInput.dispatchEvent(new Event("input", { bubbles: true }));
        searchInput.blur();
        return;
      }

      // Tier 3: active filter pill is present
      var filterClear = document.querySelector(".filter-clear-btn");
      if (filterClear) {
        filterClear.click();
        return;
      }
    });
  }

  // ----------------------------------------------------------
  // 5. htmx:afterSwap on #sync-modal-container – refresh
  //    inspector drawer and master stream after successful sync.
  // ----------------------------------------------------------
  function initSyncModalAfterSwap() {
    var modalContainer = document.getElementById("sync-modal-container");
    if (!modalContainer) return;
    modalContainer.addEventListener("htmx:afterSwap", function () {
      var status = document.getElementById("sync-status");
      if (!status) return;
      var hasError = status.querySelector(".error-alert");
      var hasSuccess = status.querySelector(".stat-grid");
      if (hasSuccess && !hasError) {
        var inspector = document.getElementById("inspector-drawer");
        if (inspector) {
          htmx.trigger(inspector, "htmx:abort");
          inspector.setAttribute("hx-get", "/library/overview");
          htmx.process(inspector);
          htmx.trigger(inspector, "load");
        }
        var master = document.getElementById("master-stream");
        if (master) {
          htmx.trigger(master, "htmx:abort");
          master.setAttribute("hx-get", "/library/search");
          htmx.process(master);
          htmx.trigger(master, "load");
        }
      }
    });
  }

  // ----------------------------------------------------------
  // 6. htmx:afterSwap on #master-stream – keep mode pills and
  //    sort endpoint in sync after content swaps.
  // ----------------------------------------------------------
  function initMasterStreamAfterSwap() {
    var stream = document.getElementById("master-stream");
    if (!stream) return;
    stream.addEventListener("htmx:afterSwap", function () {
      var master = document.getElementById("master-stream");
      var sortSelect = document.getElementById("library-sort");
      var pills = document.querySelectorAll(".mode-pill");
      if (!master || !pills.length) return;

      var hasCategoryRow = master.querySelector(".category-row");

      var isPublisherPartial =
        hasCategoryRow &&
        master.innerHTML.indexOf('hx-get="/library/search?publisher=') !== -1;
      var isBundlePartial =
        hasCategoryRow &&
        master.innerHTML.indexOf('hx-get="/library/search?bundle_id=') !== -1;

      var bookPill = document.querySelector(
        '.mode-pill[data-endpoint="/library/search"]'
      );
      var publisherPill = document.querySelector(
        '.mode-pill[data-endpoint="/library/publishers"]'
      );
      var bundlePill = document.querySelector(
        '.mode-pill[data-endpoint="/library/bundles"]'
      );

      function activatePill(pill) {
        if (!pill) return;
        pills.forEach(function (p) {
          p.classList.remove("active");
          p.setAttribute("aria-selected", "false");
        });
        pill.classList.add("active");
        pill.setAttribute("aria-selected", "true");
      }

      if (isPublisherPartial) {
        activatePill(publisherPill);
        syncSortDropdown("publishers");
        if (sortSelect) {
          sortSelect.setAttribute("hx-get", "/library/publishers");
        }
      } else if (isBundlePartial) {
        activatePill(bundlePill);
        syncSortDropdown("bundles");
        if (sortSelect) {
          sortSelect.setAttribute("hx-get", "/library/bundles");
        }
      } else {
        activatePill(bookPill);
        syncSortDropdown("books");
        if (sortSelect) {
          sortSelect.setAttribute("hx-get", "/library/search");
        }
      }
    });
  }

  // ----------------------------------------------------------
  // Boot – wait for DOM ready then initialise everything.
  // ----------------------------------------------------------
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  function boot() {
    initSearchClearButton();
    initModePills();
    initEscapeKey();
    initSyncModalAfterSwap();
    initMasterStreamAfterSwap();
  }
})();