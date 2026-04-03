// static/js/catalog_variants.js
(() => {
  let portal = null;
  let opened = null;
  let globalsReady = false;
  const priceFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

  function formatMoney(value) {
    if (value == null || value === '') return '';
    const num = Number(value);
    if (!Number.isFinite(num)) return '';
    return `${priceFormatter.format(num)} ₽`;
  }

  function ensurePortal() {
    if (portal) return;
    portal = document.createElement('div');
    portal.className = 'variant-portal';
    portal.setAttribute('role', 'listbox');
    document.body.appendChild(portal);
  }

  function closePortal() {
    if (!portal) return;
    portal.classList.remove('variant-portal--open');
    portal.innerHTML = '';
    if (opened?.btn) opened.btn.setAttribute('aria-expanded', 'false');
    if (opened?.dropdown) opened.dropdown.classList.remove('product-variant--open');
    opened = null;
  }

  function positionPortalUnderButton(btn) {
    const rect = btn.getBoundingClientRect();
    portal.style.left = `${rect.left}px`;
    portal.style.top = `${rect.bottom + 8}px`;
    portal.style.width = `${rect.width}px`;
  }

  function applyToCard(ctx, mod) {
    if (!mod) return;

    if (ctx.priceEl) ctx.priceEl.textContent = formatMoney(mod.price);

    if (ctx.discountPriceEl) {
      const discounted = formatMoney(mod.discounted_price);
      ctx.discountPriceEl.textContent = discounted || formatMoney(mod.price);
    }

    const discountPercent = Number(mod.discount_percent || 0);
    const hasDiscount = discountPercent > 0;

    if (ctx.oldWrapEl) ctx.oldWrapEl.style.display = hasDiscount ? '' : 'none';
    if (hasDiscount && ctx.badgeEl) ctx.badgeEl.textContent = `-${discountPercent}%`;

    if (ctx.descEl) ctx.descEl.textContent = mod.short_description || '';

    if (ctx.imgEl) {
      if (mod.image_url) {
        ctx.imgEl.src = mod.image_url;
        ctx.imgEl.alt = mod.name || ctx.imgEl.alt || '';
        ctx.imgEl.style.display = '';
      } else {
        ctx.imgEl.removeAttribute('src');
        ctx.imgEl.style.display = 'none';
      }
    }

    if (ctx.detailsLinks && ctx.detailsLinks.length) {
      ctx.detailsLinks.forEach((link) => {
        const base = link.dataset.baseHref || link.getAttribute('href') || '';
        if (!base) return;
        link.href = `${base}?mod=${mod.id}`;
      });
    }

    if (ctx.label) ctx.label.textContent = mod.name || '';
  }

  function buildPortalOptions(ctx, activeId) {
    portal.innerHTML = '';

    ctx.mods.forEach((mod) => {
      const opt = document.createElement('button');
      opt.type = 'button';
      opt.className = `variant-portal__option${String(mod.id) === String(activeId) ? ' is-active' : ''}`;
      opt.textContent = mod.name;
      opt.dataset.value = mod.id;

      opt.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        ctx.select.value = String(mod.id);
        ctx.select.dispatchEvent(new Event('change', { bubbles: true }));
        closePortal();
      });

      portal.appendChild(opt);
    });
  }

  function initGlobalListeners() {
    if (globalsReady) return;
    globalsReady = true;

    document.addEventListener('click', (e) => {
      if (!opened) return;
      if (portal && portal.contains(e.target)) return;
      if (opened.dropdown && opened.dropdown.contains(e.target)) return;
      closePortal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePortal();
    });

    window.addEventListener('scroll', () => {
      if (opened?.btn) positionPortalUnderButton(opened.btn);
    }, true);

    window.addEventListener('resize', () => {
      if (opened?.btn) positionPortalUnderButton(opened.btn);
    });
  }

  function initCard(card) {
    if (card.dataset.variantsInit === '1') return;
    card.dataset.variantsInit = '1';

    const groupId = card.dataset.groupId;

    const priceEl = card.querySelector('.js-product-price');
    const discountPriceEl = card.querySelector('.js-product-price-discount');
    const oldWrapEl = card.querySelector('.js-old-wrap');
    const badgeEl = card.querySelector('.js-discount-badge');

    const descEl = card.querySelector('.js-product-desc');
    const imgEl = card.querySelector('.js-product-image');
    const detailsLinks = card.querySelectorAll('.js-details-link');

    const select = card.querySelector('.js-variant-select');
    const dropdown = card.querySelector('.js-variant');
    const btn = card.querySelector('.js-variant-button');
    const label = card.querySelector('.js-variant-label');

    const jsonEl = document.getElementById(`mods-data-${groupId}`);
    if (!jsonEl) return;

    let mods = [];
    try {
      mods = JSON.parse(jsonEl.textContent);
    } catch (e) {
      console.error(`mods-data-${groupId}: invalid JSON`, e);
      return;
    }

    const ctxBase = {
      priceEl,
      discountPriceEl,
      oldWrapEl,
      badgeEl,
      descEl,
      imgEl,
      detailsLinks,
      select,
      mods,
      label,
    };

    if (!select) {
      applyToCard({ ...ctxBase, label: null, select: null }, mods[0]);
      if (window.syncCatalogCardRows) window.syncCatalogCardRows(document);
      return;
    }

    select.addEventListener('change', () => {
      const mod = mods.find((x) => String(x.id) === String(select.value));
      applyToCard(ctxBase, mod);
      if (window.syncCatalogCardRows) window.syncCatalogCardRows(document);
    });

    select.dispatchEvent(new Event('change', { bubbles: true }));

    if (!dropdown || !btn || !label) return;

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      ensurePortal();
      initGlobalListeners();

      if (opened && opened.card === card) {
        closePortal();
        return;
      }

      closePortal();

      opened = { card, dropdown, select, btn, label, mods };

      dropdown.classList.add('product-variant--open');
      btn.setAttribute('aria-expanded', 'true');

      buildPortalOptions(opened, select.value);
      positionPortalUnderButton(btn);
      portal.classList.add('variant-portal--open');
    });
  }

  window.initCatalogVariants = function initCatalogVariants(rootEl) {
    const root = rootEl || document;
    if (root.querySelector('.js-variant-button')) {
      ensurePortal();
      initGlobalListeners();
    }
    root.querySelectorAll('.js-product-card').forEach(initCard);
  };

  document.addEventListener('DOMContentLoaded', () => {
    window.initCatalogVariants(document);
  });
})();
