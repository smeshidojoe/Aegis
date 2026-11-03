// Значок Aegis в полях входа и подстановка логина и пароля.
//
// Ищем поля пароля, к каждому — поле логина перед ним. Справа в поле пароля
// (и логина) — маленький щит; клик открывает список записей этого сайта из
// Aegis. Пароли сюда приходят только для выбранной записи.
//
// Значок и список живут в своём Shadow DOM: стили сайта их не ломают, а наши
// не трогают сайт.

(() => {
  if (window.__aegis) return;
  window.__aegis = true;

  const api = globalThis.browser ?? globalThis.chrome;
  const RU = (navigator.language || "").toLowerCase().startsWith("ru");
  const T = RU ? {
    locked: "Aegis заперт", unlock: "Открыть Aegis", none: "Для этого сайта записей нет",
    pair: "Расширение не подключено к Aegis", pairHint: "Нажмите значок Aegis на панели браузера",
    noHost: "Aegis не запущен или не установлен", open: "Открыть Aegis",
  } : {
    locked: "Aegis is locked", unlock: "Unlock Aegis", none: "No entries for this site",
    pair: "The extension isn't connected to Aegis", pairHint: "Click the Aegis icon in the toolbar",
    noHost: "Aegis isn't running or installed", open: "Open Aegis",
  };

  const SHIELD = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" ' +
    'd="M12 2.2c1.9 1 4.6 1.5 7.8 1.6v6.9c0 5.3-3.4 9.2-7.8 11.1C7.6 19.9 4.2 16 4.2 10.7V3.8' +
    'c3.2-.1 5.9-.6 7.8-1.6Zm0 5.3a2.1 2.1 0 0 0-1.1 3.9l-.6 4.3h3.4l-.6-4.3A2.1 2.1 0 0 0 12 7.5Z"/></svg>';

  const host = document.createElement("aegis-root");
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .icon { position: fixed; z-index: 2147483646; width: 22px; height: 22px; border-radius: 6px;
              display: flex; align-items: center; justify-content: center; cursor: pointer;
              background: #000; color: #fff; opacity: .85; box-shadow: 0 1px 3px rgba(0,0,0,.35); }
      .icon:hover { opacity: 1; }
      .menu { position: fixed; z-index: 2147483647; min-width: 260px; max-width: 360px;
              background: #28282e; color: rgba(255,255,255,.92); border-radius: 12px; padding: 5px;
              border: 1px solid rgba(255,255,255,.12); box-shadow: 0 10px 30px rgba(0,0,0,.45);
              font: 13px/1.35 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; }
      .row { display: flex; gap: 10px; align-items: center; padding: 7px 9px; border-radius: 8px;
             cursor: pointer; }
      .row:hover, .row.sel { background: rgba(255,255,255,.1); }
      .tile { width: 26px; height: 26px; border-radius: 7px; flex: none; display: flex;
              align-items: center; justify-content: center; font-weight: 600; color: #fff; }
      .title { font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .sub { color: rgba(255,255,255,.5); font-size: 12px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }
      .text { min-width: 0; }
      .note { padding: 9px 10px; color: rgba(255,255,255,.62); }
      .button { margin: 2px 4px 4px; padding: 7px 10px; border-radius: 8px; text-align: center;
                background: #0a84ff; color: #fff; cursor: pointer; }
    </style>`;
  let attached = false;
  function attach() {
    if (!attached && document.documentElement) {
      document.documentElement.appendChild(host);
      attached = true;
    }
  }

  const icons = new Map();     // поле -> значок
  let menu = null;
  let menuField = null;

  // --- поиск полей -------------------------------------------------------- //

  function visible(el) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return r.width > 30 && r.height > 12 && style.visibility !== "hidden" && style.display !== "none";
  }

  function usernameFor(password) {
    const scope = password.form || document;
    const inputs = [...scope.querySelectorAll("input")].filter((i) =>
      ["text", "email", "tel", ""].includes(i.type) && visible(i) && !i.readOnly && !i.disabled);
    let best = null;
    for (const input of inputs) {
      if (input.compareDocumentPosition(password) & Node.DOCUMENT_POSITION_FOLLOWING) best = input;
    }
    return best;
  }

  function scan() {
    const fields = new Set();
    for (const password of document.querySelectorAll('input[type="password"]')) {
      if (!visible(password)) continue;
      fields.add(password);
      const user = usernameFor(password);
      if (user) fields.add(user);
    }
    for (const [field, icon] of icons) {
      if (!fields.has(field) || !field.isConnected) {
        icon.remove();
        icons.delete(field);
      }
    }
    for (const field of fields) {
      if (!icons.has(field)) addIcon(field);
    }
    place();
  }

  function addIcon(field) {
    attach();
    const icon = document.createElement("div");
    icon.className = "icon";
    icon.innerHTML = SHIELD;
    icon.title = "Aegis";
    icon.addEventListener("mousedown", (e) => e.preventDefault());
    icon.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMenu(field);
    });
    shadow.appendChild(icon);
    icons.set(field, icon);
  }

  function place() {
    for (const [field, icon] of icons) {
      const r = field.getBoundingClientRect();
      const offscreen = r.bottom < 0 || r.top > innerHeight || !visible(field);
      icon.style.display = offscreen ? "none" : "flex";
      icon.style.left = `${r.right - 22 - Math.min(8, (r.height - 22) / 2 + 2)}px`;
      icon.style.top = `${r.top + (r.height - 22) / 2}px`;
    }
    if (menu && menuField) positionMenu();
  }

  // --- список записей ------------------------------------------------------ //

  function tileColor(text) {
    let h = 0;
    for (const c of text.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h} 45% 40%)`;
  }

  function closeMenu() {
    menu?.remove();
    menu = null;
    menuField = null;
  }

  function positionMenu() {
    const r = menuField.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
    const below = r.bottom + 6;
    menu.style.top = below + menu.offsetHeight < innerHeight ? `${below}px`
      : `${Math.max(8, r.top - menu.offsetHeight - 6)}px`;
  }

  function note(text) {
    const div = document.createElement("div");
    div.className = "note";
    div.textContent = text;
    return div;
  }

  function button(text, onClick) {
    const div = document.createElement("div");
    div.className = "button";
    div.textContent = text;
    div.addEventListener("mousedown", (e) => e.preventDefault());
    div.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
    return div;
  }

  async function toggleMenu(field) {
    if (menu && menuField === field) { closeMenu(); return; }
    closeMenu();
    menuField = field;
    menu = document.createElement("div");
    menu.className = "menu";
    menu.addEventListener("mousedown", (e) => e.preventDefault());
    shadow.appendChild(menu);
    positionMenu();
    const reply = await api.runtime.sendMessage({ type: "query" });
    if (!menu || menuField !== field) return;
    render(reply);
    positionMenu();
  }

  function render(reply) {
    menu.textContent = "";
    if (reply.type === "error") {
      if (reply.error === "not_paired") {
        menu.append(note(T.pair), note(T.pairHint));
      } else {
        menu.append(note(T.noHost));
      }
      return;
    }
    if (reply.locked) {
      menu.append(note(T.locked), button(T.unlock, () => {
        api.runtime.sendMessage({ type: "unlock" });
        closeMenu();
      }));
      return;
    }
    if (!reply.entries.length) {
      menu.append(note(T.none), button(T.open, () => {
        api.runtime.sendMessage({ type: "open" });
        closeMenu();
      }));
      return;
    }
    for (const entry of reply.entries) {
      const row = document.createElement("div");
      row.className = "row";
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.style.background = tileColor(entry.title || "?");
      tile.textContent = (entry.title || "?").trim().charAt(0).toUpperCase();
      const text = document.createElement("div");
      text.className = "text";
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = entry.title;
      const sub = document.createElement("div");
      sub.className = "sub";
      sub.textContent = entry.username;
      text.append(title, sub);
      row.append(tile, text);
      row.addEventListener("click", async (e) => {
        e.stopPropagation();
        const field = menuField;
        closeMenu();
        const creds = await api.runtime.sendMessage({ type: "fill", entry_id: entry.id });
        if (creds.type === "credentials") fill(creds, field);
      });
      menu.append(row);
    }
  }

  // --- подстановка --------------------------------------------------------- //

  // Через сеттер прототипа: React и Vue следят за value своим сеттером и
  // присвоение напрямую пропустили бы мимо.
  function setValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    input.focus();
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fill(creds, near) {
    let password = near?.type === "password" ? near : null;
    if (!password) {
      const all = [...document.querySelectorAll('input[type="password"]')].filter(visible);
      password = near?.form ? all.find((p) => p.form === near.form) : all[0];
    }
    const user = password ? usernameFor(password) : (near?.type !== "password" ? near : null);
    if (user && creds.username) setValue(user, creds.username);
    if (password) setValue(password, creds.password);
    lastFilled = creds.password;
  }

  api.runtime.onMessage.addListener((message) => {
    if (message.type === "aegis-fill" && document.querySelector('input[type="password"]')) {
      fill(message, document.activeElement instanceof HTMLInputElement ? document.activeElement
        : null);
    }
  });

  // --- предложение сохранить ------------------------------------------------ //

  let lastFilled = "";
  let lastOffered = "";

  function offerSave(form) {
    const password = [...(form || document).querySelectorAll('input[type="password"]')]
      .find((p) => p.value);
    if (!password || password.value === lastFilled || password.value === lastOffered) return;
    lastOffered = password.value;
    const user = usernameFor(password);
    api.runtime.sendMessage({ type: "save", username: user?.value || "",
                              password: password.value });
  }

  document.addEventListener("submit", (e) => offerSave(e.target), true);
  document.addEventListener("click", (e) => {
    const target = e.target.closest?.('button, input[type="submit"], [role="button"]');
    if (target && document.querySelector('input[type="password"]')) {
      offerSave(target.form || target.closest("form"));
    }
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target instanceof HTMLInputElement
        && document.querySelector('input[type="password"]')) {
      offerSave(e.target.form);
    }
  }, true);

  // --- наблюдение --------------------------------------------------------- //

  let scanTimer = 0;
  function scheduleScan() {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(scan, 400);
  }

  document.addEventListener("click", (e) => { if (menu && !e.composedPath().includes(host)) closeMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  addEventListener("scroll", () => requestAnimationFrame(place), true);
  addEventListener("resize", () => requestAnimationFrame(place));
  new MutationObserver(scheduleScan).observe(document.documentElement,
                                             { childList: true, subtree: true, attributes: true,
                                               attributeFilter: ["type", "style", "class"] });
  scan();
})();
