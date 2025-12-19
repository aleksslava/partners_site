(() => {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  async function apiGetQuantities() {
    const r = await fetch('/api/cart/quantities/', { headers: { 'X-Requested-With': 'XMLHttpRequest' }});
    return r.ok ? r.json() : {};
  }

  async function apiUpdateItem(productId, delta) {
    const r = await fetch('/api/cart/items/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ product_id: productId, delta })
    });
    if (!r.ok) throw new Error('Cart update failed');
    return r.json(); // ожидаем {product_id, qty, quantities?}
  }

  function setControlState(control, qty) {
    const mainBtn = control.querySelector('.js-cart-main');
    control.classList.toggle('is-active', qty > 0);
    mainBtn.textContent = qty > 0 ? String(qty) : 'В корзину';
  }

  function initCartControls(root) {
    const scope = root || document;
    const cards = scope.querySelectorAll('.js-product-card');

    cards.forEach(card => {
      const control = card.querySelector('.js-cart-control');
      if (!control || control.dataset.init === '1') return;
      control.dataset.init = '1';

      const select = card.querySelector('.js-variant-select');
      const decBtn = control.querySelector('.js-cart-dec');
      const incBtn = control.querySelector('.js-cart-inc');
      const mainBtn = control.querySelector('.js-cart-main');

      // Текущий product_id берём из выбранной модификации
      function currentProductId() {
        return select ? String(select.value) : (control.dataset.productId || '');
      }

      // обновление data-product-id при смене модификации
      if (select) {
        select.addEventListener('change', () => {
          control.dataset.productId = currentProductId();
          const qty = window.__cartQty?.[control.dataset.productId] || 0;
          setControlState(control, qty);
        });
        control.dataset.productId = currentProductId();
      }

      // клики
      async function applyDelta(delta) {
        const pid = currentProductId();
        if (!pid) return;

        const res = await apiUpdateItem(pid, delta);
        const qty = Number(res.qty || 0);

        window.__cartQty = window.__cartQty || {};
        window.__cartQty[pid] = qty;

        setControlState(control, qty);
      }

      mainBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const pid = currentProductId();
        const qty = window.__cartQty?.[pid] || 0;
        // если было 0 — добавляем 1, иначе ничего не делаем (можно сделать +1)
        applyDelta(qty > 0 ? 0 : 1).catch(console.error);
      });

      incBtn.addEventListener('click', (e) => { e.preventDefault(); applyDelta(1).catch(console.error); });
      decBtn.addEventListener('click', (e) => { e.preventDefault(); applyDelta(-1).catch(console.error); });
    });

    // выставляем начальные qty
    scope.querySelectorAll('.js-cart-control').forEach(control => {
      const pid = control.dataset.productId;
      if (!pid) return;
      const qty = window.__cartQty?.[pid] || 0;
      setControlState(control, qty);
    });
  }

  window.initCatalogCartControls = initCartControls;

  document.addEventListener('DOMContentLoaded', async () => {
    window.__cartQty = await apiGetQuantities();
    initCartControls(document);
  });
})();
