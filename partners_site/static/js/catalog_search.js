document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('catalog-search-input');
  const clearBtn = document.getElementById('catalog-search-clear');
  const results = document.getElementById('catalog-results');
  const tagsWrap = document.getElementById('catalog-tags');
  const loadingEl = document.getElementById('catalog-loading');
  const statusEl = document.getElementById('catalog-results-status');

  if (!input || !results || !clearBtn) return;

  let timer = null;
  let abortCtrl = null;
  let requestSeq = 0;
  const DEBOUNCE_MS = 300;

  function announceStatus(message) {
    if (!statusEl) return;
    statusEl.textContent = '';
    window.setTimeout(() => {
      statusEl.textContent = message;
    }, 0);
  }

  function getResultsCount(root = results) {
    return root ? root.querySelectorAll('.js-product-card').length : 0;
  }

  function announceResults(root = results) {
    const count = getResultsCount(root);
    if (count > 0) {
      announceStatus(`Найдено товаров: ${count}.`);
      return;
    }
    announceStatus('Товары не найдены.');
  }

  function setLoading(isLoading) {
    if (loadingEl) loadingEl.hidden = !isLoading;
    results.classList.toggle('is-loading', isLoading);
    results.setAttribute('aria-busy', isLoading ? 'true' : 'false');
    if (isLoading) announceStatus('Загружаем результаты поиска.');
  }

  function setClearVisible() {
    const hasText = input.value.trim().length > 0;
    clearBtn.classList.toggle('is-hidden', !hasText);
  }

  function setActiveTag(tagValue) {
    if (!tagsWrap) return;
    tagsWrap.querySelectorAll('.tag-chip').forEach((btn) => {
      const value = btn.dataset.tag || '';
      btn.classList.toggle('is-active', value === (tagValue || ''));
    });
  }

  async function fetchAndReplace({ q, tag }) {
    if (abortCtrl) abortCtrl.abort();
    abortCtrl = new AbortController();
    const seq = ++requestSeq;

    const url = new URL(window.location.href);
    if (q) url.searchParams.set('q', q);
    else url.searchParams.delete('q');

    if (tag) url.searchParams.set('tag', tag);
    else url.searchParams.delete('tag');

    setLoading(true);
    try {
      const resp = await fetch(url.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: abortCtrl.signal,
      });
      if (!resp.ok) throw new Error(`Catalog search failed: ${resp.status}`);

      const html = await resp.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const newResults = doc.getElementById('catalog-results');
      if (newResults) {
        results.innerHTML = newResults.innerHTML;
        announceResults(results);
      }

      window.history.replaceState({}, '', url.toString());

      if (window.initCatalogVariants) window.initCatalogVariants(results);
      if (window.initCatalogCartControls) window.initCatalogCartControls(results);
      if (window.syncCatalogCardRows) window.syncCatalogCardRows(results);
    } finally {
      if (seq === requestSeq) setLoading(false);
    }
  }

  function scheduleSearch() {
    const q = input.value.trim();
    setClearVisible();

    const url = new URL(window.location.href);
    const tag = url.searchParams.get('tag') || '';

    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fetchAndReplace({ q, tag }).catch((err) => {
        if (err && err.name === 'AbortError') return;
        announceStatus('Не удалось обновить результаты. Попробуйте снова.');
        console.error(err);
      });
    }, DEBOUNCE_MS);
  }

  input.addEventListener('input', scheduleSearch);

  input.addEventListener('search', () => {
    input.value = '';
    scheduleSearch();
  });

  clearBtn.addEventListener('click', () => {
    input.value = '';
    input.focus();
    scheduleSearch();
  });

  if (tagsWrap) {
    tagsWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.tag-chip');
      if (!btn) return;

      const tag = btn.dataset.tag || '';
      setActiveTag(tag);

      const q = input.value.trim();
      fetchAndReplace({ q, tag }).catch((err) => {
        if (err && err.name === 'AbortError') return;
        announceStatus('Не удалось обновить результаты. Попробуйте снова.');
        console.error(err);
      });
    });
  }

  setClearVisible();
  const currentTag = new URL(window.location.href).searchParams.get('tag') || '';
  setActiveTag(currentTag);
  announceResults(results);
});
