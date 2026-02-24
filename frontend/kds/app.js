const pendingCol = document.getElementById("pendingCol");
const preparingCol = document.getElementById("preparingCol");
const readyCol = document.getElementById("readyCol");

const pendingCount = document.getElementById("pendingCount");
const preparingCount = document.getElementById("preparingCount");
const readyCount = document.getElementById("readyCount");
const lowStockList = document.getElementById("lowStockList");
const alertList = document.getElementById("alertList");
const connectionStatus = document.getElementById("connectionStatus");

const state = {
  orders: [],
  lowStock: [],
  alerts: [],
  highlightedOrders: new Set(),
};

const STATUS_TEXT = {
  pending: "待處理",
  preparing: "製作中",
  ready: "待取餐",
  completed: "已完成",
  cancelled: "已取消",
};

const SOURCE_TEXT = {
  takeout: "外帶",
  dine_in: "內用",
  delivery: "外送",
};

const PAYMENT_TEXT = {
  unpaid: "未付款",
  paid: "已付款",
  refunded: "已退款",
};

const WAIT_RULES = {
  pending: { warn: 8, danger: 12 },
  preparing: { warn: 15, danger: 22 },
  ready: { warn: 5, danger: 10 },
};

let lowStockSignature = "";

function captureScrollState(container) {
  return {
    top: container.scrollTop,
    height: container.scrollHeight,
  };
}

function restoreScrollState(container, prev) {
  if (!prev || prev.top <= 0) return;
  const delta = container.scrollHeight - prev.height;
  container.scrollTop = Math.max(0, prev.top + delta);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toDate(value) {
  if (!value) return new Date(NaN);
  const d = new Date(value);
  return d;
}

function showToast(message) {
  const existing = document.querySelector(".kds-toast");
  if (existing) existing.remove();
  const toast = document.createElement("div");
  toast.className = "kds-toast";
  toast.textContent = message;
  toast.style.cssText = "position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#EF4444;color:#fff;padding:10px 20px;border-radius:8px;z-index:9999;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.12);";
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function sortByCreatedAt(rows) {
  return [...rows].sort((a, b) => toDate(a.created_at) - toDate(b.created_at));
}

function waitMinutes(createdAt) {
  const d = toDate(createdAt);
  if (Number.isNaN(d.getTime())) return 0;
  const diffMs = Date.now() - d.getTime();
  return Math.max(0, Math.floor(diffMs / 60000));
}

function waitLabel(minutes) {
  if (minutes < 60) return `${minutes} 分`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours} 小時 ${mins} 分`;
}

function waitLevel(status, minutes) {
  const rule = WAIT_RULES[status];
  if (!rule) return "";
  if (minutes >= rule.danger) return "danger";
  if (minutes >= rule.warn) return "warn";
  return "";
}

function addAlert(kind, title, detail) {
  state.alerts.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    kind,
    title,
    detail,
    createdAt: new Date().toISOString(),
  });
  state.alerts = state.alerts.slice(0, 50);
  renderAlerts();
}

function renderAlerts() {
  alertList.innerHTML = "";
  if (!state.alerts.length) {
    alertList.innerHTML = '<li class="empty">目前沒有事件</li>';
    return;
  }

  state.alerts.forEach((row) => {
    const item = document.createElement("li");
    item.className = `alert alert-kind-${row.kind}`;
    item.innerHTML = `
      <strong>${escapeHtml(row.title)}</strong>
      <div>${escapeHtml(row.detail)}</div>
      <div class="alert-time">${new Date(row.createdAt).toLocaleTimeString("zh-TW")}</div>
    `;
    alertList.appendChild(item);
  });
}

function renderLowStock() {
  lowStockList.innerHTML = "";
  if (!state.lowStock.length) {
    lowStockList.innerHTML = '<li class="empty">目前沒有低庫存項目</li>';
    return;
  }

  state.lowStock.forEach((row) => {
    const item = document.createElement("li");
    item.textContent = `${row.ingredient_name}：${row.current_stock} ${row.unit}（門檻 ${row.reorder_level}）`;
    lowStockList.appendChild(item);
  });
}

function updateLowStock(rows, notify = false) {
  if (!Array.isArray(rows)) return;
  state.lowStock = rows;
  renderLowStock();

  const signature = rows
    .map((row) => `${row.ingredient_name}:${row.current_stock}:${row.reorder_level}`)
    .join("|");
  if (notify && rows.length && signature !== lowStockSignature) {
    const preview = rows
      .slice(0, 3)
      .map((row) => `${row.ingredient_name}(${row.current_stock}${row.unit})`)
      .join("、");
    const suffix = rows.length > 3 ? ` 等 ${rows.length} 項` : "";
    addAlert("stock", "低庫存警示", `${preview}${suffix}`);
  }
  lowStockSignature = signature;
}

function summarizeDiff(diff) {
  if (!diff) return "內容已更新";
  const parts = [];
  if (Array.isArray(diff.added) && diff.added.length) {
    parts.push(`新增 ${diff.added.length} 項`);
  }
  if (Array.isArray(diff.removed) && diff.removed.length) {
    parts.push(`刪除 ${diff.removed.length} 項`);
  }
  if (Array.isArray(diff.quantity_changed) && diff.quantity_changed.length) {
    parts.push(`數量異動 ${diff.quantity_changed.length} 項`);
  }
  return parts.length ? parts.join(" / ") : "內容已更新";
}

function markAmended(orderId) {
  state.highlightedOrders.add(orderId);
  setTimeout(() => {
    state.highlightedOrders.delete(orderId);
    render(state.orders);
  }, 25000);
}

function render(orders) {
  const pendingState = captureScrollState(pendingCol);
  const preparingState = captureScrollState(preparingCol);
  const readyState = captureScrollState(readyCol);

  pendingCol.innerHTML = "";
  preparingCol.innerHTML = "";
  readyCol.innerHTML = "";

  const sorted = sortByCreatedAt(orders);
  const groups = {
    pending: [],
    preparing: [],
    ready: [],
  };
  sorted.forEach((order) => {
    if (groups[order.status]) groups[order.status].push(order);
  });

  pendingCount.textContent = String(groups.pending.length);
  preparingCount.textContent = String(groups.preparing.length);
  readyCount.textContent = String(groups.ready.length);

  renderLane(groups.pending, pendingCol, "pending");
  renderLane(groups.preparing, preparingCol, "preparing");
  renderLane(groups.ready, readyCol, "ready");

  restoreScrollState(pendingCol, pendingState);
  restoreScrollState(preparingCol, preparingState);
  restoreScrollState(readyCol, readyState);
}

function renderLane(rows, container, status) {
  if (!rows.length) {
    container.innerHTML = '<div class="empty">目前沒有訂單</div>';
    return;
  }

  rows.forEach((order) => {
    const wait = waitMinutes(order.created_at);
    const level = waitLevel(order.status, wait);
    const createdTime = toDate(order.created_at).toLocaleTimeString("zh-TW", {
      hour: "2-digit",
      minute: "2-digit",
    });
    const amendedClass = state.highlightedOrders.has(order.id) ? " amended" : "";

    const card = document.createElement("article");
    card.className = `order${amendedClass}`;
    card.dataset.status = order.status;
    card.dataset.createdAt = order.created_at;
    card.style.cursor = "pointer";
    card.innerHTML = `
      <div class="order-head">
        <div class="order-id">#${escapeHtml(order.order_number)}</div>
        <span class="timer ${level}">等待 ${waitLabel(wait)}</span>
      </div>
      <div class="meta-row">
        <span class="pill pill-source">來源：${escapeHtml(SOURCE_TEXT[order.source] || order.source)}</span>
        <span class="pill pill-payment">付款：${escapeHtml(PAYMENT_TEXT[order.payment_status] || order.payment_status)}</span>
        <span class="pill pill-created">建立：${createdTime}</span>
      </div>
      <ul class="item-list">
        ${order.items
          .map((item) => {
            const note = item.note ? `<span class="note-badge">備註：${escapeHtml(item.note)}</span>` : "";
            return `<li><strong>${escapeHtml(item.menu_item_name)}</strong> x${item.quantity}${note}</li>`;
          })
          .join("")}
      </ul>
      <div class="actions"></div>
    `;

    // 整張卡片可點擊切換狀態
    let primaryAction = null;
    if (status === "pending") {
      primaryAction = () => updateStatus(order.id, "preparing");
    } else if (status === "preparing") {
      primaryAction = () => updateStatus(order.id, "ready");
    } else if (status === "ready") {
      primaryAction = () => updateStatus(order.id, "completed");
    }

    if (primaryAction) {
      card.addEventListener("click", (e) => {
        // 如果點擊的是按鈕，讓按鈕處理
        if (e.target.tagName === "BUTTON") return;
        primaryAction();
      });
    }

    const actions = card.querySelector(".actions");
    if (status === "pending") {
      addAction(actions, "開始製作", () => updateStatus(order.id, "preparing"));
      addAction(actions, "取消訂單", () => updateStatus(order.id, "cancelled"), "btn-danger");
    } else if (status === "preparing") {
      addAction(actions, "製作完成", () => updateStatus(order.id, "ready"));
      addAction(actions, "取消訂單", () => updateStatus(order.id, "cancelled"), "btn-danger");
    } else if (status === "ready") {
      addAction(actions, "完成交餐", () => updateStatus(order.id, "completed"), "btn-secondary");
    }

    container.appendChild(card);
  });
}

function refreshTimers() {
  const cards = document.querySelectorAll(".order");
  cards.forEach((card) => {
    const status = card.dataset.status || "";
    const createdAt = card.dataset.createdAt || "";
    if (!status || !createdAt) return;
    const timer = card.querySelector(".timer");
    if (!timer) return;
    const minutes = waitMinutes(createdAt);
    const level = waitLevel(status, minutes);
    timer.className = `timer ${level}`.trim();
    timer.textContent = `等待 ${waitLabel(minutes)}`;
  });
}

function addAction(container, label, onClick, className = "") {
  const button = document.createElement("button");
  button.textContent = label;
  if (className) button.className = className;
  button.addEventListener("click", onClick);
  container.appendChild(button);
}

async function fetchOrders() {
  const res = await Auth.authFetch("/api/orders?limit=200");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
  const rows = await res.json();
  const active = rows.filter((order) => ["pending", "preparing", "ready"].includes(order.status));
  state.orders = active;
  render(active);
}

async function fetchLowStock() {
  const res = await Auth.authFetch("/api/inventory/low-stock");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
  const rows = await res.json();
  updateLowStock(rows, false);
}

async function updateStatus(orderId, status) {
  if (status === "cancelled") {
    const confirmed = window.confirm("確定要取消這張訂單嗎？");
    if (!confirmed) return;
  }

  const res = await Auth.authFetch(`/api/orders/${orderId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (res.status === 404) {
    await fetchOrders();
    showToast("訂單不存在或已被其他終端更新，已自動刷新看板");
    return;
  }
  if (!res.ok) {
    showToast(`更新失敗：${await Auth.readErrorMessage(res)}`);
    return;
  }
  await fetchOrders();
}

function handleSocketPayload(payload) {
  if (Array.isArray(payload.low_stock)) {
    updateLowStock(payload.low_stock, true);
  }

  if (!payload.event || payload.event === "connected") return;

  if (payload.event === "order_created") {
    addAlert("new", "新訂單", `#${payload.order_number} 已進入待處理`);
  } else if (payload.event === "order_amended") {
    addAlert("change", "訂單改單", `#${payload.order_number}：${summarizeDiff(payload.diff)}`);
    if (payload.order_id) markAmended(payload.order_id);
  } else if (payload.event === "order_status_changed") {
    const statusText = STATUS_TEXT[payload.status] || payload.status;
    const kind = payload.status === "cancelled" ? "cancel" : "new";
    addAlert(kind, "訂單狀態更新", `#${payload.order_number} -> ${statusText}`);
  } else if (payload.event === "order_paid") {
    addAlert("new", "付款完成", `#${payload.order_number} 已付款`);
  }

  debouncedFetchOrders();
}

let _fetchOrdersTimer = null;
function debouncedFetchOrders() {
  if (_fetchOrdersTimer) clearTimeout(_fetchOrdersTimer);
  _fetchOrdersTimer = setTimeout(() => {
    _fetchOrdersTimer = null;
    fetchOrders();
  }, 300);
}

function setupWebsocket() {
  Auth.connectEventSocket({
    onMessage: (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        handleSocketPayload(payload);
      } catch (_) {
        // Ignore malformed payload.
      }
    },
    onDisconnected: () => {
      connectionStatus.textContent = "即時連線中斷，嘗試重連中...";
      connectionStatus.className = "connection warn";
    },
    onConnected: () => {
      connectionStatus.textContent = "即時連線中";
      connectionStatus.className = "connection ok";
    },
  });
}

async function bootstrap() {
  await Auth.ensureAuth(["kitchen", "manager", "owner"]);
  await Promise.all([fetchOrders(), fetchLowStock()]);
  renderAlerts();
  refreshTimers();
  setupWebsocket();
  setInterval(fetchOrders, 30000);
  setInterval(refreshTimers, 15000);
}

bootstrap().catch((err) => {
  showToast(`初始化失敗：${String(err.message || err)}`);
});
