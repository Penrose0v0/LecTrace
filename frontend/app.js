// LecTrace 前端：登录 → 讲义（转录舞台 + 对话）/ 历史抽屉 / 设置。
// 界面语言跟随用户偏好（设置页），每节课可单独设定讲义语言 / 输出语言。

const $ = (id) => document.getElementById(id);

// ---------------- i18n ----------------
const I18N = {
  ja: {
    docTitle: "LecTrace", loginSub: "聞き逃しを、すぐ取り戻す。",
    devLogin: "ローカル開発として続行", loginHint: "Google アカウントでサインインすると、過去の講義を見返したり再開できます。",
    loginHintDev: "GOOGLE_CLIENT_ID が未設定のため、ローカル開発用ログインを使っています。",
    loginFailed: "ログインに失敗しました：",
    navNew: "新しい講義", navHistory: "履歴", navProfile: "プロフィール", navSettings: "設定", logout: "サインアウト",
    untitled: "無題の講義", lectureInfo: "講義情報",
    metaNote: "すべて任意。タイトルや説明は、AI が講義の文脈を理解する手がかりになります。",
    fLectureLang: "講義の言語", fUserLang: "あなたの言語",
    fWindow: "Catch-up の範囲", fSource: "音声ソース", fFile: "アーカイブ", minUnit: "分",
    srcOpenai: "マイク · OpenAI", srcGoogle: "マイク · Google", srcReplay: "アーカイブ再生",
    titlePh: "無題の講義", descPh: "説明やメモ（任意）",
    hintNew: "● を押すとすぐ始まります。このパネルは自動で閉じます。",
    hintLive: "変更は自動で保存されます。音声ソースは開始後に変更できません。",
    emptyNew: "● を押して始めましょう。",
    emptyOpened: "まだ文字起こしがありません。",
    recStart: "開始", recPause: "一時停止", recResume: "再開",
    stIdle: "", stConnecting: "接続中…", stReconnecting: "再接続中…", stRequestMic: "マイクを要求中…",
    stMicDenied: "マイクが使えません", stStopped: "一時停止",
    stError: (m) => `エラー：${m}`, stLive: "", stReplay: (s) => `${s}× 再生`,
    tellMe: "Tell me", newThread: "新しいスレッド", threadsEmpty: "このスレッド以外はまだありません",
    threadDefault: "この講義について質問", msgUnit: (n) => `${n} 件`,
    catchup: "Catch-up", explain: "Explain", chatPlaceholder: "この講義について質問…",
    chatEmpty: "ついていけなくなったら Catch-up。\n用語が分からなければ Explain。\nあとは何でも聞いてください。",
    chatEmptyNoSession: "文字起こしを始めると、ここで質問や Catch-up ができます。",
    catchupLoading: (x) => `直近 ${x} 分を要約中…`, failed: "失敗：",
    historyTitle: "履歴", historyEmpty: "まだ講義がありません。",
    segUnit: (n) => `${n} 件`,
    settingsTitle: "設定", sUiLang: "表示・要約の言語", sLectureLang: "既定の講義の言語",
    sWindow: "既定の Catch-up の範囲", sTheme: "テーマ", themeDark: "ダーク", themeLight: "ライト（準備中）",
    save: "保存", saved: "保存しました", saveFailed: "保存に失敗しました",
    confirmInterrupt: "文字起こし中です。続けると現在の文字起こしは中断されます（あとで履歴から再開できます）。よろしいですか？",
    replayLabel: (f, m, n) => `${f} · ${m}分 / ${n}件`,
  },
  zh: {
    docTitle: "LecTrace", loginSub: "走神了？几秒钟追上进度。",
    devLogin: "以本地开发身份继续", loginHint: "用 Google 账号登录后，可以回看过去的课堂或继续转录。",
    loginHintDev: "未配置 GOOGLE_CLIENT_ID，当前使用本地开发登录。",
    loginFailed: "登录失败：",
    navNew: "新课堂", navHistory: "历史", navProfile: "我的", navSettings: "设置", logout: "退出登录",
    untitled: "未命名课堂", lectureInfo: "课堂信息",
    metaNote: "全部可选。标题和描述能帮助 AI 理解这节课的上下文。",
    fLectureLang: "讲义语言", fUserLang: "你的语言",
    fWindow: "Catch-up 范围", fSource: "音频来源", fFile: "归档文件", minUnit: "分钟",
    srcOpenai: "麦克风 · OpenAI", srcGoogle: "麦克风 · Google", srcReplay: "回放归档",
    titlePh: "未命名课堂", descPh: "描述或备注（可选）",
    hintNew: "按 ● 立即开始，面板会自动收起。",
    hintLive: "改动会自动保存。开始后不能更换音频来源。",
    emptyNew: "按 ● 开始。",
    emptyOpened: "这节课还没有转录内容。",
    recStart: "开始", recPause: "暂停", recResume: "继续",
    stIdle: "", stConnecting: "连接中…", stReconnecting: "重连中…", stRequestMic: "正在请求麦克风…",
    stMicDenied: "无法使用麦克风", stStopped: "已暂停",
    stError: (m) => `错误：${m}`, stLive: "", stReplay: (s) => `${s}× 回放`,
    tellMe: "Tell me", newThread: "新线程", threadsEmpty: "还没有其他线程",
    threadDefault: "关于这节课", msgUnit: (n) => `${n} 条`,
    catchup: "Catch-up", explain: "Explain", chatPlaceholder: "问问这节课的内容…",
    chatEmpty: "没跟上就点 Catch-up，\n听不懂的术语点 Explain，\n其他的随便问。",
    chatEmptyNoSession: "开始转录后，就可以在这里提问或 Catch-up。",
    catchupLoading: (x) => `正在总结最近 ${x} 分钟…`, failed: "失败：",
    historyTitle: "历史", historyEmpty: "还没有课堂。",
    segUnit: (n) => `${n} 段`,
    settingsTitle: "设置", sUiLang: "界面与摘要语言", sLectureLang: "默认讲义语言",
    sWindow: "默认 Catch-up 范围", sTheme: "主题", themeDark: "深色", themeLight: "浅色（即将推出）",
    save: "保存", saved: "已保存", saveFailed: "保存失败",
    confirmInterrupt: "正在转录中，继续会中断当前转录（之后可以从历史里继续）。确定吗？",
    replayLabel: (f, m, n) => `${f} · ${m}分 / ${n}段`,
  },
  en: {
    docTitle: "LecTrace", loginSub: "Zoned out? Catch up in seconds.",
    devLogin: "Continue as local dev", loginHint: "Sign in with Google to revisit past lectures or resume one.",
    loginHintDev: "GOOGLE_CLIENT_ID is not configured — using the local dev login.",
    loginFailed: "Sign-in failed: ",
    navNew: "New lecture", navHistory: "History", navProfile: "Profile", navSettings: "Settings", logout: "Sign out",
    untitled: "Untitled lecture", lectureInfo: "Lecture info",
    metaNote: "Everything is optional. Title and description help the AI understand the lecture's context.",
    fLectureLang: "Lecture language", fUserLang: "Your language",
    fWindow: "Catch-up window", fSource: "Audio source", fFile: "Archive file", minUnit: "min",
    srcOpenai: "Microphone · OpenAI", srcGoogle: "Microphone · Google", srcReplay: "Replay archive",
    titlePh: "Untitled lecture", descPh: "Description or notes (optional)",
    hintNew: "Press ● to start right away — this panel closes by itself.",
    hintLive: "Changes save automatically. The audio source can't change after starting.",
    emptyNew: "Press ● to start.",
    emptyOpened: "No transcript yet for this lecture.",
    recStart: "Start", recPause: "Pause", recResume: "Resume",
    stIdle: "", stConnecting: "Connecting…", stReconnecting: "Reconnecting…", stRequestMic: "Requesting mic…",
    stMicDenied: "Microphone unavailable", stStopped: "Paused",
    stError: (m) => `Error: ${m}`, stLive: "", stReplay: (s) => `${s}× replay`,
    tellMe: "Tell me", newThread: "New thread", threadsEmpty: "No other threads yet",
    threadDefault: "About this lecture", msgUnit: (n) => `${n} msgs`,
    catchup: "Catch-up", explain: "Explain", chatPlaceholder: "Ask about this lecture…",
    chatEmpty: "Lost the thread? Catch-up.\nUnfamiliar term? Explain.\nOr ask anything.",
    chatEmptyNoSession: "Start transcribing to ask questions or catch up here.",
    catchupLoading: (x) => `Summarizing the last ${x} min…`, failed: "Failed: ",
    historyTitle: "History", historyEmpty: "No lectures yet.",
    segUnit: (n) => `${n} segs`,
    settingsTitle: "Settings", sUiLang: "Interface & summary language", sLectureLang: "Default lecture language",
    sWindow: "Default catch-up window", sTheme: "Theme", themeDark: "Dark", themeLight: "Light (coming soon)",
    save: "Save", saved: "Saved", saveFailed: "Save failed",
    confirmInterrupt: "Transcription is running. Continuing will interrupt it (you can resume from History later). Proceed?",
    replayLabel: (f, m, n) => `${f} · ${m} min / ${n} segs`,
  },
};

let uiLang = "ja";
const t = (key) => I18N[uiLang][key] ?? I18N.en[key] ?? key;

function applyI18n() {
  document.documentElement.lang = uiLang;
  document.title = t("docTitle");
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  $("mTitle").placeholder = t("titlePh");
  $("mDesc").placeholder = t("descPh");
  $("devLoginBtn").textContent = t("devLogin");
  renderAll();
}

// ---------------- 通用 ----------------
function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
function fmtDate(epoch) {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleString(uiLang === "en" ? "en-US" : uiLang === "zh" ? "zh-CN" : "ja-JP", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
// 轻量 markdown：**粗体**、- 列表、# 标题 → HTML（先转义）
function renderMd(text) {
  const lines = escapeHtml(text || "").split("\n");
  let html = "", inList = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  for (const raw of lines) {
    const line = raw.trim();
    const li = line.match(/^(?:[-*•・]|\d+[.)])\s+(.*)$/);
    if (li) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(li[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (!line) continue;
    const h = line.match(/^#{1,4}\s+(.*)$/);
    html += h ? `<p><b>${inline(h[1])}</b></p>` : `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (r.status === 401) { showLogin(); throw new Error("unauthorized"); }
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${r.status}`);
  }
  return r;
}
const postJson = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });

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

// =====================================================================
// 状态
// =====================================================================
const state = {
  user: null,
  prefs: { ui_language: "ja", lecture_language: "ja", window_minutes: 3, theme: "dark" },
  authConfig: { google_client_id: "", dev_login: false },
  view: "lecture",
  session: null,          // 当前讲义（服务端 SessionInfo），新建未开始时为 null
  meta: null,             // meta 面板里的本地表单值
  sheetOpen: false,
  demoSessions: [],
  // 转录：transcribing（进行中）/ paused（可续接）/ 都为 false = 还没开始
  ws: null, transcribing: false, paused: false, reconnectAttempts: 0,
  latestT: 0, tBase: 0, wallStart: 0,
  status: { key: "stIdle", param: null, live: false, err: false },
  // 对话
  conversationId: null, threadTitle: "",
};
const MAX_RECONNECT = 5;

// =====================================================================
// 登录
// =====================================================================
async function boot() {
  const [cfg, me] = await Promise.all([
    fetch("/api/auth/config").then((r) => r.json()).catch(() => ({})),
    fetch("/api/auth/me").then((r) => r.json()).catch(() => ({ user: null })),
  ]);
  state.authConfig = cfg;
  if (me.user) enterApp(me.user, me.prefs);
  else showLogin();
}

function showLogin() {
  $("appShell").classList.add("hidden");
  $("loginView").classList.remove("hidden");
  applyI18n();
  const cfg = state.authConfig;
  $("devLoginBtn").classList.toggle("hidden", !cfg.dev_login);
  $("loginHint").textContent = cfg.google_client_id ? t("loginHint") : cfg.dev_login ? t("loginHintDev") : "GOOGLE_CLIENT_ID is not configured.";
  if (cfg.google_client_id) mountGoogleButton(cfg.google_client_id);
}

let gsiLoaded = false;
function mountGoogleButton(clientId) {
  const render = () => {
    google.accounts.id.initialize({ client_id: clientId, callback: onGoogleCredential, ux_mode: "popup" });
    google.accounts.id.renderButton($("googleBtn"), {
      theme: "filled_black", size: "large", shape: "pill", width: 280, text: "signin_with",
      locale: uiLang === "zh" ? "zh-CN" : uiLang,
    });
  };
  if (gsiLoaded && window.google?.accounts) return render();
  const s = document.createElement("script");
  s.src = "https://accounts.google.com/gsi/client";
  s.async = true;
  s.onload = () => { gsiLoaded = true; render(); };
  document.head.appendChild(s);
}

async function onGoogleCredential(resp) {
  try {
    const r = await postJson("/api/auth/google", { credential: resp.credential });
    const d = await r.json();
    enterApp(d.user, d.prefs);
  } catch (e) {
    $("loginHint").textContent = t("loginFailed") + e.message;
  }
}

async function devLogin() {
  try {
    const r = await postJson("/api/auth/dev", {});
    const d = await r.json();
    enterApp(d.user, d.prefs);
  } catch (e) {
    $("loginHint").textContent = t("loginFailed") + e.message;
  }
}

async function logout() {
  teardownTranscription();
  await postJson("/api/auth/logout", {}).catch(() => {});
  state.user = null;
  $("profileMenu").classList.add("hidden");
  location.reload();
}

function enterApp(user, prefs) {
  state.user = user;
  state.prefs = { ...state.prefs, ...(prefs || {}) };
  uiLang = state.prefs.ui_language || "ja";
  document.documentElement.dataset.theme = state.prefs.theme || "dark";
  $("loginView").classList.add("hidden");
  $("appShell").classList.remove("hidden");
  renderProfile();
  loadDemoSessions();
  newLecture();
  applyI18n();
}

function renderProfile() {
  const u = state.user;
  if (!u) return;
  const img = u.picture ? `<img src="${escapeHtml(u.picture)}" alt="" referrerpolicy="no-referrer">` : `<svg class="icon"><use href="#i-user"/></svg>`;
  $("avatar").innerHTML = img;
  $("profileAvatar").innerHTML = img;
  $("profileName").textContent = u.name || u.email;
  $("profileEmail").textContent = u.email;
}

async function loadDemoSessions() {
  try {
    const r = await api("/api/demo-sessions");
    state.demoSessions = (await r.json()).sessions || [];
    renderFileOptions();
  } catch (e) { /* 没有归档也无妨 */ }
}

// =====================================================================
// 视图 / 抽屉
// =====================================================================
function showView(view) {
  state.view = view;
  for (const v of ["lecture", "settings"]) $(v + "View").classList.toggle("hidden", v !== view);
  $("navSettings").classList.toggle("active", view === "settings");
  $("profileMenu").classList.add("hidden");
  closeHistory();
  if (view === "settings") renderSettings();
  if (view === "lecture") { resizeWave(); if (state.sheetOpen) layoutSheet(); }
}

function toggleHistory() {
  const open = !$("historyDrawer").classList.contains("open");
  $("historyDrawer").classList.toggle("open", open);
  $("navHistory").classList.toggle("active", open);
  if (open) loadHistory();
}
function closeHistory() {
  $("historyDrawer").classList.remove("open");
  $("navHistory").classList.remove("active");
}

// 转录中要离开当前讲义时提示会中断
function confirmInterrupt() {
  return !state.transcribing || confirm(t("confirmInterrupt"));
}

// =====================================================================
// 讲义：新建 / 打开
// =====================================================================
function defaultMeta() {
  return {
    title: "", description: "",
    lecture_language: state.prefs.lecture_language || "ja",
    user_language: state.prefs.ui_language || "ja",
    window_minutes: Number(state.prefs.window_minutes) || 3,
    source: "openai-stt", file: "",
  };
}

function newLecture() {
  if (!confirmInterrupt()) return;
  teardownTranscription();
  state.session = null;
  state.meta = defaultMeta();
  state.latestT = 0; state.tBase = 0;
  state.conversationId = null; state.threadTitle = "";
  setStatus("stIdle");
  $("transcript").innerHTML = "";
  renderChatEmpty();
  showView("lecture");
  renderMetaForm();
  setSheet(true);
  renderAll();
  fetch("/api/health").then((r) => r.json()).then((h) => {
    if (!state.session && ["openai-stt", "google-stt", "replay"].includes(h.transcription_source)) {
      state.meta.source = h.transcription_source;
      renderMetaForm();
    }
  }).catch(() => {});
}

async function openLecture(id) {
  if (state.session?.id === id) { closeHistory(); showView("lecture"); return; }
  if (!confirmInterrupt()) return;
  teardownTranscription();
  let data;
  try {
    data = await (await api(`/api/sessions/${id}`)).json();
  } catch (e) { return; }
  state.session = data.session;
  state.meta = pickMeta(data.session);
  state.conversationId = null; state.threadTitle = "";
  state.latestT = data.session.latest_t || 0;
  state.tBase = state.latestT;
  state.paused = state.latestT > 0;
  setStatus(state.paused ? "stStopped" : "stIdle");
  $("transcript").innerHTML = "";
  for (const s of data.segments) appendSegment(s.text, s.t, false);
  $("transcript").scrollTop = $("transcript").scrollHeight;
  showView("lecture");
  renderMetaForm();
  setSheet(false);
  renderAll();
  loadLatestThread();
}

function pickMeta(s) {
  return {
    title: s.title || "", description: s.description || "",
    lecture_language: s.lecture_language || "ja", user_language: s.user_language || "ja",
    window_minutes: Number(s.window_minutes) || 3, source: s.source || "openai-stt", file: s.file || "",
  };
}

// ---------------- meta 面板 ----------------
function renderMetaForm() {
  const m = state.meta;
  if (!m) return;
  $("mTitle").value = m.title;
  $("mDesc").value = m.description;
  autosize($("mDesc"), 160);
  $("mLectureLang").value = m.lecture_language;
  $("mUserLang").value = m.user_language;
  $("mWindow").value = m.window_minutes;
  $("mWindowVal").textContent = m.window_minutes;
  $("mSource").value = m.source;
  renderFileOptions();
  const started = !!(state.session && state.session.segment_count > 0) || state.transcribing;
  $("mSource").disabled = started;
  $("mFile").disabled = started;
  $("mFileField").classList.toggle("hidden", m.source !== "replay");
  $("sheetHint").innerHTML = `<span class="dot"></span>${escapeHtml(started ? t("hintLive") : t("hintNew"))}`;
  $("sheet").classList.toggle("locked", started);
}

function renderFileOptions() {
  const sel = $("mFile");
  const cur = state.meta?.file || sel.value;
  sel.innerHTML = "";
  for (const s of state.demoSessions) {
    const opt = document.createElement("option");
    const mins = s.duration_sec ? Math.round(s.duration_sec / 60) : "?";
    opt.value = s.file;
    opt.textContent = t("replayLabel")(s.file, mins, s.line_count);
    sel.appendChild(opt);
  }
  if (state.demoSessions.length) {
    sel.value = cur && state.demoSessions.some((s) => s.file === cur) ? cur : state.demoSessions[state.demoSessions.length - 1].file;
    if (state.meta) state.meta.file = sel.value;
  }
}

let metaSaveTimer = null;
function onMetaChange() {
  const m = state.meta;
  m.title = $("mTitle").value;
  m.description = $("mDesc").value;
  m.lecture_language = $("mLectureLang").value;
  m.user_language = $("mUserLang").value;
  m.window_minutes = Number($("mWindow").value);
  m.source = $("mSource").value;
  m.file = $("mFile").value || "";
  $("mWindowVal").textContent = m.window_minutes;
  $("mFileField").classList.toggle("hidden", m.source !== "replay");
  autosize($("mDesc"), 160);
  renderMetaLabel();
  renderQuick();
  if (state.session) {
    clearTimeout(metaSaveTimer);
    metaSaveTimer = setTimeout(saveMeta, 500);
  }
  if (state.sheetOpen) layoutSheet();
}

async function saveMeta() {
  if (!state.session) return;
  const m = state.meta;
  const patch = {
    title: m.title, description: m.description, lecture_language: m.lecture_language,
    user_language: m.user_language, window_minutes: m.window_minutes,
  };
  if (!(state.session.segment_count > 0) && !state.transcribing) { patch.source = m.source; patch.file = m.file; }
  try {
    const r = await api(`/api/sessions/${state.session.id}`, { method: "PATCH", body: JSON.stringify(patch) });
    const info = await r.json();
    state.session = { ...state.session, ...info };
  } catch (e) { /* 下次改动会再试 */ }
}

function renderMetaLabel() {
  const title = state.meta?.title?.trim();
  $("metaLabel").textContent = title || (state.session ? t("untitled") : t("lectureInfo"));
}

function setSheet(open) {
  state.sheetOpen = open;
  $("metaBtn").classList.toggle("open", open);
  layoutSheet();
  renderTranscriptEmpty();
}
function layoutSheet() {
  const inner = $("sheetInner");
  if (!state.sheetOpen) { inner.style.setProperty("--sheet-h", "0px"); return; }
  const body = $("sheetBody");
  const avail = $("sheet").clientHeight - 72; // 减去渐变高度
  const h = Math.min(body.scrollHeight, Math.max(avail, 0));
  inner.style.setProperty("--sheet-h", `${h}px`);
}

// =====================================================================
// 转录：开始 / 暂停 / 继续
// =====================================================================
let micStream = null, audioCtx = null, processor = null, analyser = null;
let micTargetRate = 16000;
const isMic = () => state.meta?.source !== "replay";

function setStatus(key, { param = null, live = false, err = false } = {}) {
  state.status = { key, param, live, err };
  renderStatus();
}
function renderStatus() {
  const { key, param, live, err } = state.status;
  const el = $("liveStatus");
  const v = t(key);
  let text = typeof v === "function" ? v(param) : v;
  if (live) {
    const shown = Math.max(state.latestT, state.tBase + (Date.now() - state.wallStart) / 1000);
    text = fmtTime(shown) + (text ? ` · ${text}` : "");
  } else if (state.paused && state.latestT > 0) {
    text = `${fmtTime(state.latestT)} · ${text || t("stStopped")}`;
  }
  el.textContent = text;
  el.classList.toggle("live", live);
  el.classList.toggle("err", err);
}
setInterval(() => { if (state.status.live) renderStatus(); }, 1000);

function renderRec() {
  const btn = $("recBtn"), icon = $("recIcon");
  btn.classList.toggle("live", state.transcribing);
  btn.classList.remove("busy");
  btn.disabled = false;
  let use, title;
  if (state.transcribing) { use = "#i-pause"; title = t("recPause"); }
  else if (state.paused || state.session?.segment_count > 0) { use = "#i-play"; title = t("recResume"); }
  else { use = isMic() ? "#i-mic" : "#i-play"; title = t("recStart"); }
  icon.setAttribute("href", use);
  btn.title = title;
}

function closeWs() {
  if (state.ws) { try { state.ws.onclose = null; state.ws.close(); } catch (e) {} state.ws = null; }
}

async function onRecClick() {
  if (state.transcribing) { pauseTranscription(); return; }
  // 新讲义：先在服务端建会话
  if (!state.session) {
    $("recBtn").classList.add("busy");
    try {
      const r = await postJson("/api/sessions", state.meta);
      state.session = await r.json();
    } catch (e) {
      setStatus("stError", { param: e.message, err: true });
      $("recBtn").classList.remove("busy");
      return;
    }
  }
  setSheet(false);
  state.paused = false;
  state.transcribing = true;
  state.reconnectAttempts = 0;
  renderAll();
  if (isMic()) await startMic();
  else startReplay();
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/transcribe?session=${encodeURIComponent(state.session.id)}`;
}

function startReplay() {
  closeWs();
  const ws = new WebSocket(wsUrl());
  state.ws = ws;
  ws.onmessage = onTranscriptMessage;
  ws.onclose = () => { if (state.transcribing) enterPaused(); };
  ws.onerror = () => setStatus("stError", { param: "ws", err: true });
  setStatus("stConnecting");
}

// 转录消息统一处理（回放 + 麦克风共用）
function onTranscriptMessage(ev) {
  if (typeof ev.data !== "string") return;
  const msg = JSON.parse(ev.data);
  if (msg.type === "session") {
    state.reconnectAttempts = 0;
    state.tBase = Number(msg.t_offset) || 0;
    state.wallStart = Date.now();
    if (msg.source === "replay") setStatus("stReplay", { param: msg.speed, live: true });
    else setStatus("stLive", { live: true });
    renderAll();
  } else if (msg.type === "interim") {
    showInterim(msg.text);
  } else if (msg.type === "segment") {
    appendSegment(msg.text, msg.t, true);
    if (state.session) state.session.segment_count = (state.session.segment_count || 0) + 1;
    renderQuick();
  } else if (msg.type === "end") {
    // 回放放完 / 服务端收尾：进入暂停态（随时可继续）
    if (state.transcribing) enterPaused();
  } else if (msg.type === "error") {
    enterPaused();
    setStatus("stError", { param: msg.message, err: true });
  }
}

// 暂停：麦克风立刻进入暂停态，并让服务端把尾段 final 发完；回放让服务端停在当前位置
function pauseTranscription() {
  if (!state.transcribing) return;
  if (state.ws) { try { if (state.ws.readyState === 1) state.ws.send("stop"); } catch (e) {} }
  enterPaused();
}

// 进入暂停态。不主动关 ws：让服务端把尾段 final 发完再自然关闭
function enterPaused() {
  state.transcribing = false;
  state.paused = true;
  stopAudio();
  removeInterim();
  if (state.ws) state.ws.onclose = null;
  setStatus("stStopped");
  renderAll();
}

// 彻底收尾（切换讲义 / 退出登录）：不保留任何连接
function teardownTranscription() {
  if (state.ws) { try { if (state.ws.readyState === 1) state.ws.send("stop"); } catch (e) {} }
  stopAudio();
  closeWs();
  state.transcribing = false;
  state.paused = false;
}

function stopAudio() {
  if (processor) { try { processor.disconnect(); processor.onaudioprocess = null; } catch (e) {} processor = null; }
  if (analyser) { try { analyser.disconnect(); } catch (e) {} analyser = null; }
  if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
  if (micStream) { micStream.getTracks().forEach((tr) => tr.stop()); micStream = null; }
}

// ---- 麦克风 ----
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
  closeWs();
  micTargetRate = state.meta.source === "openai-stt" ? 24000 : 16000; // OpenAI 24kHz / Google 16kHz
  setStatus("stRequestMic");
  try {
    // 保留浏览器默认人声处理：autoGainControl 会把偏小的麦克风输入提升到可用音量
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    state.transcribing = false;
    state.paused = state.session?.segment_count > 0;
    setStatus("stMicDenied", { err: true });
    renderAll();
    return;
  }
  setupAudioGraph();
  state.reconnectAttempts = 0;
  openMicWs();
}

// 音频采集图：只建一次，重连时复用（onaudioprocess 引用 state.ws，重开 ws 即可续发）
function setupAudioGraph() {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === "suspended") audioCtx.resume(); // 异步创建的 AudioContext 可能被挂起
  const src = audioCtx.createMediaStreamSource(micStream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  src.connect(analyser);
  processor = audioCtx.createScriptProcessor(4096, 1, 1);
  const sink = audioCtx.createGain();
  sink.gain.value = 0; // 静音接到 destination，保证 onaudioprocess 触发又不回放
  src.connect(processor);
  processor.connect(sink);
  sink.connect(audioCtx.destination);
  processor.onaudioprocess = (e) => {
    const ws = state.ws;
    if (!ws || ws.readyState !== 1) return; // 重连间隙丢弃(几秒)，可接受
    const input = e.inputBuffer.getChannelData(0);
    const pcm = floatTo16BitPCM(downsample(input, audioCtx.sampleRate, micTargetRate));
    ws.send(pcm.buffer);
  };
}

function openMicWs() {
  const ws = new WebSocket(wsUrl());
  ws.binaryType = "arraybuffer";
  ws.onmessage = onTranscriptMessage;
  // 意外断开（含 60 分钟超时）→ 自动续接，无需用户操作
  ws.onclose = () => { if (state.transcribing) autoReconnect(); };
  state.ws = ws;
}

function autoReconnect() {
  state.reconnectAttempts++;
  if (state.reconnectAttempts > MAX_RECONNECT) { enterPaused(); return; }
  setStatus("stReconnecting");
  openMicWs();
}

// ---- 转录渲染 ----
const transcriptEl = $("transcript");
function nearBottom() {
  return transcriptEl.scrollHeight - transcriptEl.scrollTop - transcriptEl.clientHeight < 120;
}
function appendSegment(text, tSec, animate) {
  removeInterim();
  const atBottom = nearBottom();
  const div = document.createElement("div");
  div.className = "seg";
  div.dataset.t = tSec;
  if (!animate) { div.style.animation = "none"; div.style.opacity = 1; }
  div.innerHTML = `<span class="ts">${fmtTime(tSec)}</span><span class="tx">${escapeHtml(text)}</span>`;
  transcriptEl.appendChild(div);
  state.latestT = Math.max(state.latestT, tSec);
  if (atBottom) transcriptEl.scrollTop = transcriptEl.scrollHeight;
  $("transcriptEmpty").classList.add("hidden");
  waveEnergy = Math.min(1, waveEnergy + 0.6);
}
function showInterim(text) {
  const atBottom = nearBottom();
  let p = $("pendingSeg");
  if (!p) {
    p = document.createElement("div");
    p.className = "seg pending";
    p.id = "pendingSeg";
    transcriptEl.appendChild(p);
  }
  p.innerHTML = `<span class="ts"></span><span class="tx">${escapeHtml(text)}</span>`;
  if (atBottom) transcriptEl.scrollTop = transcriptEl.scrollHeight;
  $("transcriptEmpty").classList.add("hidden");
}
function removeInterim() { $("pendingSeg")?.remove(); }

function renderTranscriptEmpty() {
  const empty = !transcriptEl.querySelector(".seg");
  const el = $("transcriptEmpty");
  el.classList.toggle("hidden", !empty || state.sheetOpen);
  el.textContent = state.session ? t("emptyOpened") : t("emptyNew");
}

// ---- 声波 ----
const waveCanvas = $("wave");
let waveEnergy = 0;
function resizeWave() {
  const dpr = window.devicePixelRatio || 1;
  const r = waveCanvas.getBoundingClientRect();
  if (!r.width) return;
  waveCanvas.width = Math.round(r.width * dpr);
  waveCanvas.height = Math.round(r.height * dpr);
}
let wavePhase = 0;
function drawWave() {
  requestAnimationFrame(drawWave);
  if (state.view !== "lecture") return;
  const ctx = waveCanvas.getContext("2d");
  const W = waveCanvas.width, H = waveCanvas.height;
  if (!W) { resizeWave(); return; }
  ctx.clearRect(0, 0, W, H);
  const mid = H / 2, dpr = window.devicePixelRatio || 1;
  const color = getComputedStyle(document.documentElement).getPropertyValue(state.transcribing ? "--text" : "--line-strong").trim();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4 * dpr;
  ctx.lineJoin = "round";
  ctx.beginPath();
  const N = 160;
  if (analyser && state.transcribing) {
    const buf = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buf);
    const step = buf.length / N;
    for (let i = 0; i < N; i++) {
      const v = buf[Math.floor(i * step)];
      const env = Math.sin((i / (N - 1)) * Math.PI) ** 0.6; // 两端收窄的包络
      const y = mid - v * env * mid * 2.4;
      i ? ctx.lineTo((i / (N - 1)) * W, y) : ctx.moveTo(0, y);
    }
  } else {
    // 回放 / 空闲：合成波，幅度随段落到达衰减
    wavePhase += 0.12;
    waveEnergy *= 0.94;
    const amp = state.transcribing ? 0.08 + waveEnergy * 0.5 : 0.02;
    for (let i = 0; i < N; i++) {
      const x = i / (N - 1);
      const env = Math.sin(x * Math.PI) ** 0.8;
      const v = Math.sin(x * 28 + wavePhase) * 0.6 + Math.sin(x * 13 - wavePhase * 1.3) * 0.4;
      const y = mid - v * env * amp * mid * 2;
      i ? ctx.lineTo(x * W, y) : ctx.moveTo(0, y);
    }
  }
  ctx.stroke();
}

// =====================================================================
// 对话：线程 / Catch-up / Explain / 自由提问
// =====================================================================
const chatMessages = $("chatMessages");

function renderChatEmpty() {
  chatMessages.dataset.empty = "1";
  chatMessages.innerHTML = `<div class="chat-empty">${escapeHtml(state.session ? t("chatEmpty") : t("chatEmptyNoSession"))}</div>`;
}
function ensureChatList() {
  if (chatMessages.dataset.empty === "1") { chatMessages.innerHTML = ""; chatMessages.dataset.empty = "0"; }
}
function scrollChat() { chatMessages.scrollTop = chatMessages.scrollHeight; }

function addUserBubble(text) {
  ensureChatList();
  const div = document.createElement("div");
  div.className = "msg user";
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollChat();
  return div;
}
function addAssistant(kind) {
  ensureChatList();
  const div = document.createElement("div");
  div.className = "msg assistant streaming" + (kind === "catchup" ? " catchup" : "");
  div.innerHTML = (kind === "catchup" ? `<div class="msg-tag">${escapeHtml(t("catchup"))}</div>` : "") + `<div class="msg-body"></div>`;
  chatMessages.appendChild(div);
  scrollChat();
  return div;
}
function setBody(div, text, { error = false, done = false, loading = false } = {}) {
  const body = div.querySelector(".msg-body");
  body.classList.toggle("loading", loading);
  if (error) { div.classList.add("err"); body.textContent = text; }
  else if (loading) body.textContent = text;
  else body.innerHTML = renderMd(text);
  if (done || error) div.classList.remove("streaming");
  if (nearChatBottom) scrollChat();
}
let nearChatBottom = true;
chatMessages.addEventListener("scroll", () => {
  nearChatBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 80;
});

function renderMessages(messages) {
  chatMessages.innerHTML = ""; chatMessages.dataset.empty = "0";
  if (!messages.length) { renderChatEmpty(); return; }
  for (const m of messages) {
    if (m.role === "user") { addUserBubble(m.content); continue; }
    const div = addAssistant(m.kind === "catchup" ? "catchup" : "chat");
    setBody(div, m.content, { done: true });
  }
  scrollChat();
}

async function loadLatestThread() {
  if (!state.session) return;
  try {
    const { conversations } = await (await api(`/api/sessions/${state.session.id}/conversations`)).json();
    if (conversations.length) await loadThread(conversations[0].id);
    else renderChatEmpty();
  } catch (e) { renderChatEmpty(); }
}
async function loadThread(id) {
  const conv = await (await api(`/api/conversations/${id}`)).json();
  state.conversationId = conv.id;
  state.threadTitle = conv.title;
  renderThreadTitle();
  renderMessages(conv.messages);
}
function newThread() {
  state.conversationId = null; state.threadTitle = "";
  renderThreadTitle();
  renderChatEmpty();
  $("threadMenu").classList.add("hidden");
  $("chatInput").focus();
}
function renderThreadTitle() {
  $("threadTitle").textContent = state.threadTitle || (state.session ? t("threadDefault") : "");
}

async function toggleThreadMenu() {
  const menu = $("threadMenu");
  if (!menu.classList.contains("hidden")) { menu.classList.add("hidden"); return; }
  menu.innerHTML = `<button class="menu-item" id="menuNewThread">${escapeHtml(t("newThread"))}</button><div class="menu-sep"></div><div class="menu-empty">…</div>`;
  menu.classList.remove("hidden");
  $("menuNewThread").onclick = newThread;
  if (!state.session) { menu.querySelector(".menu-empty").textContent = t("threadsEmpty"); return; }
  try {
    const { conversations } = await (await api(`/api/sessions/${state.session.id}/conversations`)).json();
    menu.querySelector(".menu-empty").remove();
    if (!conversations.length) { menu.insertAdjacentHTML("beforeend", `<div class="menu-empty">${escapeHtml(t("threadsEmpty"))}</div>`); return; }
    for (const c of conversations) {
      const b = document.createElement("button");
      b.className = "menu-item" + (c.id === state.conversationId ? " active" : "");
      b.innerHTML = `<span>${escapeHtml(c.title)}</span><span class="sub">${escapeHtml(t("msgUnit")(c.message_count))} · ${fmtTime(c.created_t)}</span>`;
      b.onclick = () => { menu.classList.add("hidden"); loadThread(c.id); };
      menu.appendChild(b);
    }
  } catch (e) {
    menu.querySelector(".menu-empty").textContent = t("failed") + e.message;
  }
}

let busy = false;
function setBusy(v) { busy = v; renderQuick(); }
function renderQuick() {
  const can = !!state.session && state.latestT > 0 && !busy;
  $("catchupBtn").disabled = !can;
  $("explainBtn").disabled = !can;
  $("sendBtn").disabled = !state.session || busy;
  $("catchupWin").textContent = state.meta ? `· ${state.meta.window_minutes}${t("minUnit")}` : "";
}

async function doCatchup() {
  if (!state.session || busy) return;
  setBusy(true);
  const win = state.meta.window_minutes;
  const div = addAssistant("catchup");
  setBody(div, t("catchupLoading")(win), { loading: true });
  let acc = "";
  try {
    const r = await postJson("/api/catchup", {
      session_id: state.session.id, window_minutes: win, conversation_id: state.conversationId,
    });
    await parseSSE(r.body, {
      meta: (m) => {
        state.conversationId = m.conversation_id;
        if (!state.threadTitle) { state.threadTitle = m.conversation_title; renderThreadTitle(); }
      },
      text: (txt) => { acc += txt; setBody(div, acc); },
      error: (p) => setBody(div, t("failed") + p.message, { error: true }),
      done: () => setBody(div, acc, { done: true }),
    });
  } catch (e) {
    setBody(div, t("failed") + e.message, { error: true });
  } finally {
    setBusy(false);
  }
}

async function sendChat({ preset = null, message = "" } = {}) {
  if (!state.session || busy) return;
  message = message.trim();
  if (!preset && !message) return;
  setBusy(true);
  const userBubble = addUserBubble(message || "…");
  const div = addAssistant("chat");
  let acc = "";
  try {
    const r = await postJson("/api/chat", {
      session_id: state.session.id, message, conversation_id: state.conversationId, preset,
    });
    await parseSSE(r.body, {
      meta: (m) => {
        state.conversationId = m.conversation_id;
        if (m.user_message) userBubble.textContent = m.user_message;
        if (!state.threadTitle) { state.threadTitle = m.title; renderThreadTitle(); }
      },
      text: (txt) => { acc += txt; setBody(div, acc); },
      error: (p) => setBody(div, t("failed") + p.message, { error: true }),
      done: () => setBody(div, acc, { done: true }),
    });
  } catch (e) {
    setBody(div, t("failed") + e.message, { error: true });
  } finally {
    setBusy(false);
  }
}

function onSend() {
  const input = $("chatInput");
  const msg = input.value;
  if (!msg.trim()) return;
  input.value = "";
  autosize(input, 150);
  sendChat({ message: msg });
}
function autosize(ta, max) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, max) + "px";
}

// =====================================================================
// 历史抽屉 / 设置 / 资料
// =====================================================================
async function loadHistory() {
  const list = $("historyList");
  list.innerHTML = `<div class="history-empty">…</div>`;
  try {
    const { sessions } = await (await api("/api/sessions")).json();
    if (!sessions.length) { list.innerHTML = `<div class="history-empty">${escapeHtml(t("historyEmpty"))}</div>`; return; }
    list.innerHTML = "";
    for (const s of sessions) {
      const b = document.createElement("button");
      b.className = "hist-card" + (state.session?.id === s.id ? " current" : "");
      b.innerHTML = `
        <div class="hist-title">${escapeHtml(s.title || t("untitled"))}</div>
        <div class="hist-meta">
          <span>${escapeHtml(fmtDate(s.created_at))}</span>
          <span>${fmtTime(s.latest_t)}</span>
          <span>${escapeHtml(t("segUnit")(s.segment_count))}</span>
        </div>`;
      b.onclick = () => openLecture(s.id);
      list.appendChild(b);
    }
  } catch (e) {
    list.innerHTML = `<div class="history-empty">${escapeHtml(t("failed") + e.message)}</div>`;
  }
}

function renderSettings() {
  const p = state.prefs;
  $("sUiLang").value = p.ui_language;
  $("sLectureLang").value = p.lecture_language;
  $("sWindow").value = p.window_minutes;
  $("sWindowVal").textContent = p.window_minutes;
  $("sTheme").value = p.theme || "dark";
  $("prefsStatus").textContent = "";
}
async function savePrefs() {
  const prefs = {
    ui_language: $("sUiLang").value, lecture_language: $("sLectureLang").value,
    window_minutes: Number($("sWindow").value), theme: $("sTheme").value,
  };
  try {
    const r = await api("/api/me/prefs", { method: "PUT", body: JSON.stringify(prefs) });
    state.prefs = await r.json();
    uiLang = state.prefs.ui_language;
    document.documentElement.dataset.theme = state.prefs.theme || "dark";
    applyI18n();
    renderSettings();
    $("prefsStatus").textContent = t("saved");
  } catch (e) {
    $("prefsStatus").textContent = t("saveFailed") + " " + e.message;
  }
}

function renderAll() {
  renderMetaLabel();
  renderStatus();
  renderRec();
  renderQuick();
  renderThreadTitle();
  renderTranscriptEmpty();
  if (chatMessages.dataset.empty === "1") renderChatEmpty();
  if (state.meta) renderMetaForm();
}

// =====================================================================
// 事件绑定
// =====================================================================
$("devLoginBtn").addEventListener("click", devLogin);
$("logoutBtn").addEventListener("click", logout);
$("navNew").addEventListener("click", newLecture);
$("navLogo").addEventListener("click", () => showView("lecture"));
$("navHistory").addEventListener("click", (e) => { e.stopPropagation(); toggleHistory(); });
$("navSettings").addEventListener("click", () => showView(state.view === "settings" ? "lecture" : "settings"));
$("navProfile").addEventListener("click", (e) => { e.stopPropagation(); $("profileMenu").classList.toggle("hidden"); });

$("recBtn").addEventListener("click", onRecClick);
$("metaBtn").addEventListener("click", () => setSheet(!state.sheetOpen));
for (const id of ["mTitle", "mDesc", "mLectureLang", "mUserLang", "mWindow", "mSource", "mFile"]) {
  $(id).addEventListener("input", onMetaChange);
  $(id).addEventListener("change", onMetaChange);
}

$("threadBtn").addEventListener("click", (e) => { e.stopPropagation(); toggleThreadMenu(); });
$("catchupBtn").addEventListener("click", doCatchup);
$("explainBtn").addEventListener("click", () => sendChat({ preset: "explain" }));
$("sendBtn").addEventListener("click", onSend);
$("chatInput").addEventListener("input", (e) => autosize(e.target, 150));
$("chatInput").addEventListener("keydown", (e) => {
  // 输入法组合中的 Enter 不发送；keyCode 229 兼容旧浏览器
  if (e.isComposing || e.keyCode === 229) return;
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
});

$("sWindow").addEventListener("input", () => { $("sWindowVal").textContent = $("sWindow").value; });
$("savePrefsBtn").addEventListener("click", savePrefs);

document.addEventListener("click", (e) => {
  if (!e.target.closest("#threadMenu, #threadBtn")) $("threadMenu").classList.add("hidden");
  if (!e.target.closest("#profileMenu, #navProfile")) $("profileMenu").classList.add("hidden");
  if (!e.target.closest("#historyDrawer, #navHistory")) closeHistory();
});
window.addEventListener("resize", () => { resizeWave(); if (state.sheetOpen) layoutSheet(); });
window.addEventListener("beforeunload", (e) => { if (state.transcribing) e.preventDefault(); });

// 启动
applyI18n();
resizeWave();
drawWave();
boot();
