document.addEventListener('DOMContentLoaded', function () {
    function getCsrfToken() {
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        return tokenInput ? tokenInput.value : '';
    }

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
    const checkoutForm = checkoutButton ? checkoutButton.closest('form') : null;

    if (checkoutForm && checkoutButton) {
        checkoutForm.addEventListener('submit', function (event) {
            event.preventDefault();
            checkoutButton.disabled = true;

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
                });
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
                    document.getElementById('item-line-total-' + productId).textContent = data.item_total;
                    document.getElementById('cart-total').textContent = data.total;
                    document.getElementById('cart-discount').textContent = data.discount_total;
                    document.getElementById('cart-subtotal').textContent = data.subtotal;
                    document.getElementById('item-bonuses-append-' + productId).textContent = data.bonus_append;
                    document.getElementById('item-bonuses-spend-' + productId).textContent = data.bonus_spend;
                    document.getElementById('cart-bonuses-append').textContent = data.total_bonus_append;
                    document.getElementById('cart-bonuses-spent').textContent = data.total_bonus_spent;
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
