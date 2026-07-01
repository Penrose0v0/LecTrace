// LecTrace demo 前端：转录区 / Catchup 卡片区 / AI 对话区。
// UI 语言跟随“用户语言”下拉切换（i18n）。

const $ = (id) => document.getElementById(id);
const sessionSelect = $("sessionSelect");
const startBtn = $("startBtn");
const statusEl = $("status");
const transcriptEl = $("transcript");
const lectureLang = $("lectureLang");
const userLang = $("userLang");
const windowSlider = $("windowSlider");
const windowVal = $("windowVal");
const catchupBtn = $("catchupBtn");
const cardChips = $("cardChips");
const cardBody = $("cardBody");
const cardsPrev = $("cardsPrev");
const cardsNext = $("cardsNext");
const chatMessages = $("chatMessages");
const chatInput = $("chatInput");
const sendBtn = $("sendBtn");
const newChatBtn = $("newChatBtn");
const historyBtn = $("historyBtn");
const historyPanel = $("historyPanel");

// ---------------- i18n ----------------
const I18N = {
  ja: {
    docTitle: "LecTrace — 聞き逃しCatchup",
    sessionTitle: "再生する講義を選択", start: "文字起こし開始",
    transcriptHead: "リアルタイム文字起こし",
    catchupSettingsTitle: "振り返り時間の設定",
    lectureLangLabel: "講義の言語", userLangLabel: "あなたの言語",
    windowPre: "直近", windowSuf: "分を振り返る",
    catchupBtn: "ついていけない？要約する",
    statusIdle: "未接続", statusConnecting: "接続中…",
    statusLive: (s) => `ライブ · ${s}× 再生`, statusEnded: "再生終了",
    statusDisconnected: "切断されました", statusConnError: "接続エラー",
    loadSessionsFailed: "セッションの読み込みに失敗",
    noSessions: "（アーカイブなし）", sessionOption: (m, n) => `${m}分 / ${n}件`,
    cardsEmpty: "上のボタンを押すと、このラウンドの要約がここに表示されます。",
    summaryLoading: (x) => `直近 ${x} 分を要約中…`,
    catchupFailedPrefix: "Catchup 失敗：", segUnit: "件",
    aiTitle: "AI チャット", newChat: "新しいチャット", history: "履歴", send: "送信",
    chatPlaceholder: "この講義について質問…",
    chatEmpty: "講義の文字起こしを踏まえて AI が答えます。質問してみましょう。",
    historyEmpty: "履歴はまだありません", chatMsgUnit: (n) => `${n} メッセージ`,
    chatFailedPrefix: "エラー：",
  },
  zh: {
    docTitle: "LecTrace — 听讲 Catchup",
    sessionTitle: "选择要回放的归档课堂", start: "开始转录",
    transcriptHead: "实时转录",
    catchupSettingsTitle: "设置回顾时间",
    lectureLangLabel: "讲义语言", userLangLabel: "用户语言",
    windowPre: "回顾最近", windowSuf: "分钟",
    catchupBtn: "没跟上？点我总结",
    statusIdle: "未连接", statusConnecting: "连接中…",
    statusLive: (s) => `直播中 · ${s}× 回放`, statusEnded: "回放结束",
    statusDisconnected: "已断开", statusConnError: "连接错误",
    loadSessionsFailed: "加载 session 失败",
    noSessions: "（无归档 session）", sessionOption: (m, n) => `${m}分 / ${n}段`,
    cardsEmpty: "点击上方按钮后，本轮摘要会显示在这里。",
    summaryLoading: (x) => `正在总结最近 ${x} 分钟…`,
    catchupFailedPrefix: "Catchup 失败：", segUnit: "段",
    aiTitle: "AI 对话", newChat: "新对话", history: "历史对话", send: "发送",
    chatPlaceholder: "问问这节课的内容…",
    chatEmpty: "向 AI 提问，它会结合课堂转录来回答。",
    historyEmpty: "暂无历史对话", chatMsgUnit: (n) => `${n} 条消息`,
    chatFailedPrefix: "出错：",
  },
  en: {
    docTitle: "LecTrace — Lecture Catchup",
    sessionTitle: "Choose an archived lecture to replay", start: "Start",
    transcriptHead: "Live transcript",
    catchupSettingsTitle: "Recap window",
    lectureLangLabel: "Lecture language", userLangLabel: "Your language",
    windowPre: "Recap the last", windowSuf: "min",
    catchupBtn: "Lost track? Summarize",
    statusIdle: "Not connected", statusConnecting: "Connecting…",
    statusLive: (s) => `Live · ${s}× replay`, statusEnded: "Replay ended",
    statusDisconnected: "Disconnected", statusConnError: "Connection error",
    loadSessionsFailed: "Failed to load sessions",
    noSessions: "(no archived sessions)", sessionOption: (m, n) => `${m}min / ${n} segs`,
    cardsEmpty: "Click the button above and this round's summary shows up here.",
    summaryLoading: (x) => `Summarizing the last ${x} min…`,
    catchupFailedPrefix: "Catchup failed: ", segUnit: "segs",
    aiTitle: "AI Chat", newChat: "New chat", history: "History", send: "Send",
    chatPlaceholder: "Ask about this lecture…",
    chatEmpty: "Ask the AI — it answers using the lecture transcript.",
    historyEmpty: "No conversations yet", chatMsgUnit: (n) => `${n} messages`,
    chatFailedPrefix: "Error: ",
  },
};

let uiLang = userLang.value || "ja";
const t = (key) => I18N[uiLang][key];

let statusState = { key: "statusIdle", param: null, live: false };
let sessionsCache = [];

function applyI18n(lang) {
  uiLang = lang;
  document.documentElement.lang = lang;
  document.title = t("docTitle");
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  renderStatus();
  renderSessions();
  renderCards();
  if (!chatMessages.children.length || chatMessages.dataset.empty === "1") renderChatEmpty();
}

// ---------------- 通用 ----------------
function fmtTime(sec) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function setStatus(key, { param = null, live = false } = {}) {
  statusState = { key, param, live };
  renderStatus();
}
function renderStatus() {
  const { key, param, live } = statusState;
  const v = t(key);
  statusEl.textContent = typeof v === "function" ? v(param) : v;
  statusEl.classList.toggle("live", live);
}
function renderSessions() {
  const sel = sessionSelect.value;
  sessionSelect.innerHTML = "";
  if (!sessionsCache.length) {
    const opt = document.createElement("option");
    opt.textContent = t("noSessions");
    sessionSelect.appendChild(opt);
    return;
  }
  for (const s of sessionsCache) {
    const opt = document.createElement("option");
    const mins = s.duration_sec ? Math.round(s.duration_sec / 60) : "?";
    opt.value = s.file;
    opt.textContent = `${s.file}  ·  ${t("sessionOption")(mins, s.line_count)}`;
    sessionSelect.appendChild(opt);
  }
  sessionSelect.value = sel || sessionsCache[sessionsCache.length - 1].file;
}

// 通用 SSE 消费器
async function parseSSE(body, handlers) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      let event = "message";
      const dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const payload = JSON.parse(dataLines.join(""));
      if (event === "meta") handlers.meta?.(payload);
      else if (event === "error") { handlers.error?.(payload); return; }
      else if (event === "done") { handlers.done?.(); return; }
      else if (payload.text) handlers.text?.(payload.text);
    }
  }
}

// ---------------- 转录 ----------------
let ws = null;
let sessionId = null;

async function loadSessions() {
  try {
    const r = await fetch("/api/sessions");
    const { sessions } = await r.json();
    sessionsCache = sessions;
    renderSessions();
  } catch (e) { setStatus("loadSessionsFailed"); }
}

function appendSegment(seq, text, tSec) {
  // 追加前先判断用户是否已在底部附近；只有在底部时才自动下拉，
  // 用户往上翻看历史时不打断。
  const atBottom =
    transcriptEl.scrollHeight - transcriptEl.scrollTop - transcriptEl.clientHeight < 80;
  const div = document.createElement("div");
  div.className = "seg";
  div.dataset.t = tSec;
  div.innerHTML = `<span class="ts">${fmtTime(tSec)}</span>${escapeHtml(text)}`;
  transcriptEl.appendChild(div);
  if (atBottom) transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function startTranscription() {
  if (ws) ws.close();
  transcriptEl.innerHTML = "";
  sessionId = null;
  catchupBtn.disabled = true;

  const file = sessionSelect.value;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/transcribe?file=${encodeURIComponent(file)}`);
  setStatus("statusConnecting");

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "session") {
      sessionId = msg.session_id;
      catchupBtn.disabled = false;
      setStatus("statusLive", { param: msg.speed, live: true });
    } else if (msg.type === "segment") {
      appendSegment(msg.seq, msg.text, msg.t);
    } else if (msg.type === "end") {
      setStatus("statusEnded");
    } else if (msg.type === "error") {
      setStatus("statusConnError");
    }
  };
  ws.onclose = () => { if (statusState.key === "statusLive") setStatus("statusDisconnected"); };
  ws.onerror = () => setStatus("statusConnError");
}

// ---------------- 转录高亮 ----------------
function clearHighlight() {
  transcriptEl.querySelectorAll(".seg.hl").forEach((e) => e.classList.remove("hl"));
}
function highlightRange(from, to, scroll) {
  clearHighlight();
  let first = null;
  transcriptEl.querySelectorAll(".seg").forEach((e) => {
    const tt = parseFloat(e.dataset.t);
    if (tt >= from && tt <= to) { e.classList.add("hl"); if (!first) first = e; }
  });
  if (scroll && first) first.scrollIntoView({ block: "center", behavior: "smooth" });
}

// ---------------- Catchup 卡片 ----------------
let cards = [];       // {id, index, from, to, model, segCount, text, status}
let activeCardId = null;
let cardSeq = 0;

function renderCards() {
  // chips
  cardChips.innerHTML = "";
  for (const c of cards) {
    const chip = document.createElement("div");
    chip.className = "chip" + (c.id === activeCardId ? " active" : "");
    chip.textContent = `#${c.index} · ${fmtTime(c.from)}`;
    chip.title = `${fmtTime(c.from)}–${fmtTime(c.to)}`;
    chip.onclick = () => selectCard(c.id, true);
    cardChips.appendChild(chip);
  }
  const idx = cards.findIndex((c) => c.id === activeCardId);
  cardsPrev.disabled = idx <= 0;
  cardsNext.disabled = idx < 0 || idx >= cards.length - 1;

  // body
  const active = cards.find((c) => c.id === activeCardId);
  if (!active) {
    cardBody.innerHTML = `<div class="empty">${t("cardsEmpty")}</div>`;
    return;
  }
  const meta = `#${active.index} · ${fmtTime(active.from)}–${fmtTime(active.to)} · ${active.segCount}${t("segUnit")} · ${active.model}`;
  const bodyHtml = active.status === "error"
    ? `<div class="err">${escapeHtml(t("catchupFailedPrefix") + active.text)}</div>`
    : escapeHtml(active.text || "…");
  cardBody.innerHTML = `<div class="meta">${meta}</div>${bodyHtml}`;
}

function selectCard(id, scroll) {
  activeCardId = id;
  const c = cards.find((x) => x.id === id);
  renderCards();
  if (c) highlightRange(c.from, c.to, scroll);
}

async function doCatchup() {
  if (!sessionId) return;
  const windowMinutes = Number(windowSlider.value);
  catchupBtn.disabled = true;

  const card = {
    id: "c" + ++cardSeq, index: cardSeq,
    from: 0, to: 0, model: "", segCount: 0, text: "", status: "loading",
  };
  cards.push(card);
  activeCardId = card.id;
  renderCards();

  try {
    const r = await fetch("/api/catchup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId, window_minutes: windowMinutes,
        lecture_language: lectureLang.value, user_language: userLang.value,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    await parseSSE(r.body, {
      meta: (m) => {
        card.from = m.covered_from; card.to = m.covered_to;
        card.model = m.model; card.segCount = m.segment_count;
        card.status = "streaming";
        if (activeCardId === card.id) highlightRange(card.from, card.to, false);
        renderCards();
      },
      text: (txt) => {
        card.text += txt;
        if (activeCardId === card.id) renderCards();
      },
      error: (p) => { card.status = "error"; card.text = p.message; renderCards(); },
      done: () => { card.status = "done"; renderCards(); },
    });
  } catch (e) {
    card.status = "error"; card.text = e.message; renderCards();
  } finally {
    catchupBtn.disabled = false;
  }
}

function stepCard(delta) {
  const idx = cards.findIndex((c) => c.id === activeCardId);
  const next = idx + delta;
  if (next >= 0 && next < cards.length) selectCard(cards[next].id, true);
}

// ---------------- AI 对话 ----------------
let conversationId = null;

function renderChatEmpty() {
  chatMessages.dataset.empty = "1";
  chatMessages.innerHTML = `<div class="empty">${t("chatEmpty")}</div>`;
}
function addBubble(role, text) {
  if (chatMessages.dataset.empty === "1") { chatMessages.innerHTML = ""; chatMessages.dataset.empty = "0"; }
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  addBubble("user", message);
  const bubble = addBubble("assistant", "…");
  sendBtn.disabled = true;

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId || "", message,
        conversation_id: conversationId, user_language: userLang.value,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    let acc = "";
    await parseSSE(r.body, {
      meta: (m) => { conversationId = m.conversation_id; },
      text: (txt) => { acc += txt; bubble.textContent = acc; chatMessages.scrollTop = chatMessages.scrollHeight; },
      error: (p) => { bubble.classList.add("err"); bubble.textContent = t("chatFailedPrefix") + p.message; },
      done: () => {},
    });
  } catch (e) {
    bubble.classList.add("err");
    bubble.textContent = t("chatFailedPrefix") + e.message;
  } finally {
    sendBtn.disabled = false;
  }
}

function newChat() {
  conversationId = null;
  historyPanel.classList.add("hidden");
  renderChatEmpty();
  chatInput.focus();
}

async function toggleHistory() {
  if (!historyPanel.classList.contains("hidden")) { historyPanel.classList.add("hidden"); return; }
  historyPanel.innerHTML = `<div class="history-empty">…</div>`;
  historyPanel.classList.remove("hidden");
  try {
    const r = await fetch(`/api/conversations?session_id=${encodeURIComponent(sessionId || "")}`);
    const { conversations } = await r.json();
    if (!conversations.length) { historyPanel.innerHTML = `<div class="history-empty">${t("historyEmpty")}</div>`; return; }
    historyPanel.innerHTML = "";
    for (const c of conversations) {
      const item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML = `<div class="h-title">${escapeHtml(c.title)}</div><div class="h-sub">${t("chatMsgUnit")(c.message_count)}</div>`;
      item.onclick = () => loadConversation(c.id);
      historyPanel.appendChild(item);
    }
  } catch (e) {
    historyPanel.innerHTML = `<div class="history-empty">${t("chatFailedPrefix") + e.message}</div>`;
  }
}

async function loadConversation(id) {
  historyPanel.classList.add("hidden");
  try {
    const r = await fetch(`/api/conversations/${id}`);
    const conv = await r.json();
    conversationId = conv.id;
    chatMessages.innerHTML = ""; chatMessages.dataset.empty = "0";
    for (const m of conv.messages) addBubble(m.role === "user" ? "user" : "assistant", m.content);
  } catch (e) { /* ignore */ }
}

// ---------------- 事件绑定 ----------------
windowSlider.addEventListener("input", () => { windowVal.textContent = windowSlider.value; });
startBtn.addEventListener("click", startTranscription);
catchupBtn.addEventListener("click", doCatchup);
cardsPrev.addEventListener("click", () => stepCard(-1));
cardsNext.addEventListener("click", () => stepCard(1));
userLang.addEventListener("change", () => applyI18n(userLang.value));
sendBtn.addEventListener("click", sendChat);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});
newChatBtn.addEventListener("click", newChat);
historyBtn.addEventListener("click", toggleHistory);

// 初始渲染
setStatus("statusIdle");
renderChatEmpty();
applyI18n(uiLang);
loadSessions();
