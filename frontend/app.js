/* TradeSim Mini App (DEMO). All data is simulated. */
// API base resolution:
//  - explicit override via window.TRADESIM_API wins;
//  - standalone dev server (python http.server on :5500) or file:// -> talk to backend on :8000;
//  - otherwise (served by the backend itself, incl. via HTTPS tunnel) -> same origin.
const API = (typeof window.TRADESIM_API === "string")
  ? window.TRADESIM_API
  : (location.port === "5500" || location.protocol === "file:")
    ? "http://localhost:8000"
    : location.origin;
const WS_URL = API.replace(/^http/, "ws") + "/ws";

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

const $ = (id) => document.getElementById(id);

function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (tg && tg.initData) h["X-Init-Data"] = tg.initData;
  else h["X-Dev-User-Id"] = localStorage.getItem("devUserId") || "100001";
  return h;
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: authHeaders(), ...opts });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.status); }
  return res.json();
}

let me = null;
const trades = new Map();

/* ---------------- UI helpers ---------------- */
function toast(message, type = "info", ms = 3200) {
  const host = $("toast-host");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-bar"></span><span>${message}</span>`;
  host.appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 350); }, ms);
}

function confirmModal(title, body, okText = "Подтвердить") {
  return new Promise((resolve) => {
    $("confirm-title").textContent = title;
    $("confirm-body").innerHTML = body;
    $("confirm-ok").textContent = okText;
    const overlay = $("confirm-modal");
    overlay.classList.add("on");
    const done = (val) => { overlay.classList.remove("on"); resolve(val); };
    $("confirm-ok").onclick = () => done(true);
    $("confirm-cancel").onclick = () => done(false);
    overlay.onclick = (e) => { if (e.target === overlay) done(false); };
  });
}

function animateNumber(el, to, { decimals = 0, duration = 700 } = {}) {
  const from = parseFloat((el.dataset.val || "0")) || 0;
  el.dataset.val = to;
  const start = performance.now();
  function step(now) {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = from + (to - from) * eased;
    el.textContent = decimals ? val.toFixed(decimals) : Math.round(val).toLocaleString("ru-RU");
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ripple on buttons */
document.addEventListener("pointerdown", (e) => {
  const btn = e.target.closest(".btn");
  if (!btn) return;
  const r = btn.getBoundingClientRect();
  const ink = document.createElement("span");
  ink.className = "ripple";
  const size = Math.max(r.width, r.height);
  ink.style.width = ink.style.height = size + "px";
  ink.style.left = (e.clientX - r.left - size / 2) + "px";
  ink.style.top = (e.clientY - r.top - size / 2) + "px";
  btn.appendChild(ink);
  setTimeout(() => ink.remove(), 600);
});

/* ---------------- tabs ---------------- */
document.querySelectorAll(".tabitem").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tabitem").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".screen").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $(t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "tx") loadTx(true);
  };
});

/* ---------------- dashboard ---------------- */
async function loadMe(animate = false) {
  me = await api("/api/me");
  animateNumber($("balance"), me.balance, { decimals: 2, duration: animate ? 900 : 400 });
  $("tier-chip").textContent = `Этап ${me.tier} · ${me.tier_name}`;

  $("level-badge").textContent = me.level.toUpperCase();
  if (me.next_level) {
    const remaining = me.next_level_at - me.total_trades;
    $("level-meta").textContent = `${remaining} сделок до ${me.next_level.toUpperCase()}`;
    // progress from previous threshold to next
    const pct = Math.max(4, Math.min(100, (me.total_trades / me.next_level_at) * 100));
    $("level-progress").style.width = pct + "%";
  } else {
    $("level-meta").textContent = "Максимальный уровень";
    $("level-progress").style.width = "100%";
  }

  renderTiers();
  renderInfoGrid();
  updateBookHint();
}

function renderInfoGrid() {
  $("info-grid").innerHTML = `
    <div class="stat"><div class="stat-label">Сделок сегодня</div><div class="stat-value">${me.remaining_trades_today} / ${me.daily_limit}</div></div>
    <div class="stat"><div class="stat-label">Цена буста</div><div class="stat-value">${me.next_boost_price} <span style="font-size:12px;color:var(--muted)">УЕ</span></div></div>
    <div class="stat"><div class="stat-label">Всего сделок</div><div class="stat-value">${me.total_trades}</div></div>
    <div class="stat"><div class="stat-label">Реф. бонус</div><div class="stat-value">${me.referral_earnings} <span style="font-size:12px;color:var(--muted)">УЕ</span></div></div>
  `;
}

async function renderTiers() {
  const tiers = await api("/api/tiers");
  const box = $("tiers");
  box.innerHTML = "";
  tiers.forEach((t) => {
    const d = document.createElement("div");
    d.className = "tier" + (t.tier === me.tier ? " active" : "");
    d.innerHTML =
      (t.tier === me.tier ? '<span class="tier-current"></span>' : "") +
      `<div class="tier-num">Этап ${t.tier}</div><div class="tier-price">${t.price}</div><div class="tier-lim">${t.daily_limit}/сутки</div>`;
    d.onclick = async () => {
      if (t.tier === me.tier) { toast("Этот этап уже активен", "info"); return; }
      const ok = await confirmModal(
        `Этап ${t.tier} · ${t.daily_limit}/сутки`,
        `Списать <b>${t.price} УЕ</b> (виртуальные) и активировать этап на 30 дней?`,
        "Активировать"
      );
      if (!ok) return;
      try { me = await api(`/api/subscribe/${t.tier}`, { method: "POST" }); await loadMe(); toast(`Этап ${t.tier} активирован`, "success"); }
      catch (e) { toast(e.message, "error"); }
    };
    box.appendChild(d);
  });
}

function updateBookHint() {
  const hint = $("book-hint");
  if (me && me.tier < 2) {
    hint.className = "book-head locked";
    hint.innerHTML = "Стакан открывается на <b>Этапе 2</b>. Сейчас Этап 1 — только наблюдение за сделками.";
  } else {
    hint.className = "book-head";
    hint.innerHTML = `Доступно сделок сегодня: <b>${me ? me.remaining_trades_today : "—"}</b> · нажмите «Принять» на зелёной карточке`;
  }
}

/* ---------------- order book ---------------- */
function fmt(n) { return Math.round(n).toLocaleString("ru-RU"); }

function renderCard(t) {
  let el = $("card-" + t.id);
  const isNew = !el;
  if (isNew) {
    el = document.createElement("div");
    el.id = "card-" + t.id;
    $("cards").prepend(el);
    $("book-empty").style.display = "none";
  }
  const win = t.profit >= 0;
  el.className = "tcard " + t.state + (t.state === "completed" ? (win ? " win" : " loss") : "");

  let inner = `<div class="asset">${t.asset}</div><div class="vol">${fmt(t.volume)} USDT</div>`;
  if (t.state === "analyzing") {
    inner += `<div class="state"><span class="spin"></span> Анализ…</div><div class="shimmer"></div>`;
  } else if (t.state === "open") {
    inner += `<div class="pnl ${win ? "pos" : "neg"}">${win ? "+" : ""}${fmt(t.profit)} УЕ</div>`;
    inner += `<div class="timer-wrap" id="tw-${t.id}"><div class="timer-bar"><div class="timer-fill" id="tf-${t.id}" style="width:100%"></div></div><div class="timer-row"><span class="timer-label" id="tl-${t.id}">15:00</span></div></div>`;
    if (me && me.tier === 2) inner += `<button class="btn accept" onclick="acceptTrade(${t.id})">Принять</button>`;
    else if (me && me.tier === 3) inner += `<div class="auto-badge"><span class="conn-dot" style="position:static;background:var(--blue)"></span> Авто-приём</div>`;
  } else if (t.state === "accepted") {
    inner += `<div class="state" style="color:var(--blue)"><span class="spin" style="border-top-color:var(--blue)"></span> Исполняется…</div>`;
  } else if (t.state === "completed") {
    inner += `<div class="state ${win ? "pos" : "neg"}">${win ? "Завершено · прибыль" : "Завершено · убыток"}</div><div class="pnl ${win ? "pos" : "neg"}">${win ? "+" : ""}${fmt(t.profit)} УЕ</div>`;
  } else if (t.state === "missed") {
    inner += `<div class="state" style="color:var(--faint)">Пропущена</div>`;
  }
  el.innerHTML = inner;
}

function startTimer(id, totalSecs) {
  const t = trades.get(id);
  if (!t) return;
  const deadline = Date.now() + totalSecs * 1000;
  if (t.interval) clearInterval(t.interval);
  t.interval = setInterval(() => {
    const remain = Math.max(0, deadline - Date.now());
    const fill = $("tf-" + id), label = $("tl-" + id), wrap = $("tw-" + id);
    if (!fill) { clearInterval(t.interval); return; }
    fill.style.width = (remain / (totalSecs * 1000)) * 100 + "%";
    const s = Math.ceil(remain / 1000);
    if (label) label.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    if (wrap) wrap.classList.toggle("warn", remain <= 30000);
    if (remain <= 0) clearInterval(t.interval);
  }, 250);
}

window.acceptTrade = async function (id) {
  const t = trades.get(id);
  const latency = t && t.openedAt ? Date.now() - t.openedAt : null;
  try {
    const r = await api(`/api/trades/${id}/accept` + (latency ? `?latency_ms=${latency}` : ""), { method: "POST" });
    if (!r.ok) {
      if (r.detail.includes("буст")) {
        const ok = await confirmModal("Лимит исчерпан", `${r.detail}<br><br>Купить дополнительную сделку (буст)?`, "Купить буст");
        if (ok) {
          try { me = await api("/api/boosts/buy", { method: "POST" }); await loadMe(); toast("Буст куплен — нажмите «Принять» снова", "success"); }
          catch (e) { toast(e.message, "error"); }
        }
      } else toast(r.detail, "error");
      return;
    }
    await loadMe();
    toast("Сделка принята · идёт исполнение", "info");
  } catch (e) { toast(e.message, "error"); }
};

async function loadInitialTrades() {
  const list = await api("/api/trades?limit=30");
  $("cards").innerHTML = "";
  if (!list.length) { $("book-empty").style.display = "block"; return; }
  $("book-empty").style.display = "none";
  list.reverse().forEach((t) => { trades.set(t.id, { data: t }); renderCard(t); });
}

/* ---------------- websocket ---------------- */
let ws, reconnectDelay = 1000;
function setConn(on, text) {
  const c = $("conn");
  c.classList.toggle("on", on);
  $("conn-text").textContent = text;
}
function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { setConn(true, "online"); reconnectDelay = 1000; };
  ws.onclose = () => {
    setConn(false, "переподключение…");
    setTimeout(connectWS, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 16000);
  };
  ws.onmessage = (ev) => handleWS(JSON.parse(ev.data));
}

function handleWS(msg) {
  if (msg.counters) {
    animateNumber($("c-analyzed"), msg.counters.analyzed, { duration: 500 });
    animateNumber($("c-profitable"), msg.counters.profitable, { duration: 500 });
  }
  if (msg.type === "trade_new") {
    const t = { id: msg.trade.id, asset: msg.trade.asset, volume: msg.trade.volume, state: "analyzing", profit: 0 };
    trades.set(t.id, { data: t });
    renderCard(t);
  } else if (msg.type === "trade_open") {
    const t = msg.trade; t.state = "open";
    const rec = trades.get(t.id) || {}; rec.data = t; rec.openedAt = Date.now(); trades.set(t.id, rec);
    renderCard(t);
    startTimer(t.id, msg.trade.open_seconds);
  } else if (msg.type === "trade_accepted") {
    const rec = trades.get(msg.trade_id); if (rec) { rec.data.state = "accepted"; renderCard(rec.data); }
  } else if (msg.type === "trade_completed") {
    const rec = trades.get(msg.trade_id);
    if (rec) {
      rec.data.state = "completed"; rec.data.profit = msg.profit; renderCard(rec.data);
      const card = $("card-" + msg.trade_id);
      if (card && msg.profit >= 0) { card.classList.add("flash-win"); setTimeout(() => card.classList.remove("flash-win"), 700); }
      const sign = msg.profit >= 0 ? "+" : "";
      toast(`Сделка #${msg.trade_id} завершена · ${sign}${fmt(msg.profit)} УЕ`, msg.profit >= 0 ? "success" : "error");
    }
    loadMe();
  } else if (msg.type === "trade_missed") {
    const rec = trades.get(msg.trade_id); if (rec) { rec.data.state = "missed"; renderCard(rec.data); }
  }
}

/* ---------------- blockchain explorer (simulated) ---------------- */
function randHash() {
  const hex = "0123456789abcdef";
  let s = "0x";
  for (let i = 0; i < 64; i++) s += hex[Math.floor(Math.random() * 16)];
  return s;
}
function addChainRow() {
  if (!$("chain").classList.contains("active")) return; // only animate when visible
  const feed = $("chain-feed");
  const row = document.createElement("div");
  const hash = randHash();
  const amt = (Math.random() * 49900 + 100).toFixed(2);
  const mine = Math.random() < 0.05;
  row.className = "chain-row flash" + (mine ? " mine" : "");
  row.innerHTML =
    `<span class="chain-hash">${hash.slice(0, 18)}…</span>` +
    `<span class="chain-amt">${amt} USDT</span>` +
    `<span class="chain-badge">подтверждено</span>` +
    (mine ? `<span class="chain-mine-tag">ваша</span>` : "");
  row.onclick = () => openTxModal(hash, amt);
  feed.prepend(row);
  while (feed.children.length > 50) feed.removeChild(feed.lastChild);
  setTimeout(() => row.classList.remove("flash"), 600);
}
function openTxModal(hash, amt) {
  $("tx-modal-body").innerHTML =
    `<div style="color:var(--muted)">Хэш</div>${hash}<br><br>` +
    `<div style="color:var(--muted)">Отправитель</div>${randHash().slice(0, 26)}…<br><br>` +
    `<div style="color:var(--muted)">Получатель</div>${randHash().slice(0, 26)}…<br><br>` +
    `<div style="color:var(--muted)">Сумма</div>${amt} USDT &nbsp;·&nbsp; комиссия ${(Math.random() * 5).toFixed(4)} USDT<br><br>` +
    `<span class="sim-tag-sm">Сгенерированные данные (DEMO)</span>`;
  $("tx-modal").classList.add("on");
}
$("tx-modal-close").onclick = () => $("tx-modal").classList.remove("on");
$("tx-modal").onclick = (e) => { if (e.target.id === "tx-modal") $("tx-modal").classList.remove("on"); };
setInterval(addChainRow, 1600);

/* ---------------- transactions ---------------- */
const TX_ICONS = {
  in: '<svg viewBox="0 0 24 24"><path d="M12 4l-1.4 1.4L16.2 11H4v2h12.2l-5.6 5.6L12 20l8-8z" transform="rotate(90 12 12)"/></svg>',
  out: '<svg viewBox="0 0 24 24"><path d="M12 4l-1.4 1.4L16.2 11H4v2h12.2l-5.6 5.6L12 20l8-8z" transform="rotate(-90 12 12)"/></svg>',
};
let txOffset = 0;
async function loadTx(reset = false) {
  if (reset) { txOffset = 0; $("tx-list").innerHTML = ""; }
  const list = await api(`/api/transactions?limit=20&offset=${txOffset}`);
  const box = $("tx-list");
  if (!list.length && reset) { box.innerHTML = `<div class="empty">Операций пока нет</div>`; return; }
  list.forEach((t) => {
    const pos = t.amount >= 0;
    const row = document.createElement("div");
    row.className = "tx-row";
    row.innerHTML =
      `<div class="tx-icon ${pos ? "in" : "out"}">${pos ? TX_ICONS.in : TX_ICONS.out}</div>` +
      `<div class="tx-main"><div class="tx-type">${t.type}</div><div class="tx-note">${t.note || ""}</div></div>` +
      `<div class="tx-amt ${pos ? "pos" : "neg"}">${pos ? "+" : ""}${t.amount.toFixed(2)}</div>`;
    box.appendChild(row);
  });
  txOffset += list.length;
}
$("tx-load").onclick = () => loadTx(false);

/* ---------------- boot ---------------- */
(async function boot() {
  setConn(false, "подключение…");
  try { await loadMe(true); await loadInitialTrades(); }
  catch (e) { toast("Бэкенд недоступен — запустите окно 1 (порт 8000)", "error", 6000); console.error(e); }
  connectWS();
})();
