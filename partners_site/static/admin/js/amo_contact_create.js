(function () {
  "use strict";

  window.addEventListener("DOMContentLoaded", function () {
    const input = document.querySelector('input[name="amo_id_contact"]');
    const button = document.querySelector("[data-amo-contact-create-button]");

    if (!input || !button) {
      return;
    }

    const syncButtonState = function () {
      button.disabled = !/^\d+$/.test(input.value.trim());
    };

    input.addEventListener("input", syncButtonState);
    syncButtonState();
  });
})();
