const tg = window.Telegram?.WebApp;

function syncThemeWithTelegram() {
  const scheme = tg?.colorScheme;
  if (scheme === "light" || scheme === "dark") {
    document.documentElement.setAttribute("data-theme", scheme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

try {
  tg?.ready();
  tg?.expand();
  syncThemeWithTelegram();
  tg?.onEvent?.("themeChanged", syncThemeWithTelegram);
} catch (_) {
  // Открыто не из Telegram — это ок для теста в браузере
}

const QUESTIONS = window.QUESTIONS || [];
if (!Array.isArray(QUESTIONS) || QUESTIONS.length !== 4) {
  console.error("QUESTIONS должен быть массивом из 4 вопросов");
}

const examLandingAssetBase = window.EXAM_LANDING_ASSET_BASE || "";

function resolveAssetPath(path) {
  if (!path || path.startsWith("/") || /^https?:\/\//i.test(path)) {
    return path;
  }

  return `${examLandingAssetBase}${path}`;
}

let index = 0;

// answers[qId][fieldId] = number
const answers = Object.fromEntries(QUESTIONS.map(q => [q.id, {}]));

const elProgress = document.getElementById("progress");
const elTaskText = document.getElementById("taskText");
const elTaskImage = document.getElementById("taskImage");
const elQuestionText = document.getElementById("questionText");
const elFields = document.getElementById("fields");
const elNextBtn = document.getElementById("nextBtn");
const elHint = document.getElementById("hint");
const elLightbox = document.getElementById("lightbox");
const elLightboxImage = document.getElementById("lightboxImage");
const elLightboxClose = document.getElementById("lightboxClose");

function openLightbox(src, altText = "") {
  if (!src || !elLightbox || !elLightboxImage) return;
  elLightboxImage.src = src;
  elLightboxImage.alt = altText;
  elLightbox.classList.add("open");
  elLightbox.setAttribute("aria-hidden", "false");
}

function closeLightbox() {
  if (!elLightbox || !elLightboxImage) return;
  elLightbox.classList.remove("open");
  elLightbox.setAttribute("aria-hidden", "true");
  elLightboxImage.src = "";
}

function allFieldsValid(q) {
  return q.fields.every(f => Number.isFinite(answers[q.id][f.id]));
}

function getVisibleFieldCount(q) {
  const firstEmptyIndex = q.fields.findIndex(f => !Number.isFinite(answers[q.id][f.id]));
  return firstEmptyIndex === -1 ? q.fields.length : firstEmptyIndex + 1;
}

function buildFieldRow(q, f) {
  const row = document.createElement("div");
  row.className = "fieldRow";

  const label = document.createElement("div");
  label.className = "fieldLabel";
  label.textContent = `${f.label} —`;

  const control = document.createElement("div");
  control.className = "fieldControl";

  const input = document.createElement("input");
  input.className = "fieldInput";
  input.type = "number";
  input.inputMode = "numeric";
  input.placeholder = "0";

  const current = answers[q.id][f.id];
  input.value = Number.isFinite(current) ? String(current) : "";

  const clearBtn = document.createElement("button");
  clearBtn.className = "fieldClear";
  clearBtn.type = "button";
  clearBtn.setAttribute("aria-label", `Очистить поле ${f.label}`);
  clearBtn.textContent = "×";
  clearBtn.hidden = !Number.isFinite(current);

  input.addEventListener("input", () => {
    const visibleBefore = getVisibleFieldCount(q);
    const raw = input.value.trim();

    if (raw === "") {
      answers[q.id][f.id] = 0;
      input.value = "0";
      clearBtn.hidden = false;
      const visibleAfterEmpty = getVisibleFieldCount(q);
      if (visibleAfterEmpty !== visibleBefore) {
        render();
        return;
      }
      updateButtonState();
      return;
    }

    const n = Number(raw);
    if (Number.isFinite(n)) {
      answers[q.id][f.id] = n;
    } else {
      answers[q.id][f.id] = 0;
      input.value = "0";
    }

    const visibleAfter = getVisibleFieldCount(q);
    if (visibleAfter !== visibleBefore) {
      const nextField = visibleAfter > visibleBefore ? q.fields[visibleBefore] : null;
      render({ focusFieldId: nextField?.id ?? null });
      return;
    }

    clearBtn.hidden = !Number.isFinite(answers[q.id][f.id]);
    updateButtonState();
  });

  clearBtn.addEventListener("click", () => {
    answers[q.id][f.id] = 0;
    input.value = "0";
    clearBtn.hidden = false;
    updateButtonState();
  });

  control.appendChild(input);
  control.appendChild(clearBtn);

  row.appendChild(label);
  row.appendChild(control);
  return row;
}

function updateButtonState() {
  const q = QUESTIONS[index];
  const ok = allFieldsValid(q);
  elNextBtn.disabled = !ok;

  elHint.textContent = ok ? "" : "Заполните все поля цифрами, чтобы продолжить.";
}

function render(options = {}) {
  const { focusFieldId = null } = options;
  const q = QUESTIONS[index];
  const isLast = index === QUESTIONS.length - 1;

  elProgress.textContent = `Страница ${index + 1} / ${QUESTIONS.length}`;

  elTaskText.textContent = q.taskText;
  elTaskImage.src = resolveAssetPath(q.image);
  elTaskImage.alt = `Изображение задачи ${index + 1}`;

  elQuestionText.textContent = q.questionText;

  elFields.innerHTML = "";
  const visibleFieldCount = getVisibleFieldCount(q);
  q.fields
    .slice(0, visibleFieldCount)
    .forEach(f => elFields.appendChild(buildFieldRow(q, f)));

  if (focusFieldId) {
    const focusIndex = q.fields.findIndex(f => f.id === focusFieldId);
    if (focusIndex >= 0 && focusIndex < visibleFieldCount) {
      const inputToFocus = elFields.querySelectorAll(".fieldInput")[focusIndex];
      inputToFocus?.focus();
      inputToFocus?.select?.();
    }
  }

  elNextBtn.textContent = isLast ? "Отправить ответы" : "Далее";

  updateButtonState();

  // Чтобы “страница” всегда начиналась сверху
  window.scrollTo({ top: 0, behavior: "instant" });
}

function nextOrSubmit() {
  const q = QUESTIONS[index];
  if (!allFieldsValid(q)) return;

  const isLast = index === QUESTIONS.length - 1;

  if (!isLast) {
    index += 1;
    render();
    return;
  }

  // Финальная отправка
  const payload = {
    answers,
    submittedAt: new Date().toISOString(),
    // initDataUnsafe может быть полезен боту (user id и т.д.), но не доверяй без проверки initData на сервере
    user: tg?.initDataUnsafe?.user ?? null,
  };

  if (tg?.sendData) {
    tg.sendData(JSON.stringify(payload));
    elHint.textContent = "Ответы отправлены";
    // Можно закрыть окно
    setTimeout(() => tg.close?.(), 200);
  } else {
    // Тест в обычном браузере
    window.EXAM_LANDING_LAST_PAYLOAD = payload;
    alert("Открыто не в Telegram. Ответы сформированы, но не отправлены.");
  }
}

elNextBtn.addEventListener("click", nextOrSubmit);
elTaskImage.addEventListener("click", () => {
  openLightbox(elTaskImage.src, elTaskImage.alt || "Увеличенное изображение задачи");
});

elLightboxClose?.addEventListener("click", closeLightbox);

elLightbox?.addEventListener("click", (event) => {
  if (event.target === elLightbox) {
    closeLightbox();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && elLightbox?.classList.contains("open")) {
    closeLightbox();
  }
});

render();
