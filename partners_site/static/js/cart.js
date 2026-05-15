document.addEventListener('DOMContentLoaded', function () {
    function getCsrfToken() {
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        return tokenInput ? tokenInput.value : '';
    }

    const moneyFormatter = new Intl.NumberFormat('ru-RU');

    function formatMoney(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) {
            return value;
        }
        return moneyFormatter.format(Math.round(num));
    }

    function syncCartBonusRows() {
        document.querySelectorAll('.js-cart-bonus-row, .js-cart-discount-row, .js-cart-delivery-row').forEach(row => {
            const valueEl = row.querySelector('strong');
            const rawValue = valueEl ? valueEl.textContent.replace(/[^\d.-]/g, '') : '';
            const value = Number(rawValue || 0);
            row.style.display = value > 0 ? '' : 'none';
        });
    }

    window.syncCartBonusRows = syncCartBonusRows;
    syncCartBonusRows();

    document.querySelectorAll('.btn-increase').forEach(button => {
        button.addEventListener('click', function () {
            const productId = this.getAttribute('data-product-id');
            updateCartItem(productId, 1);
        });
    });

    document.querySelectorAll('.btn-decrease').forEach(button => {
        button.addEventListener('click', function () {
            const productId = this.getAttribute('data-product-id');
            updateCartItem(productId, -1);
        });
    });

    document.querySelectorAll('.btn-remove').forEach(button => {
        button.addEventListener('click', function () {
            const productId = this.getAttribute('data-product-id');
            removeCartItem(productId);
        });
    });

    const checkoutButton = document.querySelector('.js-checkout');
    const mobileCheckoutButton = document.querySelector('.js-mobile-checkout');
    const checkoutForm = checkoutButton ? checkoutButton.closest('form') : null;
    const termsCheckbox = document.querySelector('.js-cart-terms-input');
    const termsCheck = document.querySelector('.js-cart-terms-check');

    function setTermsHighlight(isError) {
        if (!termsCheck) {
            return;
        }
        termsCheck.classList.toggle('cart-check--error', isError);
    }

    function syncCheckoutState() {
        if (!termsCheckbox) {
            return;
        }
        const canCheckout = termsCheckbox.checked;
        [checkoutButton, mobileCheckoutButton].forEach(button => {
            if (!button) {
                return;
            }
            button.classList.toggle('is-disabled', !canCheckout);
            button.setAttribute('aria-disabled', String(!canCheckout));
        });
    }

    if (termsCheckbox) {
        syncCheckoutState();
        termsCheckbox.addEventListener('change', function () {
            if (this.checked) {
                setTermsHighlight(false);
            }
            syncCheckoutState();
        });
    }

    if (checkoutForm && checkoutButton) {
        checkoutForm.addEventListener('submit', function (event) {
            if (termsCheckbox && !termsCheckbox.checked) {
                event.preventDefault();
                setTermsHighlight(true);
                termsCheck?.scrollIntoView({behavior: 'smooth', block: 'center'});
                return;
            }

            event.preventDefault();
            setTermsHighlight(false);
            checkoutButton.disabled = true;
            if (mobileCheckoutButton) {
                mobileCheckoutButton.disabled = true;
            }

            fetch('/api/cart/checkout/', {
                method: 'POST',
                body: JSON.stringify({}),
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then(async response => {
                    const contentType = response.headers.get('Content-Type') || '';
                    let data = null;

                    if (contentType.includes('application/json')) {
                        data = await response.json();
                    } else if (response.redirected && response.url) {
                        window.location.href = response.url;
                        return;
                    }

                    if (!response.ok || !data || !data.success) {
                        throw new Error((data && data.error) || 'Не удалось оформить заказ');
                    }

                    window.location.href = data.redirect_url || '/cabinet/';
                })
                .catch(error => {
                    alert(error.message || 'Ошибка при оформлении заказа');
                })
                .finally(() => {
                    checkoutButton.disabled = false;
                    if (mobileCheckoutButton) {
                        mobileCheckoutButton.disabled = false;
                    }
                    syncCheckoutState();
                });
        });
    }

    if (mobileCheckoutButton && checkoutForm) {
        mobileCheckoutButton.addEventListener('click', function () {
            if (termsCheckbox && !termsCheckbox.checked) {
                setTermsHighlight(true);
                termsCheck?.scrollIntoView({behavior: 'smooth', block: 'center'});
                syncCheckoutState();
                return;
            }

            if (checkoutForm.requestSubmit) {
                checkoutForm.requestSubmit();
            } else {
                checkoutForm.dispatchEvent(new Event('submit', {cancelable: true}));
            }
        });
    }

    const mobileSectionMedia = window.matchMedia('(max-width: 640px), (max-aspect-ratio: 4/5)');
    const cartSections = Array.from(document.querySelectorAll('.js-cart-section'));

    function setCartSectionOpen(section, isOpen) {
        const toggle = section.querySelector('.js-cart-section-toggle');
        section.classList.toggle('is-open', isOpen);
        if (toggle) {
            toggle.setAttribute('aria-expanded', String(isOpen));
        }
    }

    function syncCartSections() {
        cartSections.forEach(section => {
            if (mobileSectionMedia.matches) {
                setCartSectionOpen(section, section.dataset.userOpen === 'true');
            } else {
                setCartSectionOpen(section, true);
            }
        });
    }

    cartSections.forEach(section => {
        const toggle = section.querySelector('.js-cart-section-toggle');
        if (!toggle) {
            return;
        }

        toggle.addEventListener('click', function () {
            if (!mobileSectionMedia.matches) {
                return;
            }
            const isOpen = !section.classList.contains('is-open');
            section.dataset.userOpen = String(isOpen);
            setCartSectionOpen(section, isOpen);
        });
    });

    if (cartSections.length) {
        syncCartSections();
        if (mobileSectionMedia.addEventListener) {
            mobileSectionMedia.addEventListener('change', syncCartSections);
        } else {
            mobileSectionMedia.addListener(syncCartSections);
        }
    }

    function syncSectionSummaries() {
        document.querySelectorAll('.js-cart-section-summary[data-summary-source]').forEach(summary => {
            const source = document.querySelector(summary.dataset.summarySource);
            if (source) {
                summary.textContent = source.textContent.trim();
            }
        });
    }

    syncSectionSummaries();
    document.querySelectorAll('.js-cart-section-summary[data-summary-source]').forEach(summary => {
        const source = document.querySelector(summary.dataset.summarySource);
        if (!source || !window.MutationObserver) {
            return;
        }

        new MutationObserver(syncSectionSummaries).observe(source, {
            childList: true,
            characterData: true,
            subtree: true,
        });
    });

    const cartTotal = document.getElementById('cart-total');
    const mobileTotal = document.getElementById('cart-mobile-total');

    function syncMobileTotal() {
        if (cartTotal && mobileTotal) {
            mobileTotal.textContent = cartTotal.textContent.trim();
        }
    }

    syncMobileTotal();
    if (cartTotal && mobileTotal && window.MutationObserver) {
        new MutationObserver(syncMobileTotal).observe(cartTotal, {
            childList: true,
            characterData: true,
            subtree: true,
        });
    }

    const needHelpCheckbox = document.querySelector('.js-cart-need-help');
    if (needHelpCheckbox) {
        needHelpCheckbox.addEventListener('change', function () {
            const nextValue = this.checked;
            this.disabled = true;

            fetch('/api/cart/set_need_help/', {
                method: 'POST',
                body: JSON.stringify({need_help: nextValue}),
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then(response => response.json().then(data => ({ok: response.ok, data})))
                .then(({ok, data}) => {
                    if (!ok || !data.success) {
                        throw new Error((data && data.error) || 'save failed');
                    }
                    needHelpCheckbox.checked = Boolean(data.need_help);
                })
                .catch(() => {
                    needHelpCheckbox.checked = !nextValue;
                    alert('Не удалось сохранить параметр "Нужна помощь с заказом"');
                })
                .finally(() => {
                    needHelpCheckbox.disabled = false;
                });
        });
    }

    function updateCartItem(productId, delta) {
        fetch('/api/cart/update_item/', {
            method: 'POST',
            body: JSON.stringify({product_id: productId, delta: delta}),
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (data.item_qty === 0) {
                        location.reload();
                        return;
                    }
                    document.getElementById('cart-item-qty-' + productId).textContent = data.item_qty;
                    document.getElementById('button-item-qty-' + productId).textContent = data.item_qty;
                    document.getElementById('item-line-total-' + productId).textContent = formatMoney(data.item_total);
                    const mobileLineTotal = document.getElementById('item-line-total-mobile-' + productId);
                    if (mobileLineTotal) {
                        mobileLineTotal.textContent = formatMoney(data.item_total);
                    }
                    document.getElementById('cart-total').textContent = formatMoney(data.total);
                    const mobileTotal = document.getElementById('cart-mobile-total');
                    if (mobileTotal) {
                        mobileTotal.textContent = formatMoney(data.total);
                    }
                    document.getElementById('cart-discount').textContent = formatMoney(data.discount_total);
                    document.getElementById('cart-subtotal').textContent = formatMoney(data.subtotal);
                    document.getElementById('cart-bonuses-append').textContent = data.total_bonus_append;
                    document.getElementById('cart-bonuses-spent').textContent = data.total_bonus_spent;
                    window.applyCartBonusSpendLimit?.(data);
                    syncCartBonusRows();
                }
            });
    }

    function removeCartItem(productId) {
        fetch('/cart/remove_item/', {
            method: 'POST',
            body: JSON.stringify({product_id: productId}),
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                }
            });
    }
});
