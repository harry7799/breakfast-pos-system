const preparingList = document.getElementById("preparingList");
const readyList = document.getElementById("readyList");
const completedList = document.getElementById("completedList");
const countPreparing = document.getElementById("countPreparing");
const countReady = document.getElementById("countReady");
const countCompleted = document.getElementById("countCompleted");
const lastUpdated = document.getElementById("lastUpdated");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function shortOrderNo(orderNumber, fallbackId = 0) {
  const digits = String(orderNumber || "").replace(/\D/g, "");
  if (digits.length >= 3) return digits.slice(-3);
  const idNum = Number(fallbackId || 0);
  if (Number.isFinite(idNum) && idNum > 0) return String(idNum % 1000).padStart(3, "0");
  return String(orderNumber || "---");
}

function formatTime(value) {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "--:--";
  return dt.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
}

function applyDensityMode(counts) {
  const maxCount = Math.max(...counts);
  document.body.classList.remove("density-compact", "density-dense");
  if (maxCount >= 18) {
    document.body.classList.add("density-dense");
  } else if (maxCount >= 12) {
    document.body.classList.add("density-compact");
  }
}

function renderTickets(container, rows, emptyText) {
  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();
  rows.forEach((row) => {
    const card = document.createElement("article");
    card.className = "ticket";
    card.innerHTML = `
      <div class="no">#${escapeHtml(shortOrderNo(row.order_number, row.id))}</div>
      <div class="meta">${escapeHtml(row.source === "dine_in" ? "內用" : row.source === "delivery" ? "外送" : "外帶")}・${escapeHtml(formatTime(row.created_at))}</div>
    `;
    fragment.appendChild(card);
  });
  container.appendChild(fragment);
}

async function fetchPickupBoard() {
  const res = await fetch("/api/orders/pickup-board?minutes=180&limit=180");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const rows = await res.json();
  const preparing = rows.filter((row) => row.status === "preparing");
  const ready = rows.filter((row) => row.status === "ready");
  const completed = rows.filter((row) => row.status === "completed").slice(0, 30);

  countPreparing.textContent = String(preparing.length);
  countReady.textContent = String(ready.length);
  countCompleted.textContent = String(completed.length);
  applyDensityMode([preparing.length, ready.length, completed.length]);

  renderTickets(preparingList, preparing, "目前沒有製作中的號碼");
  renderTickets(readyList, ready, "目前沒有可取餐號碼");
  renderTickets(completedList, completed, "目前沒有剛完成的號碼");
  lastUpdated.textContent = `最後更新：${new Date().toLocaleTimeString("zh-TW")}`;
}

async function bootstrap() {
  await fetchPickupBoard();
  setInterval(fetchPickupBoard, 5000);
}

bootstrap().catch((err) => {
  const message = `看板初始化失敗：${String(err.message || err)}`;
  preparingList.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
  readyList.innerHTML = "";
  completedList.innerHTML = "";
});
