const AUTH_STORAGE_KEY = "breakfast_auth";
const API_TIMEOUT_MS = 10000;

const ROLE_LABEL = {
  staff: "櫃台",
  kitchen: "廚房",
  manager: "店長",
  owner: "老闆",
};

const ROLE_META = [
  { role: "staff", label: "櫃台", description: "開單、收銀、修單" },
  { role: "kitchen", label: "廚房", description: "看單、出餐、更新狀態" },
  { role: "manager", label: "店長", description: "管理菜單、庫存、營運數據" },
  { role: "owner", label: "老闆", description: "全權限與帳號管理" },
];

const DEMO_CREDENTIALS = [
  "staff1 / staff1234",
  "kitchen1 / kitchen1234",
  "manager1 / manager1234",
  "owner1 / owner1234",
];

let _publicConfig = null;
async function fetchPublicConfig() {
  if (_publicConfig) return _publicConfig;
  try {
    const res = await fetch("/api/config/public");
    if (res.ok) {
      const data = await res.json();
      _publicConfig = {
        env: data?.env || "development",
        auth_disabled: Boolean(data?.auth_disabled),
      };
    }
  } catch (_) {
    // fallback
  }
  if (!_publicConfig) {
    _publicConfig = { env: "development", auth_disabled: false };
  }
  return _publicConfig;
}

async function fetchAppEnv() {
  const conf = await fetchPublicConfig();
  return conf.env || "development";
}

async function isAuthDisabled() {
  const conf = await fetchPublicConfig();
  return Boolean(conf.auth_disabled);
}

function translateErrorText(text) {
  if (!text) return "";
  let output = String(text);
  const mappings = [
    ["Insufficient inventory", "庫存不足"],
    ["Missing bearer token", "缺少登入憑證"],
    ["Invalid or expired token", "登入憑證失效，請重新登入"],
    ["Permission denied", "你沒有這個操作權限"],
    ["Invalid username or password", "帳號或密碼錯誤"],
    ["Order not found", "?????"],
    ["Request failed", "請求失敗，請稍後再試"],
    [
      "Completed or cancelled orders cannot be amended",
      "已完成或已取消的訂單不可修單",
    ],
  ];
  mappings.forEach(([from, to]) => {
    output = output.split(from).join(to);
  });
  return output;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getSession() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function saveSession(session) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

function tokenHeaders() {
  const session = getSession();
  if (!session || !session.access_token) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

async function readErrorMessage(response) {
  try {
    const data = await response.clone().json();
    if (typeof data?.detail === "string") return translateErrorText(data.detail);
    if (Array.isArray(data?.detail)) return translateErrorText(data.detail.join(", "));
    if (data?.detail?.message) {
      const shortages = Array.isArray(data.detail.shortages) ? data.detail.shortages : [];
      if (!shortages.length) return translateErrorText(data.detail.message);
      const rows = shortages
        .map((row) => `${row.ingredient_name} (${row.current_stock}/${row.required} ${row.unit})`)
        .join(", ");
      return translateErrorText(`${data.detail.message}: ${rows}`);
    }
    if (typeof data?.message === "string") return translateErrorText(data.message);
  } catch (_) {
    // Ignore JSON parse error and fallback to plain text.
  }

  try {
    const text = await response.text();
    if (text) return translateErrorText(text);
  } catch (_) {
    // Ignore text parse error and fallback to status code.
  }
  return translateErrorText(`HTTP ${response.status}`);
}

async function authFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const retries = options.retries ?? (method === "GET" ? 1 : 0);
  const timeoutMs = options.timeoutMs ?? API_TIMEOUT_MS;
  const headers = {
    ...(options.headers || {}),
    ...tokenHeaders(),
  };

  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });
      if (response.status === 401) {
        clearSession();
      }
      if (response.status >= 500 && attempt < retries) {
        await sleep(300 * (attempt + 1));
        continue;
      }
      return response;
    } catch (err) {
      lastError = err;
      if (attempt >= retries) {
        throw err;
      }
      await sleep(300 * (attempt + 1));
    } finally {
      clearTimeout(timer);
    }
  }

  throw lastError || new Error("Request failed");
}

function buildModal() {
  const roleCards = ROLE_META.map(
    (item) =>
      `<li><strong>${item.label}</strong><span>${item.description}</span></li>`,
  ).join("");
  const credentialList = DEMO_CREDENTIALS.map((item) => `<li>${item}</li>`).join("");

  const backdrop = document.createElement("div");
  backdrop.className = "auth-backdrop";
  backdrop.innerHTML = `
    <div class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="authTitle">
      <section class="auth-brand">
        <p class="auth-kicker">BREAKFAST OPS</p>
        <h2 id="authTitle">登入早餐店系統</h2>
        <p class="auth-lead">POS、KDS、後台共用登入。登入後會依角色自動開啟對應功能。</p>
        <ul class="auth-role-list">${roleCards}</ul>
      </section>
      <section class="auth-panel">
        <form id="authForm" novalidate>
          <label for="authUsername">帳號</label>
          <input id="authUsername" name="username" autocomplete="username" required />

          <label for="authPassword">密碼</label>
          <div class="auth-password-wrap">
            <input id="authPassword" name="password" type="password" autocomplete="current-password" required />
            <button id="togglePasswordBtn" class="auth-ghost-btn" type="button">顯示</button>
          </div>

          <button id="authSubmitBtn" class="auth-submit-btn" type="submit">登入</button>
        </form>
        <p id="authMessage" class="auth-message" aria-live="polite"></p>
        <div class="auth-demo">
          <span>測試帳號</span>
          <ul>${credentialList}</ul>
        </div>
      </section>
    </div>
  `;
  document.body.appendChild(backdrop);
  return backdrop;
}

function removeModal(node) {
  if (node && node.parentNode) {
    node.parentNode.removeChild(node);
  }
}

function roleAllowed(role, allowedRoles) {
  if (!allowedRoles || !allowedRoles.length) return true;
  return allowedRoles.includes(role);
}

function ensureStyles() {
  if (document.getElementById("auth-style")) return;
  const style = document.createElement("style");
  style.id = "auth-style";
  style.textContent = `
    @import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700&display=swap");

    :root {
      --auth-pad: clamp(10px, 1.4vw, 16px);
      --auth-gap: clamp(6px, .7vw, 10px);
      --auth-text-xs: clamp(10px, .5vw, 12px);
      --auth-text-sm: clamp(11px, .62vw, 13px);
      --auth-text-md: clamp(12px, .75vw, 14px);
      --auth-radius: clamp(18px, 1.8vw, 26px);
    }

    .auth-backdrop {
      position: fixed;
      inset: 0;
      z-index: 9999;
      padding: var(--auth-pad);
      display: grid;
      place-items: center;
      background: rgba(0, 0, 0, 0.18);
      backdrop-filter: blur(6px);
      animation: authBackdropIn .26s ease both;
    }

    .auth-modal {
      width: min(920px, 100%);
      border-radius: var(--auth-radius);
      overflow: hidden;
      border: 1px solid #E2E8F0;
      background: #ffffff;
      display: grid;
      grid-template-columns: 1.18fr 1fr;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
      animation: authModalIn .32s cubic-bezier(.17, .84, .32, 1) both;
      font-family: "Inter", "Noto Sans TC", sans-serif;
    }

    .auth-brand {
      position: relative;
      padding: clamp(22px, 2.2vw, 34px) clamp(18px, 2vw, 32px) clamp(18px, 1.9vw, 30px);
      color: #FFFFFF;
      background: linear-gradient(155deg, #059669, #10B981 60%, #34D399);
    }

    .auth-brand::after {
      content: "";
      position: absolute;
      width: 180px;
      height: 180px;
      right: -42px;
      bottom: -52px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      opacity: 0.55;
    }

    .auth-kicker {
      margin: 0 0 14px;
      font-size: var(--auth-text-xs);
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: rgba(255, 255, 255, 0.8);
    }

    .auth-brand h2 {
      margin: 0 0 12px;
      font-size: clamp(27px, 4vw, 42px);
      line-height: 1.05;
      letter-spacing: -0.04em;
      font-weight: 800;
    }

    .auth-lead {
      margin: 0 0 20px;
      font-size: var(--auth-text-md);
      line-height: 1.65;
      color: rgba(255, 255, 255, 0.9);
      max-width: 40ch;
    }

    .auth-role-list {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: var(--auth-gap);
    }

    .auth-role-list li {
      border: 1px solid rgba(255, 255, 255, 0.28);
      border-radius: 14px;
      padding: clamp(7px, .68vw, 10px) clamp(9px, .85vw, 12px);
      background: rgba(0, 0, 0, 0.1);
      display: grid;
      gap: 2px;
    }

    .auth-role-list strong {
      font-size: var(--auth-text-sm);
      font-weight: 700;
    }

    .auth-role-list span {
      font-size: var(--auth-text-xs);
      color: rgba(255, 255, 255, 0.84);
      line-height: 1.45;
    }

    .auth-panel {
      padding: clamp(18px, 2vw, 30px) clamp(16px, 1.8vw, 28px);
      color: #1E293B;
      background: #FFFFFF;
    }

    .auth-panel form {
      display: grid;
      gap: var(--auth-gap);
    }

    .auth-panel label {
      font-size: var(--auth-text-sm);
      color: #64748B;
      font-weight: 600;
    }

    .auth-panel input {
      width: 100%;
      border: 1px solid #E2E8F0;
      border-radius: clamp(9px, .8vw, 12px);
      padding: clamp(9px, .9vw, 11px) clamp(10px, .95vw, 12px);
      font-size: var(--auth-text-md);
      color: #1E293B;
      background: #ffffff;
      transition: border-color .18s ease, box-shadow .18s ease;
    }

    .auth-panel input:focus-visible {
      outline: none;
      border-color: #10B981;
      box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
    }

    .auth-password-wrap {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: var(--auth-gap);
      align-items: center;
    }

    .auth-ghost-btn {
      border: 1px solid #E2E8F0;
      border-radius: clamp(8px, .72vw, 11px);
      padding: clamp(8px, .8vw, 10px) clamp(10px, .9vw, 12px);
      min-width: 62px;
      background: #ffffff;
      color: #1E293B;
      font-size: var(--auth-text-xs);
      font-weight: 700;
      cursor: pointer;
      transition: background-color .18s ease, border-color .18s ease;
    }

    .auth-ghost-btn:hover {
      background: #F1F5F9;
      border-color: #CBD5E1;
    }

    .auth-submit-btn {
      margin-top: 4px;
      border: none;
      border-radius: clamp(9px, .8vw, 12px);
      padding: clamp(10px, .95vw, 12px) clamp(11px, 1vw, 14px);
      background: #10B981;
      color: #ffffff;
      font-size: clamp(13px, .8vw, 15px);
      font-weight: 800;
      letter-spacing: 0.02em;
      cursor: pointer;
      transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
      box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25);
    }

    .auth-submit-btn:hover {
      transform: translateY(-1px);
      filter: brightness(1.06);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
    }

    .auth-submit-btn:disabled,
    .auth-ghost-btn:disabled {
      opacity: 0.58;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }

    .auth-message {
      min-height: 22px;
      margin: 10px 0 0;
      font-size: var(--auth-text-sm);
      line-height: 1.45;
      color: #64748B;
    }

    .auth-message.info {
      color: #3B82F6;
    }

    .auth-message.success {
      color: #059669;
    }

    .auth-message.error {
      color: #DC2626;
    }

    .auth-demo {
      margin-top: 14px;
      border-top: 1px dashed #E2E8F0;
      padding-top: clamp(8px, .8vw, 11px);
    }

    .auth-demo > span {
      display: block;
      margin-bottom: 7px;
      font-size: var(--auth-text-xs);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #94A3B8;
      font-weight: 700;
    }

    .auth-demo ul {
      margin: 0;
      padding-left: 16px;
      display: grid;
      gap: 4px;
      color: #64748B;
      font-size: var(--auth-text-sm);
    }

    @keyframes authBackdropIn {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }

    @keyframes authModalIn {
      from {
        opacity: 0;
        transform: translateY(14px) scale(0.98);
      }
      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    @media (max-width: 880px) {
      .auth-modal {
        grid-template-columns: 1fr;
        width: min(560px, 100%);
      }

      .auth-brand {
        padding: clamp(16px, 3.2vw, 24px) clamp(14px, 2.9vw, 22px) clamp(14px, 2.7vw, 20px);
      }

      .auth-brand h2 {
        font-size: clamp(24px, 8vw, 34px);
      }

      .auth-panel {
        padding: clamp(14px, 2.8vw, 22px) clamp(12px, 2.5vw, 18px) clamp(12px, 2.4vw, 20px);
      }

      .auth-role-list {
        grid-template-columns: 1fr 1fr;
      }
    }

    @media (max-width: 560px) {
      .auth-backdrop {
        padding: 10px;
      }

      .auth-modal {
        border-radius: 20px;
      }

      .auth-role-list {
        grid-template-columns: 1fr;
      }
    }
  `;
  document.head.appendChild(style);
}

async function validateSession(allowedRoles) {
  const session = getSession();
  const res = await authFetch("/api/auth/me", { retries: 0 });
  if (!res.ok) return null;

  const me = await res.json();
  if (!roleAllowed(me.role, allowedRoles)) {
    return { denied: true, role: me.role };
  }

  const merged = { ...(session || {}), user: me };
  saveSession(merged);
  return merged;
}

async function loginInteractive(allowedRoles) {
  ensureStyles();
  const env = await fetchAppEnv();
  const modal = buildModal();

  // Hide demo credentials in production
  if (env === "production") {
    const demoSection = modal.querySelector(".auth-demo");
    if (demoSection) demoSection.style.display = "none";
  }
  const form = modal.querySelector("#authForm");
  const usernameInput = modal.querySelector("#authUsername");
  const passwordInput = modal.querySelector("#authPassword");
  const togglePasswordBtn = modal.querySelector("#togglePasswordBtn");
  const submitBtn = modal.querySelector("#authSubmitBtn");
  const message = modal.querySelector("#authMessage");

  const setMessage = (text, tone = "") => {
    message.textContent = text || "";
    message.className = tone ? `auth-message ${tone}` : "auth-message";
  };

  const setSubmitting = (isSubmitting) => {
    submitBtn.disabled = isSubmitting;
    submitBtn.textContent = isSubmitting ? "登入中..." : "登入";
    usernameInput.disabled = isSubmitting;
    passwordInput.disabled = isSubmitting;
    togglePasswordBtn.disabled = isSubmitting;
  };

  usernameInput.focus();

  togglePasswordBtn.addEventListener("click", () => {
    const show = passwordInput.type === "password";
    passwordInput.type = show ? "text" : "password";
    togglePasswordBtn.textContent = show ? "隱藏" : "顯示";
    togglePasswordBtn.setAttribute("aria-label", show ? "隱藏密碼" : "顯示密碼");
    passwordInput.focus({ preventScroll: true });
  });

  return new Promise((resolve) => {
    form.addEventListener("submit", async (evt) => {
      evt.preventDefault();

      const username = usernameInput.value.trim();
      const password = passwordInput.value;
      if (!username || !password) {
        setMessage("請輸入帳號與密碼。", "error");
        return;
      }

      setSubmitting(true);
      setMessage("正在驗證帳號...", "info");

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
          setMessage(await readErrorMessage(res), "error");
          setSubmitting(false);
          return;
        }

        const payload = await res.json();
        if (!roleAllowed(payload.user.role, allowedRoles)) {
          setMessage(
            `你的角色是 ${ROLE_LABEL[payload.user.role] || payload.user.role}，此頁面目前未開放。`,
            "error",
          );
          setSubmitting(false);
          return;
        }

        saveSession(payload);
        setMessage("登入成功，正在載入畫面...", "success");
        removeModal(modal);
        resolve(payload);
      } catch (err) {
        setMessage(translateErrorText(String(err.message || err)), "error");
        setSubmitting(false);
      }
    });
  });
}

async function ensureAuth(allowedRoles = []) {
  const existing = await validateSession(allowedRoles);
  if (existing && !existing.denied) return existing;

  if (existing && existing.denied) {
    clearSession();
  }
  if (await isAuthDisabled()) {
    const passthrough = await validateSession(allowedRoles);
    if (passthrough && !passthrough.denied) return passthrough;
  }
  return loginInteractive(allowedRoles);
}

function getToken() {
  const session = getSession();
  return session?.access_token || "";
}

function openEventSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const token = getToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return new WebSocket(`${protocol}//${location.host}/ws/events${query}`);
}

function connectEventSocket({ onMessage, onConnected, onDisconnected }) {
  let ws = null;
  let pingTimer = null;
  let retryTimer = null;
  let stopped = false;
  let retryAttempt = 0;

  const clearTimers = () => {
    if (pingTimer) clearInterval(pingTimer);
    if (retryTimer) clearTimeout(retryTimer);
    pingTimer = null;
    retryTimer = null;
  };

  const scheduleReconnect = () => {
    if (stopped) return;
    const delayMs = Math.min(15000, 1000 * 2 ** retryAttempt);
    retryAttempt += 1;
    retryTimer = setTimeout(connect, delayMs);
  };

  const connect = () => {
    if (stopped) return;
    ws = openEventSocket();
    ws.onopen = () => {
      retryAttempt = 0;
      if (typeof onConnected === "function") onConnected();
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 20000);
    };
    ws.onmessage = (evt) => {
      if (typeof onMessage === "function") onMessage(evt);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch (_) {
        // Ignore close error.
      }
    };
    ws.onclose = () => {
      clearTimers();
      if (typeof onDisconnected === "function") onDisconnected();
      scheduleReconnect();
    };
  };

  connect();

  return () => {
    stopped = true;
    clearTimers();
    if (ws) {
      try {
        ws.close();
      } catch (_) {
        // Ignore close error.
      }
    }
  };
}

window.Auth = {
  authFetch,
  clearSession,
  connectEventSocket,
  ensureAuth,
  getToken,
  openEventSocket,
  readErrorMessage,
};
