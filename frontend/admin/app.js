const ingredientBody = document.getElementById("ingredientBody");
const movementForm = document.getElementById("movementForm");
const movementMsg = document.getElementById("movementMsg");

const totalRevenue = document.getElementById("totalRevenue");
const totalOrders = document.getElementById("totalOrders");
const avgTicket = document.getElementById("avgTicket");
const inventoryValue = document.getElementById("inventoryValue");
const topItems = document.getElementById("topItems");
const lowStock = document.getElementById("lowStock");
const auditList = document.getElementById("auditList");
const shiftCurrent = document.getElementById("shiftCurrent");
const shiftOpenForm = document.getElementById("shiftOpenForm");
const shiftCloseForm = document.getElementById("shiftCloseForm");
const shiftMsg = document.getElementById("shiftMsg");
const shiftHistory = document.getElementById("shiftHistory");

const fmt = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 });

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMoney(value) {
  return fmt.format(Number(value || 0));
}

function calcScrollState(container) {
  return {
    top: container.scrollTop,
    height: container.scrollHeight,
    nearTop: container.scrollTop <= 24,
  };
}

function restoreScrollState(container, prev) {
  if (!prev || prev.nearTop) return;
  const delta = container.scrollHeight - prev.height;
  container.scrollTop = Math.max(0, prev.top + delta);
}

function renderListStable({ container, signature, rows, emptyText, renderRow }) {
  if (container.dataset.signature === signature) return;
  const scrollState = calcScrollState(container);

  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<li>${emptyText}</li>`;
    container.dataset.signature = signature;
    restoreScrollState(container, scrollState);
    return;
  }

  const fragment = document.createDocumentFragment();
  rows.forEach((row) => {
    fragment.appendChild(renderRow(row));
  });
  container.appendChild(fragment);
  container.dataset.signature = signature;
  restoreScrollState(container, scrollState);
}

async function fetchIngredients() {
  const res = await Auth.authFetch("/api/inventory/ingredients");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

  const rows = await res.json();
  ingredientBody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const lowFlag = row.current_stock <= row.reorder_level ? " (低庫存)" : "";
    tr.innerHTML = `
      <td>${escapeHtml(row.id)}</td>
      <td>${escapeHtml(row.name)}${lowFlag}</td>
      <td>${escapeHtml(row.unit)}</td>
      <td>${formatMoney(row.current_stock)}</td>
      <td>${formatMoney(row.reorder_level)}</td>
      <td>${formatMoney(row.cost_per_unit)}</td>
    `;
    ingredientBody.appendChild(tr);
  });
}

async function submitMovement(evt) {
  evt.preventDefault();
  movementMsg.textContent = "送出中...";

  try {
    const qtyVal = Number(document.getElementById("quantity").value);
    if (!Number.isFinite(qtyVal) || qtyVal <= 0) {
      movementMsg.textContent = "失敗：數量必須為正數";
      return;
    }

    const payload = {
      ingredient_id: Number(document.getElementById("ingredientId").value),
      movement_type: document.getElementById("movementType").value,
      quantity: qtyVal,
      unit_cost: document.getElementById("unitCost").value ? Number(document.getElementById("unitCost").value) : null,
      reference: document.getElementById("reference").value || null,
    };

    const res = await Auth.authFetch("/api/inventory/movements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      movementMsg.textContent = `失敗：${await Auth.readErrorMessage(res)}`;
      return;
    }

    movementMsg.textContent = "異動已送出";
    movementForm.reset();
    await Promise.all([fetchIngredients(), fetchOverview()]);
  } catch (err) {
    movementMsg.textContent = `失敗：${String(err.message || err)}`;
  }
}

async function fetchOverview() {
  const res = await Auth.authFetch("/api/analytics/overview");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
  const data = await res.json();

  totalRevenue.textContent = `$${formatMoney(data.total_revenue)}`;
  totalOrders.textContent = formatMoney(data.total_orders);
  avgTicket.textContent = `$${formatMoney(data.average_ticket)}`;
  inventoryValue.textContent = `$${formatMoney(data.inventory_value)}`;

  const topSignature = data.top_items
    .map((item) => `${item.menu_item_name}:${item.quantity}:${item.revenue}`)
    .join("|");
  renderListStable({
    container: topItems,
    signature: topSignature,
    rows: data.top_items,
    emptyText: "目前沒有資料",
    renderRow: (item) => {
      const li = document.createElement("li");
      li.textContent = `${item.menu_item_name}：${item.quantity} 份 / $${formatMoney(item.revenue)}`;
      return li;
    },
  });

  const lowStockSignature = data.low_stock
    .map((item) => `${item.ingredient_name}:${item.current_stock}:${item.reorder_level}`)
    .join("|");
  renderListStable({
    container: lowStock,
    signature: lowStockSignature,
    rows: data.low_stock,
    emptyText: "目前沒有低庫存項目",
    renderRow: (item) => {
      const li = document.createElement("li");
      li.textContent = `${item.ingredient_name}：${formatMoney(item.current_stock)} ${item.unit}（門檻 ${formatMoney(item.reorder_level)}）`;
      return li;
    },
  });
}

function formatAuditPayload(payload) {
  if (!payload || typeof payload !== "object") return "";
  const keys = Object.keys(payload).slice(0, 4);
  if (!keys.length) return "";
  return escapeHtml(keys.map((key) => `${key}: ${JSON.stringify(payload[key])}`).join(" | "));
}

function auditActionLabel(action) {
  return (
    {
      "auth.login": "登入系統",
      "user.create": "新增使用者",
      "order.create": "建立訂單",
      "order.pay": "訂單付款",
      "order.amend": "訂單改單",
      "order.status.change": "訂單狀態變更",
      "menu.create": "新增菜單項目",
      "menu.update": "更新菜單項目",
      "menu.recipe.replace": "更新配方",
      "inventory.ingredient.create": "新增原料",
      "inventory.ingredient.update": "更新原料",
      "inventory.movement.create": "新增庫存異動",
      "shift.open": "開啟班別",
      "shift.close": "關閉班別",
    }[action] || action
  );
}

function formatDateTime(value) {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "-";
  return dt.toLocaleString("zh-TW");
}

function renderShiftCurrent(row) {
  if (!row) {
    shiftCurrent.innerHTML = "<p>目前沒有開啟中的班別。</p>";
    shiftOpenForm.style.display = "grid";
    shiftCloseForm.style.display = "none";
    return;
  }
  const statusLabel = row.status === "open" ? "進行中" : "已關閉";
  shiftCurrent.innerHTML = `
    <article>
      <div><strong>${escapeHtml(row.shift_name)}</strong>（${statusLabel}）</div>
      <div>開班時間：${escapeHtml(formatDateTime(row.opened_at))}</div>
      <div>開班現金：$${formatMoney(row.opening_cash)}</div>
      <div>應有現金：$${formatMoney(row.expected_cash)}</div>
      <div>現金差額：${row.cash_difference == null ? "-" : `$${formatMoney(row.cash_difference)}`}</div>
      <div>營收：$${formatMoney(row.total_revenue)}（現金 $${formatMoney(row.cash_revenue)} / 非現金 $${formatMoney(row.non_cash_revenue)}）</div>
      <div>已付款筆數：${formatMoney(row.paid_order_count)}</div>
    </article>
  `;
  shiftOpenForm.style.display = "none";
  shiftCloseForm.style.display = row.status === "open" ? "grid" : "none";
}

async function fetchShiftCurrent() {
  const res = await Auth.authFetch("/api/shift/current");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
  renderShiftCurrent(await res.json());
}

async function fetchShiftHistory() {
  const res = await Auth.authFetch("/api/shift/history?limit=20");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
  const rows = await res.json();
  const signature = rows
    .map((row) => `${row.id}:${row.status}:${row.closed_at || row.opened_at || ""}`)
    .join("|");

  renderListStable({
    container: shiftHistory,
    signature,
    rows,
    emptyText: "目前沒有交班紀錄",
    renderRow: (row) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <div><strong>${escapeHtml(row.shift_name)}</strong>｜${row.status === "open" ? "進行中" : "已關班"}</div>
        <div>開班：${escapeHtml(formatDateTime(row.opened_at))} / 關班：${escapeHtml(formatDateTime(row.closed_at))}</div>
        <div>營收：$${formatMoney(row.total_revenue)}，差額：${row.cash_difference == null ? "-" : `$${formatMoney(row.cash_difference)}`}</div>
      `;
      return li;
    },
  });
}

async function submitShiftOpen(evt) {
  evt.preventDefault();
  shiftMsg.textContent = "開班中...";
  try {
    const payload = {
      shift_name: document.getElementById("shiftName").value.trim(),
      opening_cash: Number(document.getElementById("openingCash").value || 0),
      notes: document.getElementById("shiftOpenNote").value.trim() || null,
    };
    if (!payload.shift_name) {
      shiftMsg.textContent = "失敗：班別名稱必填";
      return;
    }
    const res = await Auth.authFetch("/api/shift/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      shiftMsg.textContent = `失敗：${await Auth.readErrorMessage(res)}`;
      return;
    }
    shiftMsg.textContent = "班別已開啟";
    await Promise.all([fetchShiftCurrent(), fetchShiftHistory(), fetchAuditLogs()]);
  } catch (err) {
    shiftMsg.textContent = `失敗：${String(err.message || err)}`;
  }
}

async function submitShiftClose(evt) {
  evt.preventDefault();
  shiftMsg.textContent = "關班對帳中...";
  try {
    const payload = {
      actual_cash: Number(document.getElementById("actualCash").value || 0),
      notes: document.getElementById("shiftCloseNote").value.trim() || null,
    };
    const res = await Auth.authFetch("/api/shift/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      shiftMsg.textContent = `失敗：${await Auth.readErrorMessage(res)}`;
      return;
    }
    shiftMsg.textContent = "關班完成";
    shiftCloseForm.reset();
    await Promise.all([fetchShiftCurrent(), fetchShiftHistory(), fetchAuditLogs()]);
  } catch (err) {
    shiftMsg.textContent = `失敗：${String(err.message || err)}`;
  }
}

async function fetchAuditLogs() {
  const res = await Auth.authFetch("/api/audit/logs?limit=40");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

  const rows = await res.json();
  const signature = rows
    .map((row) => `${row.id}:${row.action}:${row.entity_type}:${row.entity_id || ""}:${row.created_at}`)
    .join("|");

  renderListStable({
    container: auditList,
    signature,
    rows,
    emptyText: "目前沒有稽核紀錄",
    renderRow: (row) => {
      const li = document.createElement("li");
      const payloadText = formatAuditPayload(row.payload);
      li.innerHTML = `
        <div><strong>${escapeHtml(auditActionLabel(row.action))}</strong> | ${escapeHtml(row.entity_type)}${row.entity_id ? `#${escapeHtml(row.entity_id)}` : ""}</div>
        <div>${escapeHtml(row.actor_username || "系統")}（${escapeHtml(row.actor_role || "未知角色")}）</div>
        <div>${new Date(row.created_at).toLocaleString("zh-TW")}</div>
        ${payloadText ? `<small>${payloadText}</small>` : ""}
      `;
      return li;
    },
  });
}

movementForm.addEventListener("submit", submitMovement);
shiftOpenForm.addEventListener("submit", submitShiftOpen);
shiftCloseForm.addEventListener("submit", submitShiftClose);

function setupWebsocket() {
  Auth.connectEventSocket({
    onMessage: (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.event && payload.event !== "connected") {
          fetchIngredients();
          fetchOverview();
          fetchAuditLogs();
          fetchShiftCurrent();
          fetchShiftHistory();
        }
      } catch (_) {
        // Ignore malformed payload.
      }
    },
  });
}

async function bootstrap() {
  await Auth.ensureAuth(["manager", "owner"]);
  await Promise.all([
    fetchIngredients(),
    fetchOverview(),
    fetchAuditLogs(),
    fetchShiftCurrent(),
    fetchShiftHistory(),
  ]);
  setupWebsocket();
  setInterval(fetchOverview, 45000);
  setInterval(fetchAuditLogs, 30000);
  setInterval(fetchShiftCurrent, 30000);
  setInterval(fetchShiftHistory, 60000);
}

bootstrap().catch((err) => {
  movementMsg.textContent = `初始化失敗：${String(err.message || err)}`;
});
