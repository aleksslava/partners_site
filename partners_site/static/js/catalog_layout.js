(() => {
  const DESKTOP_MIN_WIDTH = 769;
  const ROW_FIELDS = ['.product-name', '.product-prices', '.product-desc'];

  function resetRowHeights(cards) {
    cards.forEach((card) => {
      ROW_FIELDS.forEach((selector) => {
        const el = card.querySelector(selector);
        if (el) el.style.minHeight = '';
      });
    });
  }

  function groupByVisualRow(cards) {
    const rows = new Map();
    cards.forEach((card) => {
      const key = Math.round(card.offsetTop);
      if (!rows.has(key)) rows.set(key, []);
      rows.get(key).push(card);
    });
    return rows;
  }

  function alignFieldInRow(cards, selector) {
    const elements = cards
      .map((card) => card.querySelector(selector))
      .filter((el) => el && getComputedStyle(el).display !== 'none');

    if (elements.length < 2) return;

    const maxHeight = Math.max(...elements.map((el) => el.offsetHeight));
    elements.forEach((el) => {
      el.style.minHeight = `${maxHeight}px`;
    });
  }

  function syncCatalogCardRows(rootEl = document) {
    const cards = Array.from(rootEl.querySelectorAll('.js-product-card'));
    if (!cards.length) return;

    resetRowHeights(cards);

    if (window.innerWidth < DESKTOP_MIN_WIDTH) return;

    const rows = groupByVisualRow(cards);
    rows.forEach((rowCards) => {
      ROW_FIELDS.forEach((selector) => alignFieldInRow(rowCards, selector));
    });
  }

  let resizeTimer = null;
  function onResize() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => syncCatalogCardRows(document), 120);
  }

  window.syncCatalogCardRows = syncCatalogCardRows;

  document.addEventListener('DOMContentLoaded', () => {
    syncCatalogCardRows(document);
    window.addEventListener('resize', onResize);
  });
})();
