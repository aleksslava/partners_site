(() => {
  // portal
  const portal = document.createElement('div');
  portal.className = 'variant-portal';
  portal.setAttribute('role', 'listbox');
  document.body.appendChild(portal);

  let opened = null;

  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  function closePortal() {
    portal.classList.remove('variant-portal--open');
    portal.innerHTML = '';
    if (opened?.button) opened.button.setAttribute('aria-expanded', 'false');
    if (opened?.box) opened.box.classList.remove('product-variant--open');
    opened = null;
  }

  function positionPortalUnderButton(btn) {
    const rect = btn.getBoundingClientRect();
    portal.style.left = `${rect.left}px`;
    portal.style.top = `${rect.bottom + 8}px`;
    portal.style.width = `${rect.width}px`;
  }

  function buildOptions(select, currentValue, onPick) {
    portal.innerHTML = '';
    Array.from(select.options).forEach(opt => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'variant-portal__option' + (opt.value === currentValue ? ' is-active' : '');
      b.textContent = opt.textContent;
      b.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        onPick(opt.value, opt.textContent);
      });
      portal.appendChild(b);
    });
  }

  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(payload || {})
    });
    if (!r.ok) throw new Error(await r.text().catch(() => 'request failed'));
    return r.json();
  }

  function applyTotals(data) {
    if (!data) return;
    const map = {
      'cart-subtotal': data.items_subtotal,
      'cart-discount': data.discount_total,
      'cart-delivery': data.delivery_price,
      'cart-total': data.total,
      'cart-bonuses-append': data.bonuses_append_total,
    };
    Object.keys(map).forEach(id => {
      if (map[id] == null) return;
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function toggleExtraFields(discountType) {
    const onlyDiscount = document.querySelector('.js-only-discount');
    const semiBonuses = document.querySelector('.js-semi-bonuses');

    if (onlyDiscount) onlyDiscount.style.display = (discountType === 'discount') ? '' : 'none';
    if (semiBonuses) semiBonuses.style.display = (discountType === 'semi_bonuses') ? '' : 'none';
  }

  // global close
  document.addEventListener('click', (e) => {
    if (!opened) return;
    if (portal.contains(e.target)) return;
    if (opened.box && opened.box.contains(e.target)) return;
    closePortal();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePortal(); });
  window.addEventListener('scroll', () => { if (opened?.button) positionPortalUnderButton(opened.button); }, true);
  window.addEventListener('resize', () => { if (opened?.button) positionPortalUnderButton(opened.button); });

  document.addEventListener('DOMContentLoaded', () => {
    const box = document.querySelector('.js-cart-discount');
    if (!box) return;

    const select = box.querySelector('.js-cart-discount-select');
    const button = box.querySelector('.js-cart-discount-button');
    const label = box.querySelector('.js-cart-discount-label');

    const bonusesSpendInput = document.querySelector('.js-bonuses-spend');
    const orderDiscountInput = document.querySelector('.js-order-discount');

    if (!select || !button || !label) return;

    // первичный показ полей
    toggleExtraFields(select.value);

    // dropdown open
    button.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (opened && opened.box === box) {
        closePortal();
        return;
      }

      closePortal();
      opened = { box, select, button, label };

      box.classList.add('product-variant--open');
      button.setAttribute('aria-expanded', 'true');

      buildOptions(select, select.value, async (value, text) => {
        // UI
        select.value = value;
        label.textContent = text;
        toggleExtraFields(value);
        closePortal();

        // если режим не DISCOUNT — списание бонусов сбросим на UI
        if (value !== 'discount' && bonusesSpendInput) bonusesSpendInput.value = '0';

        try {
          const data = await apiPost('/api/cart/discount_type/', { discount_type: value });
          if (data?.discount_type_label) label.textContent = data.discount_type_label;
          applyTotals(data);
          location.reload();
        } catch (err) {
          console.error(err);
          location.reload();
        }
      });

      positionPortalUnderButton(button);
      portal.classList.add('variant-portal--open');
    });

    // debounce helper
    function debounce(fn, ms) {
      let t;
      return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
      };
    }

    // BONUSES_SPEND (only DISCOUNT)
    if (bonusesSpendInput) {
      bonusesSpendInput.addEventListener('input', debounce(async () => {
        if (select.value !== 'discount') return;
        const v = Number(bonusesSpendInput.value || 0);
        try {
          const data = await apiPost('/api/cart/set_bonuses_spend/', { bonuses_spent_total: v });
          applyCartRecalc(data);

        } catch (err) {
          console.error(err);
        }
      }, 250));
    }

    // ORDER_DISCOUNT (only SEMI_BONUSES)
    if (orderDiscountInput) {
      orderDiscountInput.addEventListener('input', debounce(async () => {
        if (select.value !== 'semi_bonuses') return;
        const v = Number(orderDiscountInput.value || 0);
        try {
          const data = await apiPost('/api/cart/set_order_discount/', { order_discount_percent: v });
          applyCartRecalc(data);

        } catch (err) {
          console.error(err);
        }
      }, 250));
    }
  });
})();


function applyCartRecalc(data) {
  if (!data || !data.success) return;

  const moneyFormatter = new Intl.NumberFormat('ru-RU');
  const formatMoney = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return value;
    return moneyFormatter.format(Math.round(num));
  };

  // totals
  const setText = (id, v) => {
    const el = document.getElementById(id);
    if (el && v != null) el.textContent = formatMoney(v);
  };

  setText('cart-total', data.total);
  setText('cart-subtotal', data.items_subtotal);
  setText('cart-discount', data.discount_total);
  setText('cart-delivery', data.delivery_price);
  setText('cart-bonuses-append', data.bonuses_append_total);
  setText('cart-bonuses-spent', data.bonuses_spent_total);

  // items
  (data.items || []).forEach(it => {
    const pid = String(it.product_id);

    const qtyEl = document.getElementById('cart-item-qty-' + pid);
    if (qtyEl) qtyEl.textContent = it.qty;

    const btnQtyEl = document.getElementById('button-item-qty-' + pid);
    if (btnQtyEl) btnQtyEl.textContent = it.qty;

    const lineTotalEl = document.getElementById('item-line-total-' + pid);
    if (lineTotalEl) lineTotalEl.textContent = formatMoney(it.line_total);

    const ba = document.getElementById('item-bonuses-append-' + pid);
    if (ba) ba.textContent = it.bonuses_append;

    const bs = document.getElementById('item-bonuses-spend-' + pid);
    if (bs) bs.textContent = it.bonuses_spent;

    // если хочешь обновлять цены в карточке:
    const priceNew = document.getElementById('item-price-discounted-' + pid);
    if (priceNew) priceNew.textContent = formatMoney(it.price_discounted);

    const priceOld = document.getElementById('item-price-base-' + pid);
    if (priceOld) priceOld.textContent = formatMoney(it.price);

    const discountPercent = Number(it.discount_percent || 0);
    const discountPercentEl = document.getElementById('item-discount-percent-' + pid);
    if (discountPercentEl) discountPercentEl.textContent = discountPercent;

    const oldPriceWrap = document.getElementById('item-old-price-wrap-' + pid);
    if (oldPriceWrap) oldPriceWrap.style.display = discountPercent > 0 ? '' : 'none';
  });
}
