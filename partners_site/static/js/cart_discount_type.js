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
    window.syncCartBonusRows?.();
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
    const optionButtons = Array.from(document.querySelectorAll('.js-cart-discount-option'));

    const bonusesSpendInput = document.querySelector('.js-bonuses-spend');
    const orderDiscountInput = document.querySelector('.js-order-discount');

    if (!select || !button || !label) return;

    function getOptionText(value) {
      const option = Array.from(select.options).find(opt => opt.value === value);
      return option ? option.textContent : '';
    }

    function syncDiscountButtons(value) {
      optionButtons.forEach(optionButton => {
        const isActive = optionButton.dataset.discountType === value;
        optionButton.classList.toggle('is-active', isActive);
        optionButton.setAttribute('aria-pressed', String(isActive));
      });
    }

    function setDiscountUi(value, text) {
      select.value = value;
      label.textContent = text || getOptionText(value);
      toggleExtraFields(value);
      syncDiscountButtons(value);
    }

    async function saveDiscountType(value, text) {
      setDiscountUi(value, text);
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
    }

    // первичный показ полей
    toggleExtraFields(select.value);
    syncDiscountButtons(select.value);

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

      buildOptions(select, select.value, saveDiscountType);

      positionPortalUnderButton(button);
      portal.classList.add('variant-portal--open');
    });

    optionButtons.forEach(optionButton => {
      optionButton.addEventListener('click', (e) => {
        e.preventDefault();
        const value = optionButton.dataset.discountType;
        if (!value || value === select.value) return;
        saveDiscountType(value, optionButton.textContent.trim());
      });
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
      const parseNumber = (value) => {
        const normalized = String(value || '').replace(/[^\d.-]/g, '');
        const parsed = Number(normalized || 0);
        return Number.isFinite(parsed) ? parsed : 0;
      };
      const getBonusesSpendLimit = () => parseNumber(bonusesSpendInput.dataset.max || bonusesSpendInput.max || 0);
      const getBonusesSpendValue = () => parseNumber(bonusesSpendInput.value || 0);
      const syncBonusesSpendValidity = () => {
        bonusesSpendInput.classList.toggle('is-invalid', getBonusesSpendValue() > getBonusesSpendLimit());
      };
      const saveBonusesSpend = async (value) => {
        const data = await apiPost('/api/cart/set_bonuses_spend/', { bonuses_spent_total: value });
        applyCartRecalc(data);
        if (data?.bonus_spend_limit != null) {
          bonusesSpendInput.max = data.bonus_spend_limit;
          bonusesSpendInput.dataset.max = data.bonus_spend_limit;
        }
        if (data?.bonuses_spent_total != null) bonusesSpendInput.value = data.bonuses_spent_total;
        syncBonusesSpendValidity();
      };

      bonusesSpendInput.addEventListener('input', debounce(async () => {
        if (select.value !== 'discount') return;
        const v = getBonusesSpendValue();
        syncBonusesSpendValidity();
        if (v > getBonusesSpendLimit()) return;
        try {
          await saveBonusesSpend(v);
        } catch (err) {
          console.error(err);
        }
      }, 250));

      bonusesSpendInput.addEventListener('blur', async () => {
        if (select.value !== 'discount') return;
        const nextValue = Math.min(Math.max(getBonusesSpendValue(), 0), getBonusesSpendLimit());
        bonusesSpendInput.value = nextValue;
        try {
          await saveBonusesSpend(nextValue);
        } catch (err) {
          console.error(err);
        }
      });
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
  applyCartBonusSpendLimit(data);
  window.syncCartBonusRows?.();

  // items
  (data.items || []).forEach(it => {
    const pid = String(it.product_id);

    const qtyEl = document.getElementById('cart-item-qty-' + pid);
    if (qtyEl) qtyEl.textContent = it.qty;

    const btnQtyEl = document.getElementById('button-item-qty-' + pid);
    if (btnQtyEl) btnQtyEl.textContent = it.qty;

    const lineTotalEl = document.getElementById('item-line-total-' + pid);
    if (lineTotalEl) lineTotalEl.textContent = formatMoney(it.line_total);

    const mobileLineTotalEl = document.getElementById('item-line-total-mobile-' + pid);
    if (mobileLineTotalEl) mobileLineTotalEl.textContent = formatMoney(it.line_total);

    const ba = document.getElementById('item-bonuses-append-' + pid);
    if (ba) ba.textContent = it.bonuses_append;

    const bs = document.getElementById('item-bonuses-spend-' + pid);
    if (bs) bs.textContent = it.bonuses_spent;

    // если хочешь обновлять цены в карточке:
    const priceNew = document.getElementById('item-price-discounted-' + pid);
    if (priceNew) priceNew.textContent = formatMoney(it.price_discounted);

    const priceNewMobile = document.getElementById('item-price-discounted-mobile-' + pid);
    if (priceNewMobile) priceNewMobile.textContent = formatMoney(it.price_discounted);

    const priceOld = document.getElementById('item-price-base-' + pid);
    if (priceOld) priceOld.textContent = formatMoney(it.price);

    const priceOldMobile = document.getElementById('item-price-base-mobile-' + pid);
    if (priceOldMobile) priceOldMobile.textContent = formatMoney(it.price);

    const discountPercent = Number(it.discount_percent || 0);
    const discountPercentEl = document.getElementById('item-discount-percent-' + pid);
    if (discountPercentEl) discountPercentEl.textContent = discountPercent;

    const discountPercentMobileEl = document.getElementById('item-discount-percent-mobile-' + pid);
    if (discountPercentMobileEl) discountPercentMobileEl.textContent = discountPercent;

    const oldPriceWrap = document.getElementById('item-old-price-wrap-' + pid);
    if (oldPriceWrap) oldPriceWrap.style.display = discountPercent > 0 ? '' : 'none';

    const oldPriceWrapMobile = document.getElementById('item-old-price-wrap-mobile-' + pid);
    if (oldPriceWrapMobile) oldPriceWrapMobile.style.display = discountPercent > 0 ? '' : 'none';
  });
}

function applyCartBonusSpendLimit(data) {
  if (!data || data.bonus_spend_limit == null) return;

  const moneyFormatter = new Intl.NumberFormat('ru-RU');
  const formatMoney = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return value;
    return moneyFormatter.format(Math.round(num));
  };
  const parseNumber = (value) => {
    const parsed = Number(String(value || '').replace(/[^\d.-]/g, '') || 0);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const limit = Math.max(0, parseNumber(data.bonus_spend_limit));
  const input = document.querySelector('.js-bonuses-spend');
  const hint = document.querySelector('.js-bonuses-spend-hint');
  const customerBonuses = data.customer_bonuses != null
    ? Math.max(0, parseNumber(data.customer_bonuses))
    : Math.max(0, parseNumber(hint?.dataset.customerBonuses));

  if (input) {
    input.max = String(limit);
    input.dataset.max = String(limit);

    const spent = data.bonuses_spent_total ?? data.total_bonus_spent;
    const nextValue = spent != null ? parseNumber(spent) : Math.min(parseNumber(input.value), limit);
    input.value = String(Math.min(Math.max(nextValue, 0), limit));
    input.classList.toggle('is-invalid', parseNumber(input.value) > limit);
  }

  if (hint) {
    hint.dataset.customerBonuses = String(customerBonuses);
    hint.textContent = `Можно списать ${formatMoney(limit)} из ${formatMoney(customerBonuses)} бонусов`;
  }
}
