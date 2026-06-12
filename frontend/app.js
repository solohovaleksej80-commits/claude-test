/* TradeSim Mini App (DEMO). All data is simulated. */
const API = (window.TRADESIM_API || "http://localhost:8000");
const WS_URL = API.replace(/^http/, "ws") + "/ws";

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

// Auth headers: real Telegram initData if present, else dev header.
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
const trades = new Map(); // id -> {data, timer state}

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "tx") loadTx(true);
  };
});

// ---------- balance typewriter ----------
function typeBalance(el, value) {
  const str = Number(value).toFixed(2);
  el.textContent = "";
  let i = 0;
  const iv = setInterval(() => {
    el.textContent += str[i++];
    if (i >= str.length) clearInterval(iv);
  }, 60);
}

// ---------- dashboard ----------
async function loadMe(animate = false) {
  me = await api("/api/me");
  if (animate) typeBalance(document.getElementById("balance"), me.balance);
  else document.getElementById("balance").textContent = Number(me.balance).toFixed(2);
  document.getElementById("tier-line").textContent = `ЭТАП ${me.tier} — ${me.tier_name.toUpperCase()}`;
  renderTiers();
  document.getElementById("meta").innerHTML =
    `Уровень: <b>${me.level.toUpperCase()}</b><br>` +
    `Всего сделок: <b>${me.total_trades}</b><br>` +
    `Осталось сегодня: <b>${me.remaining_trades_today}</b> / лимит ${me.daily_limit}<br>` +
    `Цена след. буста: <b>${me.next_boost_price} УЕ</b><br>` +
    (me.next_level ? `До уровня ${me.next_level.toUpperCase()}: <b>${me.next_level_at - me.total_trades}</b> сделок<br>` : "") +
    `Реф. бонус: <b>${me.referral_earnings} УЕ</b>`;
  updateBookHint();
}

async function renderTiers() {
  const tiers = await api("/api/tiers");
  const box = document.getElementById("tiers");
  box.innerHTML = "";
  tiers.forEach((t) => {
    const d = document.createElement("div");
    d.className = "tier-bar" + (t.tier === me.tier ? " active" : "");
    d.innerHTML = `<div class="t-name">ЭТАП ${t.tier}</div><div class="t-price">${t.price} УЕ</div><div class="t-name">${t.daily_limit}/сут</div>`;
    d.onclick = async () => {
      if (!confirm(`Купить Этап ${t.tier} за ${t.price} УЕ (виртуальные)?`)) return;
      try { me = await api(`/api/subscribe/${t.tier}`, { method: "POST" }); await loadMe(); }
      catch (e) { alert(e.message); }
    };
    box.appendChild(d);
  });
}

function updateBookHint() {
  const hint = document.getElementById("book-hint");
  if (me && me.tier < 2) {
    hint.className = "hint locked";
    hint.textContent = "СТАКАН ДОСТУПЕН НА ЭТАПЕ 2. Сейчас вы на Этапе 1 (только наблюдение).";
  } else {
    hint.className = "hint";
    hint.textContent = `Осталось сделок сегодня: ${me ? me.remaining_trades_today : "—"}`;
  }
}

// ---------- order book ----------
function renderCard(t) {
  let el = document.getElementById("card-" + t.id);
  if (!el) {
    el = document.createElement("div");
    el.id = "card-" + t.id;
    document.getElementById("cards").prepend(el);
  }
  el.className = "card " + t.state;
  let inner = `<div class="asset">${t.asset}</div><div class="vol">${Math.round(t.volume).toLocaleString()} USDT</div>`;

  if (t.state === "analyzing") {
    inner += `<div class="state">АНАЛИЗ...</div><div class="dash-run"></div>`;
  } else if (t.state === "open") {
    const pc = t.profit >= 0 ? "profit-pos" : "profit-neg";
    inner += `<div class="state ${pc}">${t.profit >= 0 ? "+" : ""}${Math.round(t.profit).toLocaleString()} УЕ</div>`;
    inner += `<div class="timer" id="timer-${t.id}"><div class="fill" style="height:100%"></div></div><div class="timer-label" id="tl-${t.id}"></div>`;
    if (me && me.tier === 2) inner += `<button class="btn" onclick="acceptTrade(${t.id})">ПРИНЯТЬ</button>`;
    else if (me && me.tier === 3) inner += `<div class="state">АВТО-ПРИЁМ</div>`;
  } else if (t.state === "accepted") {
    inner += `<div class="state">ИСПОЛНЯЕТСЯ...</div>`;
  } else if (t.state === "completed") {
    const pc = t.profit >= 0 ? "profit-pos" : "profit-neg";
    inner += `<div class="state struck">ЗАВЕРШЕНО</div><div class="${pc}">${t.profit >= 0 ? "+" : ""}${Math.round(t.profit).toLocaleString()} УЕ</div>`;
  } else if (t.state === "missed") {
    inner += `<div class="state struck">ПРОПУЩЕНА</div>`;
  }
  el.innerHTML = inner;
}

function startTimer(id, totalSecs, openOpenedAt) {
  const t = trades.get(id);
  if (!t) return;
  const deadline = Date.now() + totalSecs * 1000;
  t.deadline = deadline;
  if (t.interval) clearInterval(t.interval);
  t.interval = setInterval(() => {
    const remain = Math.max(0, deadline - Date.now());
    const fillEl = document.querySelector(`#timer-${id} .fill`);
    const labelEl = document.getElementById("tl-" + id);
    const timerEl = document.getElementById("timer-" + id);
    if (!fillEl) { clearInterval(t.interval); return; }
    const pct = (remain / (totalSecs * 1000)) * 100;
    fillEl.style.height = pct + "%";
    const s = Math.ceil(remain / 1000);
    if (labelEl) labelEl.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    if (timerEl) timerEl.classList.toggle("warn", remain <= 30000);
    if (remain <= 0) clearInterval(t.interval);
  }, 250);
}

window.acceptTrade = async function (id) {
  const t = trades.get(id);
  const latency = t && t.openedAt ? Date.now() - t.openedAt : null;
  try {
    const r = await api(`/api/trades/${id}/accept` + (latency ? `?latency_ms=${latency}` : ""), { method: "POST" });
    if (!r.ok) {
      if (r.detail.includes("буст") && confirm(r.detail + "\nКупить буст?")) {
        try { me = await api("/api/boosts/buy", { method: "POST" }); await loadMe(); alert("Буст куплен. Нажмите ПРИНЯТЬ снова."); }
        catch (e) { alert(e.message); }
      } else alert(r.detail);
      return;
    }
    await loadMe();
  } catch (e) { alert(e.message); }
};

async function loadInitialTrades() {
  const list = await api("/api/trades?limit=30");
  document.getElementById("cards").innerHTML = "";
  list.reverse().forEach((t) => { trades.set(t.id, { data: t }); renderCard(t); });
}

// ---------- websocket ----------
let ws, reconnectDelay = 1000;
function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { document.getElementById("conn").textContent = "ONLINE"; document.getElementById("conn").classList.add("on"); reconnectDelay = 1000; };
  ws.onclose = () => {
    document.getElementById("conn").textContent = "RECONNECT...";
    document.getElementById("conn").classList.remove("on");
    setTimeout(connectWS, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 16000);
  };
  ws.onmessage = (ev) => handleWS(JSON.parse(ev.data));
}

function handleWS(msg) {
  if (msg.counters) {
    document.getElementById("c-analyzed").textContent = msg.counters.analyzed;
    document.getElementById("c-profitable").textContent = msg.counters.profitable;
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
    const rec = trades.get(msg.trade_id); if (rec) { rec.data.state = "completed"; rec.data.profit = msg.profit; renderCard(rec.data); }
    loadMe();
  } else if (msg.type === "trade_missed") {
    const rec = trades.get(msg.trade_id); if (rec) { rec.data.state = "missed"; renderCard(rec.data); }
  }
}

// ---------- blockchain explorer (simulated) ----------
function randHash() {
  const hex = "0123456789abcdef";
  let s = "0x";
  for (let i = 0; i < 64; i++) s += hex[Math.floor(Math.random() * 16)];
  return s;
}
function addChainRow() {
  const feed = document.getElementById("chain-feed");
  const row = document.createElement("div");
  const hash = randHash();
  const amt = (Math.random() * 49900 + 100).toFixed(2);
  const mine = Math.random() < 0.05;
  row.className = "chain-row flash" + (mine ? " mine" : "");
  row.innerHTML = `<span class="hash">${hash.slice(0, 14)}...</span><span class="amt">${amt} USDT</span><span class="st">ПОДТВЕРЖДЕНО</span>${mine ? '<span class="st">ВАША</span>' : ""}`;
  row.onclick = () => openTxModal(hash, amt);
  feed.prepend(row);
  while (feed.children.length > 60) feed.removeChild(feed.lastChild);
  setTimeout(() => row.classList.remove("flash"), 60);
}
function openTxModal(hash, amt) {
  document.getElementById("tx-modal-body").innerHTML =
    `ХЭШ: ${hash}<br>ОТПРАВИТЕЛЬ: ${randHash().slice(0, 20)}...<br>ПОЛУЧАТЕЛЬ: ${randHash().slice(0, 20)}...<br>СУММА: ${amt} USDT<br>КОМИССИЯ: ${(Math.random() * 5).toFixed(4)} USDT<br><br><b>Это сгенерированные данные (DEMO).</b>`;
  document.getElementById("tx-modal").classList.add("on");
}
document.getElementById("tx-modal-close").onclick = () => document.getElementById("tx-modal").classList.remove("on");
setInterval(addChainRow, 1500);

// ---------- transactions ----------
let txOffset = 0;
async function loadTx(reset = false) {
  if (reset) { txOffset = 0; document.getElementById("tx-list").innerHTML = ""; }
  const list = await api(`/api/transactions?limit=20&offset=${txOffset}`);
  const box = document.getElementById("tx-list");
  list.forEach((t) => {
    const row = document.createElement("div");
    row.className = "tx-row";
    const cls = t.amount >= 0 ? "amt-pos" : "amt-neg";
    row.innerHTML = `<div><div>${t.type}</div><div class="note">${t.note || ""}</div></div><div class="${cls}">${t.amount >= 0 ? "+" : ""}${t.amount.toFixed(2)}</div>`;
    box.appendChild(row);
  });
  txOffset += list.length;
}
document.getElementById("tx-load").onclick = () => loadTx(false);

// ---------- boot ----------
(async function boot() {
  try { await loadMe(true); await loadInitialTrades(); } catch (e) { console.error(e); }
  connectWS();
})();
