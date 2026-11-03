// Связь с Aegis на компьютере через native messaging.
//
// Браузер запускает посредника (Aegis.exe), тот передаёт сообщения в работающий
// Aegis. На каждое сообщение приходит ровно один ответ с тем же rid.
//
// Доступ к паролям — только после сопряжения: Aegis показывает вопрос, и если
// его разрешили, выдаёт ключ. Ключ хранится в chrome.storage.local и уходит с
// каждым запросом.

const HOST = "com.smeshidojoe.aegis";
const api = globalThis.browser ?? globalThis.chrome;

let port = null;
let seq = 0;
const pending = new Map();

function connect() {
  port = api.runtime.connectNative(HOST);
  port.onMessage.addListener((message) => {
    const resolve = pending.get(message.rid);
    if (resolve) {
      pending.delete(message.rid);
      resolve(message);
    }
  });
  port.onDisconnect.addListener(() => {
    const detail = api.runtime.lastError?.message || "";
    port = null;
    for (const resolve of pending.values()) {
      resolve({ type: "error", error: "no_host", detail });
    }
    pending.clear();
  });
}

// Ожидание ответа: на «pair» человек отвечает в Aegis, это может занять минуту.
function send(message, timeoutMs = 10000) {
  return new Promise((resolve) => {
    const rid = ++seq;
    pending.set(rid, resolve);
    try {
      if (!port) connect();
      port.postMessage({ ...message, rid });
    } catch (error) {
      pending.delete(rid);
      resolve({ type: "error", error: "no_host", detail: String(error) });
      return;
    }
    setTimeout(() => {
      if (pending.has(rid)) {
        pending.delete(rid);
        resolve({ type: "error", error: "timeout" });
      }
    }, timeoutMs);
  });
}

function browserName() {
  const ua = navigator.userAgent;
  if (ua.includes("YaBrowser")) return ["Yandex Browser", "browser.exe"];
  if (ua.includes("Edg/")) return ["Microsoft Edge", "msedge.exe"];
  if (ua.includes("OPR/")) return ["Opera", "opera.exe"];
  if (ua.includes("Vivaldi")) return ["Vivaldi", "vivaldi.exe"];
  if (ua.includes("Firefox/")) return ["Firefox", "firefox.exe"];
  if (navigator.brave) return ["Brave", "brave.exe"];
  return ["Google Chrome", "chrome.exe"];
}

async function credentials() {
  const { pair_id, key } = await api.storage.local.get(["pair_id", "key"]);
  return { pair_id, key };
}

async function call(type, extra = {}, timeoutMs) {
  const auth = await credentials();
  if (!auth.key) return { type: "error", error: "not_paired" };
  const reply = await send({ type, ...auth, ...extra }, timeoutMs);
  if (reply.error === "not_paired") {
    // Сопряжение сняли в настройках Aegis — ключ больше не действует.
    await api.storage.local.remove(["pair_id", "key"]);
  }
  return reply;
}

async function pair() {
  const reply = await send({ type: "pair", browser: browserName()[0] }, 70000);
  if (reply.type === "paired") {
    await api.storage.local.set({ pair_id: reply.pair_id, key: reply.key });
  }
  return reply;
}

async function status() {
  const ping = await send({ type: "ping" });
  if (ping.type !== "pong") return { connected: false, error: ping.error };
  const hello = await call("hello", { browser: browserName()[0] });
  if (hello.type === "hello") return { connected: true, paired: true, locked: hello.locked };
  return { connected: true, paired: false, error: hello.error };
}

// --- адрес активной вкладки ------------------------------------------------ //
// Aegis по хоткею сразу показывает записи сайта: адрес он берёт отсюда, точнее
// и быстрее, чем из окна браузера.

let lastReported = "";

async function reportActiveTab() {
  try {
    const [tab] = await api.tabs.query({ active: true, lastFocusedWindow: true });
    const url = tab?.url || "";
    if (!url || url === lastReported || !/^https?:/.test(url)) return;
    const auth = await credentials();
    if (!auth.key) return;
    lastReported = url;
    await call("tab", { url, process: browserName()[1] });
  } catch (_) {
    // Нет Aegis — не страшно, хоткей прочитает адрес сам.
  }
}

api.tabs.onActivated.addListener(reportActiveTab);
api.tabs.onUpdated.addListener((_id, change, tab) => {
  if (change.url && tab.active) reportActiveTab();
});
api.windows.onFocusChanged.addListener(reportActiveTab);

// --- сообщения от страниц и всплывающего окна ------------------------------- //

async function fillTab(tabId, entryId, url) {
  const reply = await call("fill", { url, entry_id: entryId });
  if (reply.type === "credentials") {
    await api.tabs.sendMessage(tabId, { type: "aegis-fill", username: reply.username,
                                        password: reply.password, totp: reply.totp });
  }
  return reply;
}

async function handle(message, sender) {
  // Из всплывающего окна адрес приходит в сообщении (sender там — само окно),
  // со страницы — адрес её фрейма: форма входа бывает во фрейме другого сайта.
  const url = sender.tab ? (sender.url || sender.tab.url || "") : (message.url || "");
  switch (message.type) {
    case "status":
      return status();
    case "pair":
      return pair();
    case "unpair":
      await api.storage.local.remove(["pair_id", "key"]);
      return { type: "ok" };
    case "query":
      return call("query", { url });
    case "fill":
      return call("fill", { url, entry_id: message.entry_id });
    case "fill-tab":
      return fillTab(message.tab_id, message.entry_id, message.url);
    case "unlock":
      return call("unlock");
    case "open":
      return call("open", { url });
    case "save": {
      // Предлагать сохранить, только если такой пары логин+пароль у сайта ещё нет.
      const known = await call("query", { url, username: message.username,
                                          password: message.password });
      if (known.type === "entries" && known.known) return { type: "ok" };
      return call("save", { url, username: message.username, password: message.password });
    }
    default:
      return { type: "error", error: "unknown" };
  }
}

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handle(message, sender).then(sendResponse);
  return true;   // ответ придёт асинхронно
});
