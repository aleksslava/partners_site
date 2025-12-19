document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('catalog-search-input');
  const clearBtn = document.getElementById('catalog-search-clear');
  const results = document.getElementById('catalog-results');
  const tagsWrap = document.getElementById('catalog-tags');

  if (!input || !results || !clearBtn) return;

  let timer = null;
  let abortCtrl = null;
  const DEBOUNCE_MS = 300;

  function setClearVisible() {
    const hasText = input.value.trim().length > 0;
    clearBtn.classList.toggle('is-hidden', !hasText);
  }

  function setActiveTag(tagValue) {
    if (!tagsWrap) return;
    tagsWrap.querySelectorAll('.tag-chip').forEach(btn => {
      const v = btn.dataset.tag || '';
      btn.classList.toggle('is-active', v === (tagValue || ''));
    });
  }

  async function fetchAndReplace({ q, tag }) {
    if (abortCtrl) abortCtrl.abort();
    abortCtrl = new AbortController();

    const url = new URL(window.location.href);

    if (q) url.searchParams.set('q', q);
    else url.searchParams.delete('q');

    if (tag) url.searchParams.set('tag', tag);
    else url.searchParams.delete('tag');

    const resp = await fetch(url.toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      signal: abortCtrl.signal,
    });

    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');

    const newResults = doc.getElementById('catalog-results');
    if (newResults) results.innerHTML = newResults.innerHTML;

    // URL без перезагрузки
    window.history.replaceState({}, '', url.toString());

    // реинициализируем dropdown модификаций на новых карточках
    if (window.initCatalogVariants) window.initCatalogVariants(results);
  }

  function scheduleSearch() {
    const q = input.value.trim();
    setClearVisible();

    // читаем текущий tag из URL (актуально при вводе)
    const url = new URL(window.location.href);
    const tag = url.searchParams.get('tag') || '';

    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fetchAndReplace({ q, tag }).catch(err => {
        if (err && err.name === 'AbortError') return;
        console.error(err);
      });
    }, DEBOUNCE_MS);
  }

  // поиск по мере ввода
  input.addEventListener('input', scheduleSearch);

  // крестик браузера (type=search)
  input.addEventListener('search', () => {
    input.value = '';
    scheduleSearch();
  });

  // наш крестик
  clearBtn.addEventListener('click', () => {
    input.value = '';
    input.focus();
    scheduleSearch();
  });

  // клики по тегам
  if (tagsWrap) {
    tagsWrap.addEventListener('click', (e) => {
      const btn = e.target.closest('.tag-chip');
      if (!btn) return;

      const tag = btn.dataset.tag || '';
      setActiveTag(tag);

      const q = input.value.trim();
      fetchAndReplace({ q, tag }).catch(err => {
        if (err && err.name === 'AbortError') return;
        console.error(err);
      });
    });
  }

  // initial state
  setClearVisible();
  const currentTag = new URL(window.location.href).searchParams.get('tag') || '';
  setActiveTag(currentTag);
});
