(() => {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  async function apiGetQuantities() {
    const r = await fetch('/api/cart/quantities/', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    return r.ok ? r.json() : {};
  }

  async function apiUpdateItem(productId, delta) {
    const r = await fetch('/api/cart/add/', {   // <-- ОБЯЗАТЕЛЬНО со слэшем в начале
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ product_id: productId, delta })
    });

    if (!r.ok) {
      const text = await r.text().catch(() => '');
      console.error('Cart update failed', r.status, text);
      throw new Error('Cart update failed');
    }
    return r.json(); // {product_id, qty}
  }

  function updateCartBadge() {
    const badge = document.getElementById('cart-badge');
    if (!badge) return;
    const total = Object.values(window.__cartQty || {}).reduce((s, v) => s + Number(v), 0);
    badge.textContent = total;
    badge.hidden = total === 0;
  }

  function setControlState(control, qty) {
    const mainBtn = control.querySelector('.js-cart-main');
    control.classList.toggle('is-active', qty > 0);
    if (mainBtn) mainBtn.textContent = qty > 0 ? String(qty) : 'В корзину';
  }

  function initCartControls(root) {
    const scope = root || document;
    const cards = scope.querySelectorAll('.js-product-card');

    cards.forEach(card => {
      const control = card.querySelector('.js-cart-control');
      if (!control || control.dataset.init === '1') return;
      control.dataset.init = '1';

      const select = card.querySelector('.js-variant-select'); // может отсутствовать
      const decBtn = control.querySelector('.js-cart-dec');
      const incBtn = control.querySelector('.js-cart-inc');
      const mainBtn = control.querySelector('.js-cart-main');

      // всегда должен вернуть productId
      function currentProductId() {
        if (select) return String(select.value || '');
        return String(control.dataset.productId || '');
      }

      // если есть select — при смене модификации обновляем productId в control
      if (select) {
        select.addEventListener('change', () => {
          control.dataset.productId = String(select.value || '');
          const qty = window.__cartQty?.[control.dataset.productId] || 0;
          setControlState(control, qty);
        });

        // первичная установка
        control.dataset.productId = String(select.value || control.dataset.productId || '');
      }

      // если select нет — убеждаемся, что productId уже проставлен из шаблона
      // (data-product-id="{{ product.id }}")
      if (!select && !control.dataset.productId) {
        console.warn('Cart control has no productId. Add data-product-id in template.');
      }

      async function applyDelta(delta) {
        const pid = currentProductId();
        if (!pid) return;

        const res = await apiUpdateItem(pid, delta);
        const qty = Number(res.qty || 0);

        window.__cartQty = window.__cartQty || {};
        window.__cartQty[String(pid)] = qty;

        setControlState(control, qty);
        updateCartBadge();
      }

      if (mainBtn) {
        mainBtn.addEventListener('click', (e) => {
          e.preventDefault();
          const pid = currentProductId();
          if (!pid) return;

          const qty = window.__cartQty?.[pid] || 0;
          // если было 0 — добавляем 1, иначе можно ничего не делать
          applyDelta(qty > 0 ? 0 : 1).catch(console.error);
        });
      }

      if (incBtn) incBtn.addEventListener('click', (e) => { e.preventDefault(); applyDelta(1).catch(console.error); });
      if (decBtn) decBtn.addEventListener('click', (e) => { e.preventDefault(); applyDelta(-1).catch(console.error); });

      // первичная отрисовка для этой карточки
      const initPid = currentProductId();
      const initQty = initPid ? (window.__cartQty?.[initPid] || 0) : 0;
      setControlState(control, initQty);
    });

    // на случай, если разметка уже содержит controls без init (после ajax)
    scope.querySelectorAll('.js-cart-control').forEach(control => {
      const pid = String(control.dataset.productId || '');
      if (!pid) return;
      const qty = window.__cartQty?.[pid] || 0;
      setControlState(control, qty);
    });
  }

  window.initCatalogCartControls = initCartControls;

  document.addEventListener('DOMContentLoaded', async () => {
    window.__cartQty = await apiGetQuantities();
    updateCartBadge();
    initCartControls(document);
  });
})();
