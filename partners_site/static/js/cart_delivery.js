(() => {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
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
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw data;
    return data;
  }

  async function apiGet(url) {
    const r = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    const data = await r.json().catch(() => ([]));
    if (!r.ok) throw data;
    return data;
  }

  function applyTotals(data) {
    if (!data || !data.success) return;
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el && value != null) el.textContent = value;
    };
    setText('cart-total', data.total);
    setText('cart-subtotal', data.items_subtotal);
    setText('cart-discount', data.discount_total);
    setText('cart-delivery', data.delivery_price);
    setText('cart-bonuses-append', data.bonuses_append_total);
  }

  function normalizePhone(value) {
    let s = (value || '').trim().replace(/[^\d+]/g, '');
    if (s.startsWith('8') && s.length === 11) s = '+7' + s.slice(1);
    if (s.startsWith('7') && s.length === 11 && !s.startsWith('+')) s = '+' + s;
    return s;
  }

  function isValidPhone(value) {
    if (!value) return true;
    return /^\+?\d{10,15}$/.test(normalizePhone(value));
  }

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

  let opened = null; // {anchorEl, ownerEl}

  function closePortal() {
    portal.classList.remove('variant-portal--open');
    portal.innerHTML = '';
    if (opened?.anchorEl?.hasAttribute('aria-expanded')) opened.anchorEl.setAttribute('aria-expanded', 'false');
    if (opened?.ownerEl) opened.ownerEl.classList.remove('product-variant--open');
    opened = null;
  }

  function positionPortal(anchorEl) {
    const rect = anchorEl.getBoundingClientRect();
    portal.style.left = `${rect.left}px`;
    portal.style.top = `${rect.bottom + 8}px`;
    portal.style.width = `${rect.width}px`;
  }

  function collectAddressPayload(fields) {
    const payload = {
      label: (fields.fLabel?.value || '').trim(),
      city: (fields.fCity?.value || '').trim(),
      street: (fields.fStreet?.value || '').trim(),
      house: (fields.fHouse?.value || '').trim(),
      recipient_name: (fields.fName?.value || '').trim(),
      recipient_phone: normalizePhone(fields.fPhone?.value || '')
    };
    return payload;
  }

  function applyAddressToFields(fields, addr) {
    if (!addr) return;
    if (fields.fLabel) fields.fLabel.value = addr.label || '';
    if (fields.fCity) fields.fCity.value = addr.city || '';
    if (fields.fStreet) fields.fStreet.value = addr.street || '';
    if (fields.fHouse) fields.fHouse.value = addr.house || '';
    if (fields.fName) fields.fName.value = addr.recipient_name || '';
    if (fields.fPhone) fields.fPhone.value = addr.recipient_phone || '';
  }

  document.addEventListener('click', (e) => {
    if (!opened) return;
    if (portal.contains(e.target)) return;
    if (opened.ownerEl && opened.ownerEl.contains(e.target)) return;
    closePortal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePortal();
  });

  window.addEventListener('scroll', () => { if (opened?.anchorEl) positionPortal(opened.anchorEl); }, true);
  window.addEventListener('resize', () => { if (opened?.anchorEl) positionPortal(opened.anchorEl); });

  document.addEventListener('DOMContentLoaded', () => {
    const box = document.querySelector('.js-cart-delivery');
    if (!box) return;

    const select = box.querySelector('.js-cart-delivery-select');
    const button = box.querySelector('.js-cart-delivery-button');
    const label = box.querySelector('.js-cart-delivery-label');

    const selfPickup = document.querySelector('.js-self-pickup');
    const manual = document.querySelector('.js-manual-delivery');

    const fields = {
      fLabel: document.querySelector('.js-delivery-label'),
      fCity: document.querySelector('.js-delivery-city'),
      fStreet: document.querySelector('.js-delivery-street'),
      fHouse: document.querySelector('.js-delivery-house'),
      fName: document.querySelector('.js-recipient-name'),
      fPhone: document.querySelector('.js-recipient-phone'),
      phoneErr: document.querySelector('.js-phone-error'),
      saveBtn: document.querySelector('.js-save-delivery'),
      labelOptions: document.getElementById('delivery-label-options')
    };

    if (!select || !button || !label) return;

    const addressesByLabel = new Map();

    function setPhoneError(isVisible) {
      if (!fields.phoneErr) return;
      fields.phoneErr.style.display = isVisible ? '' : 'none';
    }

    function toggleBlocks(value) {
      const isSelf = value === 'self_pickup';
      if (selfPickup) selfPickup.style.display = isSelf ? '' : 'none';
      if (manual) manual.style.display = isSelf ? 'none' : '';
    }

    async function saveDeliveryType(value, textLabel) {
      if (textLabel) label.textContent = textLabel;
      const data = await apiPost('/api/cart/delivery-type/', { delivery_type: value });
      if (data?.delivery_type_label) label.textContent = data.delivery_type_label;
      if (data?.address) applyAddressToFields(fields, data.address);
      applyTotals(data);
      toggleBlocks(value);
    }

    function buildOptions() {
      portal.innerHTML = '';
      Array.from(select.options).forEach((opt) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'variant-portal__option' + (opt.value === select.value ? ' is-active' : '');
        b.textContent = opt.textContent;
        b.addEventListener('click', async (e) => {
          e.preventDefault();
          e.stopPropagation();
          select.value = opt.value;
          closePortal();
          try {
            await saveDeliveryType(opt.value, opt.textContent);
          } catch (err) {
            console.error(err);
            location.reload();
          }
        });
        portal.appendChild(b);
      });
    }

    button.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (opened && opened.anchorEl === button) {
        closePortal();
        return;
      }
      closePortal();
      opened = { anchorEl: button, ownerEl: box };
      box.classList.add('product-variant--open');
      button.setAttribute('aria-expanded', 'true');
      buildOptions();
      positionPortal(button);
      portal.classList.add('variant-portal--open');
    });

    select.addEventListener('change', async () => {
      try {
        const selected = select.options[select.selectedIndex];
        await saveDeliveryType(select.value, selected?.textContent || '');
      } catch (err) {
        console.error(err);
        location.reload();
      }
    });

    async function loadAddresses() {
      const data = await apiGet('/api/cart/addresses/');
      const list = Array.isArray(data) ? data : (data.results || []);
      addressesByLabel.clear();
      if (fields.labelOptions) fields.labelOptions.innerHTML = '';

      list.forEach((addr) => {
        const key = (addr.label || '').trim().toLowerCase();
        if (!key) return;
        if (!addressesByLabel.has(key)) addressesByLabel.set(key, addr);

        if (fields.labelOptions) {
          const opt = document.createElement('option');
          opt.value = addr.label || '';
          fields.labelOptions.appendChild(opt);
        }
      });
    }

    async function saveDraftAddress() {
      if (select.value === 'self_pickup') return;
      const payload = collectAddressPayload(fields);
      if (payload.recipient_phone && !isValidPhone(payload.recipient_phone)) {
        setPhoneError(true);
        throw new Error('invalid phone');
      }
      setPhoneError(false);
      const data = await apiPost('/api/cart/delivery/draft/', payload);
      applyTotals(data);
    }

    async function handleLabelSelectionOrBlur() {
      if (!fields.fLabel) return;
      if (select.value === 'self_pickup') return;

      const key = (fields.fLabel.value || '').trim().toLowerCase();
      if (!key) {
        await saveDraftAddress();
        return;
      }

      const addr = addressesByLabel.get(key);
      if (!addr) {
        await saveDraftAddress();
        return;
      }

      applyAddressToFields(fields, addr);
      await saveDraftAddress();
    }

    if (fields.fLabel) {
      fields.fLabel.addEventListener('focus', () => {
        loadAddresses().catch(console.error);
      });
      fields.fLabel.addEventListener('change', () => {
        handleLabelSelectionOrBlur().catch(console.error);
      });
      fields.fLabel.addEventListener('blur', () => {
        handleLabelSelectionOrBlur().catch(console.error);
      });
    }

    if (fields.fPhone) {
      fields.fPhone.addEventListener('input', () => {
        setPhoneError(!isValidPhone(fields.fPhone.value || ''));
      });
      fields.fPhone.addEventListener('blur', () => {
        if (!fields.fPhone.value) {
          setPhoneError(false);
          saveDraftAddress().catch(console.error);
          return;
        }
        const normalized = normalizePhone(fields.fPhone.value);
        fields.fPhone.value = normalized;
        const invalid = !isValidPhone(normalized);
        setPhoneError(invalid);
        if (!invalid) saveDraftAddress().catch(console.error);
      });
    }

    [fields.fCity, fields.fStreet, fields.fHouse, fields.fName].forEach((field) => {
      if (!field) return;
      field.addEventListener('blur', () => {
        saveDraftAddress().catch(console.error);
      });
    });

    if (fields.saveBtn) {
      fields.saveBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (select.value === 'self_pickup') return;

        const payload = collectAddressPayload(fields);
        if (!payload.label) {
          alert('Укажите название адреса.');
          return;
        }
        if (payload.recipient_phone && !isValidPhone(payload.recipient_phone)) {
          setPhoneError(true);
          return;
        }
        setPhoneError(false);

        try {
          const data = await apiPost('/api/cart/delivery/save-address/', payload);
          applyTotals(data);
          await loadAddresses();
        } catch (err) {
          if (err?.error === 'address_label required') {
            alert('Укажите название адреса.');
            return;
          }
          if (err?.error === 'invalid_phone') {
            setPhoneError(true);
            return;
          }
          console.error(err);
          alert('Не удалось сохранить адрес.');
        }
      });
    }

    toggleBlocks(select.value);
  });
})();
