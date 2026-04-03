(() => {
  function initCarousel(root){
    const track = root.querySelector('.js-carousel-track');
    if (!track) return;

    const slides = Array.from(track.children);
    if (slides.length <= 1) return;

    const prev = root.querySelector('.js-carousel-prev');
    const next = root.querySelector('.js-carousel-next');
    const thumbs = Array.from(document.querySelectorAll('.js-thumb'));

    let idx = 0;

    function setIndex(i){
      idx = Math.max(0, Math.min(slides.length - 1, i));
      track.style.transform = `translateX(${-idx * 100}%)`;

      thumbs.forEach(t => {
        const isActive = Number(t.dataset.index) === idx;
        t.classList.toggle('is-active', isActive);
        t.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
    }

    if (prev) prev.addEventListener('click', () => setIndex(idx - 1));
    if (next) next.addEventListener('click', () => setIndex(idx + 1));

    thumbs.forEach(t => {
      t.addEventListener('click', () => setIndex(Number(t.dataset.index)));
    });

    setIndex(0);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.js-carousel').forEach(initCarousel);
  });
})();


(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const sel = document.querySelector('.js-pdp-variant-select');
    if (!sel) return;

    sel.addEventListener('change', () => {
      const base = sel.dataset.groupUrl || window.location.pathname;
      const modId = sel.value;
      const url = new URL(base, window.location.origin);
      url.searchParams.set('mod', modId);
      window.location.href = url.toString();
    });
  });
})();

(() => {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
  }

  async function apiAdd(productId, delta) {
    const r = await fetch('/api/cart/add/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || '',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ product_id: String(productId), delta: Number(delta) })
    });

    // если не авторизован — обычно вернётся 302 на login, fetch увидит 200 HTML
    const ct = r.headers.get('content-type') || '';
    if (!r.ok) throw new Error('Cart add failed');
    if (!ct.includes('application/json')) throw new Error('Not JSON (maybe redirected to login)');

    return r.json();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.querySelector('.js-pdp-add-to-cart');
    if (!btn) return;

    btn.addEventListener('click', async (e) => {
      e.preventDefault();

      // product_id берём из data-product-id
      const pid = btn.dataset.productId;
      if (!pid) return;

      btn.disabled = true;
      try {
        const res = await apiAdd(pid, 1);

        // можно показывать количество в кнопке, если API возвращает qty
        if (res && res.qty != null) {
          btn.textContent = `В корзине: ${res.qty}`;
        } else {
          btn.textContent = 'Добавлено';
        }

        // если хочешь сразу перейти в корзину:
        // window.location.href = '/cart/';

      } catch (err) {
        console.error(err);
        alert('Не удалось добавить товар в корзину. Возможно, нужно войти в аккаунт.');
      } finally {
        btn.disabled = false;
      }
    });
  });
})();
