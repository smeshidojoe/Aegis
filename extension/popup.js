// Окно по значку на панели браузера: состояние связи, подключение к Aegis и
// записи текущего сайта.

const api = globalThis.browser ?? globalThis.chrome;
const RU = (navigator.language || "").toLowerCase().startsWith("ru");
const T = RU ? {
  noHost: "Aegis не запущен", noHostHint: "Запустите Aegis на компьютере. Если он запущен, " +
    "включите «Работать с расширением» в его настройках.",
  notPaired: "Не подключено", pairHint: "Подключите расширение — Aegis спросит разрешение.",
  pair: "Подключить к Aegis", waiting: "Подтвердите в окне Aegis…", denied: "Отклонено в Aegis",
  locked: "Заперт", unlocked: "Открыт", unlock: "Открыть Aegis", none: "Для этого сайта записей нет",
  open: "Открыть Aegis", unpair: "Отключить",
} : {
  noHost: "Aegis isn't running", noHostHint: "Start Aegis on your computer. If it's running, " +
    "turn on “Allow the Extension” in its settings.",
  notPaired: "Not connected", pairHint: "Connect the extension — Aegis will ask for permission.",
  pair: "Connect to Aegis", waiting: "Confirm in the Aegis window…", denied: "Denied in Aegis",
  locked: "Locked", unlocked: "Unlocked", unlock: "Unlock Aegis", none: "No entries for this site",
  open: "Open Aegis", unpair: "Disconnect",
};

const main = document.getElementById("main");
const state = document.getElementById("state");

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function btn(text, onClick, plain) {
  const b = el("button", plain ? "plain" : "", text);
  b.addEventListener("click", onClick);
  return b;
}

function tileColor(text) {
  let h = 0;
  for (const c of text.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h} 45% 40%)`;
}

async function activeTab() {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function render() {
  main.textContent = "";
  const status = await api.runtime.sendMessage({ type: "status" });
  if (!status.connected) {
    state.textContent = T.noHost;
    main.append(el("div", "note", T.noHostHint));
    return;
  }
  if (!status.paired) {
    state.textContent = T.notPaired;
    main.append(el("div", "note", T.pairHint), btn(T.pair, pair));
    return;
  }
  const tab = await activeTab();
  if (status.locked) {
    state.textContent = T.locked;
    main.append(btn(T.unlock, async () => {
      await api.runtime.sendMessage({ type: "unlock" });
      window.close();
    }));
    return;
  }
  state.textContent = T.unlocked;
  const reply = await api.runtime.sendMessage({ type: "query", url: tab?.url || "" });
  const entries = reply.entries || [];
  if (!entries.length) main.append(el("div", "note", T.none));
  for (const entry of entries) {
    const row = el("div", "row");
    const tile = el("div", "tile", (entry.title || "?").trim().charAt(0).toUpperCase());
    tile.style.background = tileColor(entry.title || "?");
    const text = el("div", "text");
    text.append(el("div", "title", entry.title), el("div", "sub", entry.username));
    row.append(tile, text);
    row.addEventListener("click", async () => {
      await api.runtime.sendMessage({ type: "fill-tab", tab_id: tab.id, entry_id: entry.id });
      window.close();
    });
    main.append(row);
  }
  main.append(btn(T.open, async () => {
    await api.runtime.sendMessage({ type: "open", url: tab?.url || "" });
    window.close();
  }, true), btn(T.unpair, async () => {
    await api.runtime.sendMessage({ type: "unpair" });
    render();
  }, true));
}

async function pair() {
  main.textContent = "";
  main.append(el("div", "note", T.waiting));
  const reply = await api.runtime.sendMessage({ type: "pair" });
  if (reply.type !== "paired") {
    main.textContent = "";
    main.append(el("div", "note", T.denied), btn(T.pair, pair));
    return;
  }
  render();
}

render();
