
(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('.js-pdp-variant');
    if (!root) return;

    const select = root.querySelector('.js-pdp-variant-select');
    const btn = root.querySelector('.js-pdp-variant-button');
    const label = root.querySelector('.js-pdp-variant-label');
    if (!select || !btn || !label) return;

    // один портал на страницу
    const portal = document.createElement('div');
    portal.className = 'variant-portal';
    portal.setAttribute('role', 'listbox');
    document.body.appendChild(portal);

    let open = false;

    function closePortal(){
      open = false;
      portal.classList.remove('variant-portal--open');
      portal.innerHTML = '';
      btn.setAttribute('aria-expanded', 'false');
      root.classList.remove('product-variant--open');
    }

    function positionPortal(){
      const rect = btn.getBoundingClientRect();
      portal.style.left = `${rect.left}px`;
      portal.style.top = `${rect.bottom + 8}px`;
      portal.style.width = `${rect.width}px`;
    }

    function buildOptions(){
      portal.innerHTML = '';
      Array.from(select.options).forEach(opt => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'variant-portal__option' + (opt.selected ? ' is-active' : '');
        b.textContent = opt.textContent;
        b.dataset.value = opt.value;

        b.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();

          select.value = opt.value;
          label.textContent = opt.textContent;
          closePortal();

          // Единая точка редиректа: обработчик change в product_group_detail.js
          select.dispatchEvent(new Event('change', { bubbles: true }));
        });

        portal.appendChild(b);
      });
    }

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (open) { closePortal(); return; }

      open = true;
      root.classList.add('product-variant--open');
      btn.setAttribute('aria-expanded', 'true');

      buildOptions();
      positionPortal();
      portal.classList.add('variant-portal--open');
    });

    document.addEventListener('click', (e) => {
      if (!open) return;
      if (portal.contains(e.target)) return;
      if (root.contains(e.target)) return;
      closePortal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePortal();
    });

    window.addEventListener('scroll', () => { if (open) positionPortal(); }, true);
    window.addEventListener('resize', () => { if (open) positionPortal(); });

    // начальный текст
    const current = select.options[select.selectedIndex];
    if (current) label.textContent = current.textContent;
  });
})();

