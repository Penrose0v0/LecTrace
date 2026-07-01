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
const modeSelect = $("modeSelect");
const startBtn2 = $("startBtn");
const endBtn = $("endBtn");

// ---------------- i18n ----------------
const I18N = {
  ja: {
    docTitle: "LecTrace — 聞き逃しCatchup",
    sessionTitle: "再生する講義を選択", start: "文字起こし開始", stop: "停止",
    modeTitle: "文字起こしソース", modeReplay: "アーカイブ再生",
    modeMic: "マイク·Google", modeMicOpenai: "マイク·OpenAI",
    statusListening: "収音中…", statusRequestMic: "マイクを要求中…",
    statusMicDenied: "マイクが使えません", statusSttError: (m) => `STT エラー：${m}`,
    pause: "一時停止", resume: "再開", end: "終了", statusPaused: "一時停止中",
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
    sessionTitle: "选择要回放的归档课堂", start: "开始转录", stop: "停止",
    modeTitle: "转录来源", modeReplay: "回放 demo",
    modeMic: "麦克风·Google", modeMicOpenai: "麦克风·OpenAI",
    statusListening: "收音中…", statusRequestMic: "正在请求麦克风…",
    statusMicDenied: "无法使用麦克风", statusSttError: (m) => `STT 错误：${m}`,
    pause: "暂停", resume: "继续", end: "结束", statusPaused: "已暂停",
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
    sessionTitle: "Choose an archived lecture to replay", start: "Start", stop: "Stop",
    modeTitle: "Transcript source", modeReplay: "Replay demo",
    modeMic: "Mic · Google", modeMicOpenai: "Mic · OpenAI",
    statusListening: "Listening…", statusRequestMic: "Requesting mic…",
    statusMicDenied: "Microphone unavailable", statusSttError: (m) => `STT error: ${m}`,
    pause: "Pause", resume: "Resume", end: "End", statusPaused: "Paused",
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
  updateStartBtn();
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
let mode = "replay";
let transcribing = false;
let micStream = null, audioCtx = null, processor = null;
// resume（暂停/继续）状态
let paused = false;        // 已暂停，可继续
let pausing = false;       // 正在暂停收尾（等服务端 end）
let resumeSessionId = null; // 下次连接要续接的 session
const isMicMode = () => mode !== "replay";

async function loadSessions() {
  try {
    const r = await fetch("/api/sessions");
    const { sessions } = await r.json();
    sessionsCache = sessions;
    renderSessions();
  } catch (e) { setStatus("loadSessionsFailed"); }
}

function updateStartBtn() {
  let label;
  if (paused) label = t("resume");
  else if (transcribing) label = isMicMode() ? t("pause") : t("stop");
  else label = t("start");
  startBtn2.textContent = label;
  startBtn2.classList.toggle("btn-primary", transcribing || paused);
  // 结束按钮：麦克风模式且转录中或已暂停时显示
  endBtn.classList.toggle("hidden", !(isMicMode() && (transcribing || paused)));
  const locked = transcribing || paused;
  modeSelect.disabled = locked;
  sessionSelect.disabled = locked;
}

function applyMode() {
  mode = modeSelect.value;
  sessionSelect.style.display = mode === "replay" ? "" : "none";
}

function appendSegment(seq, text, tSec) {
  removeInterim();
  // 只有当用户已在底部附近时才自动下拉，往上翻看历史时不打断。
  const atBottom =
    transcriptEl.scrollHeight - transcriptEl.scrollTop - transcriptEl.clientHeight < 80;
  const div = document.createElement("div");
  div.className = "seg";
  div.dataset.t = tSec;
  div.innerHTML = `<span class="ts">${fmtTime(tSec)}</span>${escapeHtml(text)}`;
  transcriptEl.appendChild(div);
  if (atBottom) transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

// STT 临时结果：一个滚动更新的“待定”行
function showInterim(text) {
  const atBottom =
    transcriptEl.scrollHeight - transcriptEl.scrollTop - transcriptEl.clientHeight < 80;
  let p = document.getElementById("pendingSeg");
  if (!p) {
    p = document.createElement("div");
    p.className = "seg pending";
    p.id = "pendingSeg";
    transcriptEl.appendChild(p);
  }
  p.innerHTML = `<span class="dot">●</span>${escapeHtml(text)}`;
  if (atBottom) transcriptEl.scrollTop = transcriptEl.scrollHeight;
}
function removeInterim() {
  const p = document.getElementById("pendingSeg");
  if (p) p.remove();
}

// 转录消息统一处理（回放 + 麦克风共用）
function onTranscriptMessage(ev) {
  if (typeof ev.data !== "string") return;
  const msg = JSON.parse(ev.data);
  if (msg.type === "session") {
    sessionId = msg.session_id;
    catchupBtn.disabled = false;
    if (msg.source === "replay") setStatus("statusLive", { param: msg.speed, live: true });
    else setStatus("statusListening", { live: true }); // 麦克风：openai-stt / google-stt
  } else if (msg.type === "interim") {
    showInterim(msg.text);
  } else if (msg.type === "segment") {
    appendSegment(msg.seq, msg.text, msg.t);
  } else if (msg.type === "end") {
    if (pausing) enterPaused();
    else finishTranscription("statusEnded");
  } else if (msg.type === "error") {
    setStatus("statusSttError", { param: msg.message });
    finishTranscription(null);
  }
}

function startTranscription() {
  paused = false; pausing = false; resumeSessionId = null; // 全新 session
  transcribing = true;
  updateStartBtn();
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  transcriptEl.innerHTML = "";
  removeInterim();
  sessionId = null;
  catchupBtn.disabled = true;
  cards = []; activeCardId = null; renderCards(); clearHighlight();
  if (mode === "replay") startReplay();
  else startMic();
}

function finishTranscription(statusKey) {
  transcribing = false;
  updateStartBtn();
  removeInterim();
  stopAudio();
  if (statusKey && statusState.key !== "statusMicDenied") setStatus(statusKey);
}

function stopTranscription() {
  if (isMicMode()) {
    // 发 stop 并停止采集，但保持连接，等服务端把尾部 final + end 发完再收尾
    if (ws) { try { if (ws.readyState === 1) ws.send("stop"); } catch (e) {} }
    stopAudio();
  } else {
    // 回放：直接关连接即可停止
    if (ws) { try { ws.close(); } catch (e) {} }
    finishTranscription("statusEnded");
  }
}

// 主按钮：按状态分派 开始 / 暂停 / 继续 / 停止
function onPrimaryClick() {
  if (paused) resumeTranscription();
  else if (transcribing) (isMicMode() ? pauseTranscription() : stopTranscription());
  else startTranscription();
}

// 暂停（仅麦克风）：优雅收尾并记住 session，转录留在屏上，可继续
function pauseTranscription() {
  pausing = true;
  if (ws) { try { if (ws.readyState === 1) ws.send("stop"); } catch (e) {} }
  stopAudio();
}
function enterPaused() {
  pausing = false;
  transcribing = false;
  paused = true;
  resumeSessionId = sessionId; // 下次续接
  stopAudio();
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  removeInterim();
  setStatus("statusPaused");
  updateStartBtn();
}
// 继续：重连续接同一 session，转录接着追加
function resumeTranscription() {
  paused = false;
  transcribing = true;
  updateStartBtn();
  removeInterim();
  startMic(); // startMic 会带上 resumeSessionId
}
// 结束：彻底收尾，回到空闲（转录保留在屏上，仍可 Catchup/对话）
function endTranscription() {
  if (ws) { try { if (ws.readyState === 1) ws.send("stop"); ws.close(); } catch (e) {} ws = null; }
  stopAudio();
  transcribing = false;
  paused = false;
  pausing = false;
  resumeSessionId = null;
  removeInterim();
  setStatus("statusEnded");
  updateStartBtn();
}

function stopAudio() {
  if (processor) { try { processor.disconnect(); processor.onaudioprocess = null; } catch (e) {} processor = null; }
  if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
  if (micStream) { micStream.getTracks().forEach((tr) => tr.stop()); micStream = null; }
}

// ---- 回放 ----
function startReplay() {
  const file = sessionSelect.value;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/transcribe?source=replay&file=${encodeURIComponent(file)}`);
  ws.onmessage = onTranscriptMessage;
  ws.onclose = () => { if (transcribing && statusState.key === "statusLive") finishTranscription("statusDisconnected"); };
  ws.onerror = () => setStatus("statusConnError");
  setStatus("statusConnecting");
}

// ---- 麦克风实时（Google STT）----
function floatTo16BitPCM(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}
function downsample(buf, inRate, outRate) {
  if (outRate >= inRate) return buf;
  const ratio = inRate / outRate;
  const outLen = Math.round(buf.length / ratio);
  const res = new Float32Array(outLen);
  let oi = 0, bi = 0;
  while (oi < outLen) {
    const next = Math.round((oi + 1) * ratio);
    let acc = 0, cnt = 0;
    for (let i = bi; i < next && i < buf.length; i++) { acc += buf[i]; cnt++; }
    res[oi++] = cnt ? acc / cnt : 0;
    bi = next;
  }
  return res;
}

async function startMic() {
  // OpenAI Realtime 要 24kHz，Google STT 用 16kHz
  const targetRate = mode === "openai-stt" ? 24000 : 16000;
  setStatus("statusRequestMic");
  try {
    // 关掉人声通话处理：这些算法为双向通话调，用在课程/系统音频(如 BlackHole)上
    // 会削波/门限/失真，损害 ASR。转录要的是忠实的原始音频。
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
  } catch (e) {
    setStatus("statusMicDenied");
    finishTranscription(null);
    return;
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // 续接（resume）时带上 session，让后端接着同一 session 追加
  const sessParam = resumeSessionId ? `&session=${encodeURIComponent(resumeSessionId)}` : "";
  resumeSessionId = null;
  ws = new WebSocket(`${proto}://${location.host}/ws/transcribe?source=${mode}&lang=${lectureLang.value}${sessParam}`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = onTranscriptMessage;
  ws.onclose = () => { if (pausing) enterPaused(); else if (transcribing) finishTranscription("statusEnded"); };
  ws.onerror = () => setStatus("statusConnError");
  ws.onopen = () => {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = audioCtx.createMediaStreamSource(micStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    const sink = audioCtx.createGain();
    sink.gain.value = 0; // 静音接到 destination，保证 onaudioprocess 触发又不回放
    src.connect(processor);
    processor.connect(sink);
    sink.connect(audioCtx.destination);
    processor.onaudioprocess = (e) => {
      if (!ws || ws.readyState !== 1) return;
      const input = e.inputBuffer.getChannelData(0);
      const pcm = floatTo16BitPCM(downsample(input, audioCtx.sampleRate, targetRate));
      ws.send(pcm.buffer);
    };
  };
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
startBtn2.addEventListener("click", onPrimaryClick);
endBtn.addEventListener("click", endTranscription);
modeSelect.addEventListener("change", applyMode);
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
// 默认转录源完全跟随后端配置（双向）
fetch("/api/health").then((r) => r.json()).then((h) => {
  if (["openai-stt", "google-stt", "replay"].includes(h.transcription_source)) {
    modeSelect.value = h.transcription_source;
  }
  applyMode();
}).catch(() => applyMode());
