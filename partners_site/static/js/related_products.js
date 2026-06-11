(() => {
  let portal = null;
  let opened = null;
  let globalListenersReady = false;
  const priceFormatter = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0});

  function getCsrfToken() {
    const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenInput) {
      return tokenInput.value;
    }
    const match = document.cookie.match(new RegExp('(^| )csrftoken=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  function formatMoney(value) {
    const numberValue = Number(value);
    if (!Number.isFinite(numberValue)) {
      return '';
    }
    return `${priceFormatter.format(Math.round(numberValue))} \u20bd`;
  }

  function ensurePortal() {
    if (portal) {
      return;
    }
    portal = document.createElement('div');
    portal.className = 'variant-portal related-variant-portal';
    portal.setAttribute('role', 'listbox');
    document.body.appendChild(portal);
  }

  function closePortal() {
    if (!portal) {
      return;
    }
    portal.classList.remove('variant-portal--open');
    portal.innerHTML = '';
    if (opened?.button) {
      opened.button.setAttribute('aria-expanded', 'false');
    }
    if (opened?.dropdown) {
      opened.dropdown.classList.remove('product-variant--open');
    }
    opened = null;
  }

  function positionPortalUnderButton(button) {
    const rect = button.getBoundingClientRect();
    portal.style.left = `${rect.left}px`;
    portal.style.top = `${rect.bottom + 8}px`;
    portal.style.width = `${rect.width}px`;
  }

  function buildProductUrl(baseUrl, productId) {
    if (!baseUrl || !productId) {
      return baseUrl || '';
    }
    return `${baseUrl}?mod=${encodeURIComponent(productId)}`;
  }

  function applyModification(context, modification) {
    if (!modification) {
      return;
    }

    const discountPercent = Number(modification.discount_percent || 0);
    const hasDiscount = discountPercent > 0;
    const price = Number(modification.price || 0);
    const discountedPrice = Number(modification.discounted_price || price);

    if (context.priceElement) {
      context.priceElement.textContent = formatMoney(
        hasDiscount ? discountedPrice : price
      );
    }
    if (context.oldPriceWrapper) {
      context.oldPriceWrapper.style.display = hasDiscount ? '' : 'none';
    }
    if (context.discountElement) {
      context.discountElement.textContent = hasDiscount ? `-${discountPercent}%` : '';
    }
    if (context.oldPriceElement) {
      context.oldPriceElement.textContent = formatMoney(price);
    }

    if (context.imageElement) {
      if (modification.image_url) {
        context.imageElement.src = modification.image_url;
        context.imageElement.alt = modification.name || '';
        context.imageElement.style.display = '';
        if (context.placeholderElement) {
          context.placeholderElement.style.display = 'none';
        }
      } else {
        context.imageElement.removeAttribute('src');
        context.imageElement.style.display = 'none';
        if (context.placeholderElement) {
          context.placeholderElement.style.display = '';
        }
      }
    }

    context.detailsLinks.forEach((link) => {
      const baseUrl = link.dataset.baseHref || link.getAttribute('href') || '';
      link.href = buildProductUrl(baseUrl, modification.id);
    });

    if (context.labelElement) {
      context.labelElement.textContent = (
        modification.modification_name || modification.name || ''
      );
    }
    if (context.addButton) {
      context.addButton.dataset.productId = String(modification.id);
    }
  }

  function buildPortalOptions(context, activeProductId) {
    portal.innerHTML = '';

    context.modifications.forEach((modification) => {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = (
        'variant-portal__option' +
        (String(modification.id) === String(activeProductId) ? ' is-active' : '')
      );
      option.textContent = (
        modification.modification_name || modification.name || ''
      );
      option.dataset.value = String(modification.id);

      option.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();

        context.selectElement.value = String(modification.id);
        context.selectElement.dispatchEvent(new Event('change', {bubbles: true}));
        closePortal();
      });

      portal.appendChild(option);
    });
  }

  function initGlobalListeners() {
    if (globalListenersReady) {
      return;
    }
    globalListenersReady = true;

    document.addEventListener('click', (event) => {
      if (!opened) {
        return;
      }
      if (portal && portal.contains(event.target)) {
        return;
      }
      if (opened.dropdown && opened.dropdown.contains(event.target)) {
        return;
      }
      closePortal();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closePortal();
      }
    });

    window.addEventListener('scroll', () => {
      if (opened?.button) {
        positionPortalUnderButton(opened.button);
      }
    }, true);

    window.addEventListener('resize', () => {
      if (opened?.button) {
        positionPortalUnderButton(opened.button);
      }
    });
  }

  function parseModifications(card) {
    const groupId = card.dataset.groupId;
    const dataElement = document.getElementById(`related-mods-${groupId}`);
    if (!dataElement) {
      return [];
    }

    try {
      return JSON.parse(dataElement.textContent);
    } catch (error) {
      console.error(`related-mods-${groupId}: invalid JSON`, error);
      return [];
    }
  }

  function getCardContext(card) {
    return {
      card,
      modifications: parseModifications(card),
      priceElement: card.querySelector('.js-related-price'),
      oldPriceWrapper: card.querySelector('.js-related-old-wrap'),
      discountElement: card.querySelector('.js-related-discount'),
      oldPriceElement: card.querySelector('.js-related-old-price'),
      imageElement: card.querySelector('.js-related-image'),
      placeholderElement: card.querySelector('.js-related-image-placeholder'),
      detailsLinks: Array.from(card.querySelectorAll('.js-related-details-link')),
      dropdown: card.querySelector('.js-related-variant'),
      selectElement: card.querySelector('.js-related-variant-select'),
      buttonElement: card.querySelector('.js-related-variant-button'),
      labelElement: card.querySelector('.js-related-variant-label'),
      addButton: card.querySelector('.js-related-cart-add'),
    };
  }

  function initVariantSelector(context) {
    if (
      !context.dropdown ||
      !context.selectElement ||
      !context.buttonElement ||
      !context.labelElement
    ) {
      applyModification(context, context.modifications[0]);
      return;
    }

    context.selectElement.addEventListener('change', () => {
      const modification = context.modifications.find(
        (item) => String(item.id) === String(context.selectElement.value)
      );
      applyModification(context, modification);
    });

    context.selectElement.dispatchEvent(new Event('change', {bubbles: true}));

    context.buttonElement.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();

      ensurePortal();
      initGlobalListeners();

      if (opened && opened.card === context.card) {
        closePortal();
        return;
      }

      closePortal();
      opened = {
        card: context.card,
        dropdown: context.dropdown,
        selectElement: context.selectElement,
        button: context.buttonElement,
      };

      context.dropdown.classList.add('product-variant--open');
      context.buttonElement.setAttribute('aria-expanded', 'true');
      buildPortalOptions(context, context.selectElement.value);
      positionPortalUnderButton(context.buttonElement);
      portal.classList.add('variant-portal--open');
    });
  }

  function initAddButton(button) {
    button.addEventListener('click', () => {
      const productId = button.dataset.productId;
      if (!productId || button.disabled) {
        return;
      }

      const initialText = button.textContent;
      button.disabled = true;
      button.textContent = 'Добавляем';

      fetch('/api/cart/add/', {
        method: 'POST',
        body: JSON.stringify({
          product_id: productId,
          delta: 1,
          source: 'related_products',
        }),
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
      })
        .then((response) => (
          response.json().then((data) => ({ok: response.ok, data}))
        ))
        .then(({ok, data}) => {
          if (!ok || !data.success) {
            throw new Error(
              (data && data.message) || 'Не удалось добавить товар'
            );
          }
          location.reload();
        })
        .catch((error) => {
          button.disabled = false;
          button.textContent = initialText;
          alert(error.message || 'Не удалось добавить товар');
        });
    });
  }

  function initCard(card) {
    if (card.dataset.relatedProductsInit === '1') {
      return;
    }
    card.dataset.relatedProductsInit = '1';

    const context = getCardContext(card);
    if (!context.modifications.length) {
      return;
    }

    initVariantSelector(context);
    if (context.addButton) {
      initAddButton(context.addButton);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    ensurePortal();
    initGlobalListeners();
    document.querySelectorAll('.js-related-card').forEach(initCard);
  });
})();
