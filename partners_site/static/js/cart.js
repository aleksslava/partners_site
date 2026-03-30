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
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                        return;
                    }
                    alert(data.error || 'Не удалось оформить заказ');
                })
                .catch(() => {
                    alert('Ошибка при оформлении заказа');
                })
                .finally(() => {
                    checkoutButton.disabled = false;
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
