/**
 * cart_payment.js — готовый файл для замены
 *
 * Функции:
 * 1) Dropdown выбора payment_type в стиле portal (как в каталоге)
 * 2) Показ/скрытие блока реквизитов при payment_type === 'invoice'
 * 3) Поиск реквизитов по мере ввода (portal dropdown) + автоподстановка полей
 * 4) Сохранение реквизитов кнопкой "Сохранить реквизиты" без перезагрузки:
 *    POST /api/cart/save-requisites/
 *
 * Ожидаемые классы в HTML:
 *
 * Блок оплаты:
 *  .js-cart-payment
 *    select.js-cart-payment-select          (native select)
 *    button.js-cart-payment-button          (trigger)
 *    span.js-cart-payment-label             (label)
 *
 * Инвойс-блок:
 *  .js-invoice-fields                       (обертка всех полей счета)
 *  input.js-requisites-search               (поиск реквизитов)
 *  input.js-invoice-company-name            (наименование)
 *  input.js-invoice-inn
 *  input.js-invoice-bik
 *  input.js-invoice-legal-address
 *  input.js-invoice-account
 *  button.js-save-requisites                (сохранить)
 *
 * Endpoint'ы:
 *  POST /api/cart/payment-type/             {payment_type}
 *  GET  /api/requisites/search/?q=...       -> [{id, company_name/name, inn, bik, legal_address, settlement_account}]
 *  POST /api/cart/set-requisites/           {requisites_id}
 *  POST /api/cart/save-requisites/          {id?, name, inn, bik, legal_address, settlement_account}
 */

(() => {
  // ----------------- utils -----------------
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || '',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(payload || {})
    });
    if (!r.ok) throw new Error(await r.text().catch(() => 'request failed'));
    return r.json();
  }

  async function apiGet(url) {
    const r = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (!r.ok) throw new Error(await r.text().catch(() => 'request failed'));
    return r.json();
  }

  const moneyFormatter = new Intl.NumberFormat('ru-RU');
  function formatMoney(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return value;
    return moneyFormatter.format(Math.round(num));
  }

  function applyTotals(data) {
    if (!data || !data.success) return;
    const setText = (id, v) => {
      const el = document.getElementById(id);
      if (el && v != null) el.textContent = formatMoney(v);
    };
    setText('cart-total', data.total);
    setText('cart-subtotal', data.items_subtotal);
    setText('cart-discount', data.discount_total);
    setText('cart-delivery', data.delivery_price);
    setText('cart-bonuses-append', data.bonuses_append_total);
  }

  // ----------------- portal dropdown (one per page) -----------------
  const portal = (() => {
    let el = document.querySelector('.variant-portal');
    if (!el) {
      el = document.createElement('div');
      el.className = 'variant-portal';
      el.setAttribute('role', 'listbox');
      document.body.appendChild(el);
    }
    return el;
  })();

  let opened = null; // { anchorEl, ownerEl, onClose? }

  function closePortal() {
    portal.classList.remove('variant-portal--open');
    portal.innerHTML = '';
    if (opened?.anchorEl?.hasAttribute('aria-expanded')) opened.anchorEl.setAttribute('aria-expanded', 'false');
    if (opened?.ownerEl) opened.ownerEl.classList.remove('product-variant--open');
    if (opened?.onClose) opened.onClose();
    opened = null;
  }

  function positionPortal(anchorEl, widthEl) {
    const rect = anchorEl.getBoundingClientRect();
    const wRect = (widthEl || anchorEl).getBoundingClientRect();
    portal.style.left = `${rect.left}px`;
    portal.style.top = `${rect.bottom + 8}px`;
    portal.style.width = `${wRect.width}px`;
  }

  function openPortal(anchorEl, ownerEl, widthEl, buildFn, onClose) {
    // toggle
    if (opened && opened.anchorEl === anchorEl) {
      closePortal();
      return;
    }
    closePortal();

    opened = { anchorEl, ownerEl, onClose };
    if (ownerEl) ownerEl.classList.add('product-variant--open');
    if (anchorEl?.hasAttribute('aria-expanded')) anchorEl.setAttribute('aria-expanded', 'true');

    buildFn();
    positionPortal(anchorEl, widthEl);
    portal.classList.add('variant-portal--open');
  }

  // global close
  document.addEventListener('click', (e) => {
    if (!opened) return;
    if (portal.contains(e.target)) return;
    if (opened.ownerEl && opened.ownerEl.contains(e.target)) return;
    // для поиска: клики по самому input считаем "внутри"
    if (opened.anchorEl && opened.anchorEl.contains && opened.anchorEl.contains(e.target)) return;
    closePortal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePortal();
  });

  window.addEventListener('scroll', () => {
    if (!opened?.anchorEl) return;
    positionPortal(opened.anchorEl, opened.anchorEl);
  }, true);

  window.addEventListener('resize', () => {
    if (!opened?.anchorEl) return;
    positionPortal(opened.anchorEl, opened.anchorEl);
  });

  // ----------------- init -----------------
  document.addEventListener('DOMContentLoaded', () => {
    // payment dropdown
    const paymentBox = document.querySelector('.js-cart-payment');
    const paymentSelect = paymentBox?.querySelector('.js-cart-payment-select');
    const paymentBtn = paymentBox?.querySelector('.js-cart-payment-button');
    const paymentLabel = paymentBox?.querySelector('.js-cart-payment-label');

    // invoice UI
    const invoiceWrap = document.querySelector('.js-invoice-fields');
    const reqSearchInput = document.querySelector('.js-requisites-search');

    const fCompany = document.querySelector('.js-invoice-company-name');
    const fInn = document.querySelector('.js-invoice-inn');
    const fBik = document.querySelector('.js-invoice-bik');
    const fLegal = document.querySelector('.js-invoice-legal-address');
    const fAccount = document.querySelector('.js-invoice-account');

    const saveBtn = document.querySelector('.js-save-requisites');

    // Текущий выбранный requisites_id (если ты проставляешь при рендере — можно заполнить)
    // window.__activeRequisitesId = window.__activeRequisitesId || null;

    function isInvoiceSelected() {
      return (paymentSelect?.value || '') === 'invoice';
    }

    function toggleInvoiceFields() {
      if (!invoiceWrap) return;
      invoiceWrap.style.display = isInvoiceSelected() ? '' : 'none';
      if (!isInvoiceSelected()) closePortal();
    }

    if (paymentSelect) toggleInvoiceFields();

    function buildSelectOptions(selectEl, activeValue, onPick) {
      portal.innerHTML = '';
      Array.from(selectEl.options).forEach(opt => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'variant-portal__option' + (String(opt.value) === String(activeValue) ? ' is-active' : '');
        b.textContent = opt.textContent;

        b.addEventListener('click', async (e) => {
          e.preventDefault();
          e.stopPropagation();
          await onPick(opt.value, opt.textContent);
        });

        portal.appendChild(b);
      });
    }

    // --- payment type dropdown ---
    if (paymentBox && paymentSelect && paymentBtn && paymentLabel) {
      paymentBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        openPortal(
          paymentBtn,
          paymentBox,
          paymentBtn,
          () => buildSelectOptions(paymentSelect, paymentSelect.value, async (value, text) => {
            // optimistic
            paymentSelect.value = value;
            paymentLabel.textContent = text;
            toggleInvoiceFields();
            closePortal();

            try {
              const data = await apiPost('/api/cart/payment-type/', { payment_type: value });
              if (data?.payment_type_label) paymentLabel.textContent = data.payment_type_label;
              applyCartRecalc(data);
            } catch (err) {
              console.error(err);
              location.reload();
            }
          })
        );
      });

      // если вдруг paymentSelect меняется (не должен) — синхронизируем
      paymentSelect.addEventListener('change', toggleInvoiceFields);
    }

    // --- requisites search ---
    let lastResults = [];
    let activeReqId = null;

    function setReqFields(r) {
      if (!r) return;
      if (fCompany) fCompany.value = r.company_name || r.name || '';
      if (fInn) fInn.value = r.inn || '';
      if (fBik) fBik.value = r.bik || '';
      if (fLegal) fLegal.value = r.legal_address || '';
      if (fAccount) fAccount.value = r.settlement_account || '';
    }

    function buildReqOptions(results, query) {
      portal.innerHTML = '';

      const hint = document.createElement('div');
      hint.style.padding = '10px 14px';
      hint.style.fontSize = '12px';
      hint.style.color = 'rgba(15,23,42,.55)';
      hint.textContent = query ? `Найдено: ${results.length}` : '';
      if (query) portal.appendChild(hint);

      if (!results.length) {
        const empty = document.createElement('div');
        empty.style.padding = '12px 14px';
        empty.style.fontSize = '14px';
        empty.style.fontWeight = '600';
        empty.style.color = 'rgba(15,23,42,.6)';
        empty.textContent = 'Ничего не найдено';
        portal.appendChild(empty);
        return;
      }

      results.forEach(r => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'variant-portal__option' + (String(r.id) === String(activeReqId) ? ' is-active' : '');

        const title = r.company_name || r.name || `Реквизиты #${r.id}`;
        const inn = r.inn ? `ИНН ${r.inn}` : '';
        b.textContent = inn ? `${title} • ${inn}` : title;

        b.addEventListener('click', async (e) => {
          e.preventDefault();
          e.stopPropagation();

          activeReqId = r.id;
          window.__activeRequisitesId = r.id;

          // заполнить поля
          setReqFields(r);

          // сделать красиво: в поиске отображаем выбранное
          if (reqSearchInput) reqSearchInput.value = title;

          closePortal();

          // привязать к корзине
          try {
            const data = await apiPost('/api/cart/set-requisites/', { requisites_id: r.id });
            applyTotals(data);
          } catch (err) {
            console.error(err);
            location.reload();
          }
        });

        portal.appendChild(b);
      });
    }

    const doSearch = debounce(async () => {
      if (!reqSearchInput) return;
      if (!isInvoiceSelected()) return;

      const q = (reqSearchInput.value || '').trim();
      if (!q) {
        lastResults = [];
        closePortal();
        return;
      }

      try {
        const data = await apiGet(`/api/cart/requisites/search/?q=${encodeURIComponent(q)}`);
        const results = Array.isArray(data) ? data : (data.results || []);
        lastResults = results;

        openPortal(
          reqSearchInput,
          reqSearchInput, // owner
          reqSearchInput,
          () => buildReqOptions(results, q)
        );
      } catch (err) {
        console.error(err);
        closePortal();
      }
    }, 250);

    if (reqSearchInput) {
      reqSearchInput.addEventListener('input', doSearch);

      reqSearchInput.addEventListener('focus', () => {
        if (!isInvoiceSelected()) return;
        const q = (reqSearchInput.value || '').trim();
        if (!q) return;
        if (lastResults && lastResults.length) {
          openPortal(reqSearchInput, reqSearchInput, reqSearchInput, () => buildReqOptions(lastResults, q));
        }
      });

      // если это input type="search": событие search срабатывает при клике на крестик
      reqSearchInput.addEventListener('search', () => {
        const q = (reqSearchInput.value || '').trim();
        if (!q) {
          lastResults = [];
          closePortal();
        }
      });
    }

    // --- save requisites button ---
    async function saveRequisites() {
      if (!isInvoiceSelected()) return;

      const payload = {
        id: window.__activeRequisitesId || null,
        name: fCompany?.value || '',
        inn: fInn?.value || '',
        bik: fBik?.value || '',
        legal_address: fLegal?.value || '',
        settlement_account: fAccount?.value || ''
      };

      // минимальная валидация
      if (!payload.name.trim()) {
        alert('Заполните "Наименование организации"');
        return;
      }

      const data = await apiPost('/api/cart/save-requisites/', payload);
      if (data?.success) {
        window.__activeRequisitesId = data.requisites_id;
        activeReqId = data.requisites_id;
        applyTotals(data);
      }
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', (e) => {
        e.preventDefault();
        saveRequisites().catch(console.error);
      });
    }
  });
})();
