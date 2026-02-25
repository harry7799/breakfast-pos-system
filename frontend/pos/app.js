
const HOLD_STORAGE_KEY = "breakfast_pos_held_orders_v1";
const RECENT_ORDER_LIMIT = 50;

const state = {
  menu: [],
  menuById: new Map(),
  cart: [],
  comboCart: [],
  orders: [],
  combos: [],
  comboDrafts: {},
  selectedCategory: "ALL",
  selectedTab: "current",
  activeComboId: null,
  menuSearch: "",
  peakMode: false,
  heldOrders: loadHeldOrders(),
};

const STATUS_LABEL = {
  pending: "待處理",
  preparing: "製作中",
  ready: "可取餐",
  completed: "已完成",
  cancelled: "已取消",
};

const SOURCE_LABEL = {
  takeout: "外帶",
  dine_in: "內用",
  delivery: "外送",
};

const PAYMENT_LABEL = {
  unpaid: "未付款",
  paid: "已付款",
  refunded: "已退款",
};

const CATEGORY_LABEL = {
  ALL: "全部",
  DANBING: "蛋餅",
  NOODLE: "麵",
  STIR_FRY_NOODLE: "鍋炒麵",
  RICE: "飯",
  TURNIP_CAKE: "蘿蔔糕",
  SNACK: "小點",
  DRINK: "飲料",
  OTHER: "其他",
};

const CATEGORY_ORDER = ["DANBING", "NOODLE", "STIR_FRY_NOODLE", "RICE", "TURNIP_CAKE", "SNACK", "DRINK", "OTHER"];

const els = {
  menuGrid: document.getElementById("menuGrid"),
  menuCategoryBar: document.getElementById("menuCategoryBar"),
  comboQuickSection: document.getElementById("comboQuickSection"),
  cartList: document.getElementById("cartList"),
  total: document.getElementById("total"),
  message: document.getElementById("message"),
  submitOrderBtn: document.getElementById("submitOrderBtn"),
  clearOrderBtn: document.getElementById("clearOrderBtn"),
  orders: document.getElementById("orders"),
  sourceSelect: document.getElementById("sourceSelect"),
  paymentMethodSelect: document.getElementById("paymentMethodSelect"),
  menuSearch: document.getElementById("menuSearch"),
  orderTabs: document.getElementById("orderTabs"),
  tabCurrent: document.getElementById("tabCurrent"),
  tabHeld: document.getElementById("tabHeld"),
  tabRecent: document.getElementById("tabRecent"),
  heldOrders: document.getElementById("heldOrders"),
  currentCount: document.getElementById("currentCount"),
  heldCount: document.getElementById("heldCount"),
  recentCount: document.getElementById("recentCount"),
  newOrderBtn: document.getElementById("newOrderBtn"),
  holdOrderBtn: document.getElementById("holdOrderBtn"),
  peakModeToggle: document.getElementById("peakModeToggle"),
  bizTime: document.getElementById("bizTime"),
  comboModal: document.getElementById("comboModal"),
  comboModalBody: document.getElementById("comboModalBody"),
  comboModalCloseBtn: document.getElementById("comboModalClose"),
  comboModalCancelBtn: document.getElementById("comboModalCancel"),
  comboModalConfirmBtn: document.getElementById("comboModalConfirm"),
};

const currency = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 });
const datetimeFormatter = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function loadHeldOrders() {
  try {
    const raw = localStorage.getItem(HOLD_STORAGE_KEY);
    if (!raw) return [];
    const rows = JSON.parse(raw);
    if (!Array.isArray(rows)) return [];
    return rows.slice(0, 100);
  } catch (_err) {
    return [];
  }
}

function persistHeldOrders() {
  localStorage.setItem(HOLD_STORAGE_KEY, JSON.stringify(state.heldOrders.slice(0, 100)));
}

function escapeHtml(value) {
  const text = String(value ?? "");
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeLookup(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\u4e00-\u9fa5a-z0-9]/gi, "");
}

function formatMoney(value) {
  return currency.format(Number(value || 0));
}

function shortOrderNo(orderNumber, fallbackId = 0) {
  const digits = String(orderNumber || "").replace(/\D/g, "");
  if (digits.length >= 3) return digits.slice(-3);
  const idNum = Number(fallbackId || 0);
  if (Number.isFinite(idNum) && idNum > 0) return String(idNum % 1000).padStart(3, "0");
  return String(orderNumber || "---");
}

function orderTag(order) {
  return `#${shortOrderNo(order?.order_number, order?.id)}`;
}

function formatTaipeiTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return `${datetimeFormatter.format(parsed)} (UTC+8)`;
}

function setMessage(text, type = "info") {
  if (!els.message) return;
  els.message.textContent = String(text || "");
  els.message.className = "message";
  if (type === "success") els.message.classList.add("success");
  if (type === "error") els.message.classList.add("error");
}

function setClock() {
  if (!els.bizTime) return;
  const now = new Date();
  const t = now.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" });
  els.bizTime.textContent = `台灣時間 ${t}`;
}

function byId(id) {
  return state.menuById.get(id) || null;
}

function comboById(id) {
  return state.combos.find((combo) => combo.id === id) || null;
}
function detectCategory(name) {
  const text = String(name || "");
  if (!text) return "OTHER";
  if (/(紅茶|奶茶|豆漿|咖啡|鮮奶|果汁|茶|飲|冰|熱|中杯|大杯|杯|冬瓜|拿鐵)/.test(text)) return "DRINK";
  if (/(蛋餅|抓餅|蔥抓餅)/.test(text)) return "DANBING";
  if (/(鍋炒|炒麵|炒烏龍|炒意麵)/.test(text)) return "STIR_FRY_NOODLE";
  if (/(麵|意麵|烏龍|冬粉|米粉|湯麵|乾麵|板條)/.test(text)) return "NOODLE";
  if (/(飯|燴飯|便當|丼|炒飯)/.test(text)) return "RICE";
  if (/(蘿蔔糕)/.test(text)) return "TURNIP_CAKE";
  if (/(薯|雞塊|炸|熱狗|點心|小點|沙拉|捲|吐司|三明治|漢堡)/.test(text)) return "SNACK";
  return "OTHER";
}

function normalizeMenuItem(item) {
  const rawName = String(item.name || "").trim();
  let displayName = rawName;
  let taggedCategory = null;

  const bracketTag = rawName.match(/^\[([A-Z_]+)\]\s*(.+)$/);
  if (bracketTag) {
    taggedCategory = bracketTag[1].trim();
    displayName = bracketTag[2].trim();
  }

  const mappedCategory = CATEGORY_LABEL[taggedCategory] ? taggedCategory : detectCategory(displayName);
  return {
    ...item,
    display_name: displayName || rawName,
    category: mappedCategory,
  };
}

function sortMenu(items) {
  return [...items].sort((a, b) => {
    const aCat = CATEGORY_ORDER.indexOf(a.category);
    const bCat = CATEGORY_ORDER.indexOf(b.category);
    if (aCat !== bCat) return aCat - bCat;
    return String(a.display_name).localeCompare(String(b.display_name), "zh-Hant");
  });
}

function getCategoryStats() {
  const stats = new Map();
  state.menu.forEach((item) => {
    stats.set(item.category, (stats.get(item.category) || 0) + 1);
  });
  return stats;
}

function renderCategoryBar() {
  if (!els.menuCategoryBar) return;
  const stats = getCategoryStats();
  const categories = CATEGORY_ORDER.filter((key) => stats.has(key));
  const chips = [{ key: "ALL", count: state.menu.length }, ...categories.map((key) => ({ key, count: stats.get(key) }))];

  els.menuCategoryBar.innerHTML = "";
  chips.forEach((chip) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `category-chip${state.selectedCategory === chip.key ? " active" : ""}`;
    button.textContent = `${CATEGORY_LABEL[chip.key] || chip.key} (${chip.count})`;
    button.addEventListener("click", () => {
      state.selectedCategory = chip.key;
      renderCategoryBar();
      renderMenu();
    });
    els.menuCategoryBar.appendChild(button);
  });
}

function getFilteredMenu() {
  const keyword = normalizeLookup(state.menuSearch);
  const listByCategory = state.selectedCategory === "ALL"
    ? state.menu
    : state.menu.filter((item) => item.category === state.selectedCategory);

  if (!keyword) return listByCategory;
  return listByCategory.filter((item) => normalizeLookup(item.display_name).includes(keyword));
}

function renderMenu() {
  if (!els.menuGrid) return;
  const rows = getFilteredMenu();
  els.menuGrid.innerHTML = "";

  if (!state.menu.length) {
    els.menuGrid.innerHTML = '<div class="menu-empty">尚未載入任何菜單項目</div>';
    return;
  }

  if (!rows.length) {
    els.menuGrid.innerHTML = '<div class="menu-empty">找不到符合條件的品項</div>';
    return;
  }

  rows.forEach((item) => {
    const card = document.createElement("article");
    card.className = "menu-item";
    card.style.cursor = "pointer";
    card.innerHTML = `
      <span class="menu-item-category">${escapeHtml(CATEGORY_LABEL[item.category] || "其他")}</span>
      <strong class="menu-item-name">${escapeHtml(item.display_name)}</strong>
      <div class="menu-item-price">$${formatMoney(item.price)}</div>
      <button data-id="${item.id}" type="button">+1 加入</button>
    `;
    // 整張卡片可點擊
    card.addEventListener("click", (e) => {
      // 如果點擊的是按鈕本身，讓按鈕處理
      if (e.target.tagName === "BUTTON") return;
      addToCart(item.id);
    });
    card.querySelector("button")?.addEventListener("click", (e) => {
      e.stopPropagation(); // 防止觸發卡片的點擊事件
      addToCart(item.id);
    });
    els.menuGrid.appendChild(card);
  });
}

function ensureComboDraft(combo) {
  const key = String(combo.id);
  if (!state.comboDrafts[key]) {
    state.comboDrafts[key] = {
      drink_item_ids: [],
      side_codes: [],
    };
  }
  const draft = state.comboDrafts[key];
  if (!Array.isArray(draft.drink_item_ids)) draft.drink_item_ids = [];
  if (!Array.isArray(draft.side_codes)) draft.side_codes = [];

  const neededDrinkSlots = Number(combo.drink_choice_count || 0);
  while (draft.drink_item_ids.length < neededDrinkSlots) {
    draft.drink_item_ids.push(combo.eligible_drinks[draft.drink_item_ids.length]?.menu_item_id || "");
  }
  draft.drink_item_ids = draft.drink_item_ids.slice(0, neededDrinkSlots);
  return draft;
}

function findMenuItemForSideOption(sideName) {
  const target = normalizeLookup(sideName);
  if (!target) return null;

  const candidates = state.menu
    .map((item) => {
      const normalized = normalizeLookup(item.display_name);
      if (!normalized) return null;
      if (!normalized.includes(target) && !target.includes(normalized)) return null;
      let score = 0;
      if (item.category === "FRIED") score += 80;
      score -= Math.abs(normalized.length - target.length);
      return { item, score };
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score);

  return candidates.length ? candidates[0].item : null;
}

function applyCombo(combo) {
  const draft = ensureComboDraft(combo);
  const chosenDrinkIds = draft.drink_item_ids
    .map((id) => Number(id))
    .filter((id) => Number.isFinite(id) && id > 0);

  if (chosenDrinkIds.length < combo.drink_choice_count) {
    setMessage(`請先選滿 ${combo.drink_choice_count} 杯飲料`, "error");
    return false;
  }

  const selectedSideCodes = [...draft.side_codes];
  if (selectedSideCodes.length < combo.side_choice_count) {
    setMessage(`請先選滿 ${combo.side_choice_count} 個附餐`, "error");
    return false;
  }

  const mappedSideIds = [];
  const unresolved = [];

  selectedSideCodes.forEach((code) => {
    const option = combo.side_options.find((side) => side.code === code);
    if (!option) return;
    const mapped = findMenuItemForSideOption(option.name);
    if (!mapped) {
      unresolved.push(option.name);
      return;
    }
    mappedSideIds.push(mapped.id);
  });

  if (unresolved.length) {
    setMessage(`以下附餐找不到對應品項：${unresolved.join("、")}`, "error");
    return false;
  }

  state.comboCart.push({
    key: `${combo.id}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    combo_id: combo.id,
    combo_name: combo.name,
    bundle_price: Number(combo.bundle_price || 0),
    drink_item_ids: [...chosenDrinkIds],
    side_item_ids: [...mappedSideIds],
  });

  setMessage(`已加入套餐：${combo.name}`, "success");
  renderCart();
  return true;
}
function renderComboQuick() {
  if (!els.comboQuickSection) return;
  els.comboQuickSection.innerHTML = "";

  if (!state.combos.length) {
    return;
  }

  state.combos.forEach((combo) => {
    const card = document.createElement("article");
    card.className = "combo-card";
    card.innerHTML = `
      <div class="combo-title-row">
        <h3>${escapeHtml(combo.name)}</h3>
        <span class="combo-price">$${formatMoney(combo.bundle_price)}</span>
      </div>
      <div class="combo-meta">
        <span>飲料 ${combo.drink_choice_count} 選</span>
        <span>附餐 ${combo.side_choice_count} 選</span>
      </div>
      <button class="combo-trigger-btn" type="button">展開套餐</button>
    `;

    const open = () => openComboModal(combo.id);
    card.querySelector(".combo-trigger-btn")?.addEventListener("click", open);
    card.addEventListener("dblclick", open);
    els.comboQuickSection.appendChild(card);
  });
}

function renderComboModalContent(combo) {
  if (!els.comboModalBody) return;
  const draft = ensureComboDraft(combo);
  els.comboModalBody.innerHTML = "";

  const summary = document.createElement("div");
  summary.className = "combo-card";
  summary.innerHTML = `
    <div class="combo-title-row">
      <h3>${escapeHtml(combo.name)}</h3>
      <span class="combo-price">$${formatMoney(combo.bundle_price)}</span>
    </div>
    <div class="combo-meta">
      <span>飲料 ${combo.drink_choice_count} 選</span>
      <span>附餐 ${combo.side_choice_count} 選</span>
    </div>
  `;
  els.comboModalBody.appendChild(summary);

  if (combo.drink_choice_count > 0) {
    const drinkWrap = document.createElement("div");
    drinkWrap.className = "combo-control-block";

    const title = document.createElement("p");
    title.className = "combo-control-title";
    title.textContent = `飲料選擇（${combo.drink_choice_count}）`;
    drinkWrap.appendChild(title);

    for (let i = 0; i < combo.drink_choice_count; i += 1) {
      const select = document.createElement("select");
      select.className = "combo-select";

      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = `請選擇飲料 ${i + 1}`;
      select.appendChild(placeholder);

      combo.eligible_drinks.forEach((drink) => {
        const option = document.createElement("option");
        option.value = String(drink.menu_item_id);
        option.textContent = drink.menu_item_name;
        select.appendChild(option);
      });

      select.value = draft.drink_item_ids[i] ? String(draft.drink_item_ids[i]) : "";
      select.addEventListener("change", (evt) => {
        draft.drink_item_ids[i] = evt.target.value ? Number(evt.target.value) : "";
      });

      drinkWrap.appendChild(select);
    }

    els.comboModalBody.appendChild(drinkWrap);
  }

  if (combo.side_choice_count > 0) {
    const sideWrap = document.createElement("div");
    sideWrap.className = "combo-control-block";

    const title = document.createElement("p");
    title.className = "combo-control-title";
    title.textContent = `附餐選擇（${combo.side_choice_count}）`;
    sideWrap.appendChild(title);

    combo.side_options.forEach((option) => {
      const mapped = findMenuItemForSideOption(option.name);

      const row = document.createElement("label");
      row.className = "combo-side-row";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = option.code;
      checkbox.checked = draft.side_codes.includes(option.code);
      checkbox.addEventListener("change", (evt) => {
        if (evt.target.checked) {
          if (draft.side_codes.length >= combo.side_choice_count) {
            evt.target.checked = false;
            setMessage(`${combo.name} 最多可選 ${combo.side_choice_count} 個附餐`, "error");
            return;
          }
          draft.side_codes.push(option.code);
        } else {
          draft.side_codes = draft.side_codes.filter((code) => code !== option.code);
        }
      });

      const text = document.createElement("span");
      text.className = "combo-side-text";
      if (mapped) {
        text.textContent = `${option.code}. ${option.name} -> ${mapped.display_name}`;
      } else {
        text.textContent = `${option.code}. ${option.name}（找不到菜單對應）`;
        row.classList.add("unmapped");
      }

      row.appendChild(checkbox);
      row.appendChild(text);
      sideWrap.appendChild(row);
    });

    els.comboModalBody.appendChild(sideWrap);
  }
}

function openComboModal(comboId) {
  const combo = comboById(comboId);
  if (!combo || !els.comboModal) return;

  state.activeComboId = comboId;
  renderComboModalContent(combo);
  els.comboModal.classList.add("open");
  els.comboModal.setAttribute("aria-hidden", "false");
}

function closeComboModal() {
  if (!els.comboModal || !els.comboModalBody) return;

  state.activeComboId = null;
  els.comboModal.classList.remove("open");
  els.comboModal.setAttribute("aria-hidden", "true");
  els.comboModalBody.innerHTML = "";
}

function confirmComboModal() {
  if (!state.activeComboId) return;

  const combo = comboById(state.activeComboId);
  if (!combo) return;

  const ok = applyCombo(combo);
  if (ok) closeComboModal();
}

function addToCart(menuItemId, options = {}) {
  const render = options.render !== false;
  const existing = state.cart.find((line) => line.menu_item_id === menuItemId);
  if (existing) {
    existing.quantity += 1;
  } else {
    state.cart.push({ menu_item_id: menuItemId, quantity: 1 });
  }

  if (render) renderCart();
}

function updateQty(menuItemId, delta) {
  const line = state.cart.find((row) => row.menu_item_id === menuItemId);
  if (!line) return;

  line.quantity += delta;
  if (line.quantity <= 0) {
    state.cart = state.cart.filter((row) => row.menu_item_id !== menuItemId);
  }

  renderCart();
}

function removeComboFromCart(comboKey) {
  state.comboCart = state.comboCart.filter((line) => line.key !== comboKey);
  renderCart();
}
function calcCartTotal() {
  let total = 0;
  state.cart.forEach((line) => {
    const item = byId(line.menu_item_id);
    if (!item) return;
    total += Number(item.price || 0) * Number(line.quantity || 0);
  });
  state.comboCart.forEach((line) => {
    total += Number(line.bundle_price || 0);
  });
  return total;
}

function updateTabCounters() {
  if (els.currentCount) {
    const qty = state.cart.reduce((sum, row) => sum + Number(row.quantity || 0), 0) + state.comboCart.length;
    els.currentCount.textContent = String(qty);
  }
  if (els.heldCount) els.heldCount.textContent = String(state.heldOrders.length);
  if (els.recentCount) els.recentCount.textContent = String(state.orders.length);
}

function renderCart() {
  if (!els.cartList || !els.total || !els.submitOrderBtn) return;

  els.cartList.innerHTML = "";

  if (!state.cart.length && !state.comboCart.length) {
    els.cartList.innerHTML = '<li class="cart-empty">購物車目前是空的，請先加入品項。</li>';
  }

  state.cart.forEach((line) => {
    const item = byId(line.menu_item_id);
    if (!item) return;

    const lineTotal = Number(item.price || 0) * Number(line.quantity || 0);

    const li = document.createElement("li");
    li.className = "cart-line";
    li.innerHTML = `
      <div class="cart-line-main">
        <strong class="cart-line-name">${escapeHtml(item.display_name || item.name)}</strong>
        <span class="cart-line-total">$${formatMoney(lineTotal)}</span>
      </div>
      <div class="cart-line-sub">
        <span class="cart-line-qty">數量 x${line.quantity}</span>
        <div class="cart-line-actions">
          <button data-op="plus" type="button" aria-label="增加數量">+1</button>
          <button data-op="minus" type="button" aria-label="減少數量">-1</button>
        </div>
      </div>
    `;

    li.querySelector('[data-op="plus"]')?.addEventListener("click", () => updateQty(line.menu_item_id, 1));
    li.querySelector('[data-op="minus"]')?.addEventListener("click", () => updateQty(line.menu_item_id, -1));
    els.cartList.appendChild(li);
  });

  state.comboCart.forEach((line) => {
    const drinkNames = line.drink_item_ids
      .map((itemId) => byId(itemId)?.display_name || byId(itemId)?.name || `#${itemId}`)
      .join(" / ");
    const sideNames = line.side_item_ids
      .map((itemId) => byId(itemId)?.display_name || byId(itemId)?.name || `#${itemId}`)
      .join(" / ");
    const detail = [drinkNames, sideNames].filter(Boolean).join(" + ");

    const li = document.createElement("li");
    li.className = "cart-line";
    li.innerHTML = `
      <div class="cart-line-main">
        <strong class="cart-line-name">${escapeHtml(line.combo_name)}（套餐）</strong>
        <span class="cart-line-total">$${formatMoney(line.bundle_price)}</span>
      </div>
      <div class="cart-line-sub">
        <span class="cart-line-qty">${escapeHtml(detail || "套餐內容")}</span>
        <div class="cart-line-actions">
          <button data-op="remove-combo" type="button" aria-label="移除套餐">刪除</button>
        </div>
      </div>
    `;

    li.querySelector('[data-op="remove-combo"]')?.addEventListener("click", () => removeComboFromCart(line.key));
    els.cartList.appendChild(li);
  });

  els.total.textContent = formatMoney(calcCartTotal());
  els.submitOrderBtn.disabled = state.cart.length === 0 && state.comboCart.length === 0;
  updateTabCounters();
}

function summarizeOrderItems(items, maxShown = 3) {
  if (!Array.isArray(items) || !items.length) return "無品項";
  const shown = items.slice(0, maxShown).map((item) => {
    const note = item.note ? ` (${item.note})` : "";
    return `${item.menu_item_name} x${item.quantity}${note}`;
  });
  const hidden = items.length - shown.length;
  if (hidden > 0) return `${shown.join(" / ")} +${hidden} 項`;
  return shown.join(" / ");
}

function refillFromOrder(order) {
  if (!order || !Array.isArray(order.items)) return;

  state.cart = [];
  state.comboCart = [];

  order.items.forEach((item) => {
    const inMenu = byId(item.menu_item_id);
    if (!inMenu) return;
    state.cart.push({ menu_item_id: item.menu_item_id, quantity: Number(item.quantity || 1) });
  });

  if (state.cart.length === 0) {
    setMessage("此訂單品項不在目前菜單，無法復單", "error");
    return;
  }

  if (els.sourceSelect) els.sourceSelect.value = order.source || "takeout";
  switchTab("current");
  renderCart();
  setMessage(`已復單：${orderTag(order)}`, "success");
}

function renderRecentOrders() {
  if (!els.orders) return;
  els.orders.innerHTML = "";

  if (!state.orders.length) {
    els.orders.innerHTML = '<div class="orders-empty">目前沒有近期訂單</div>';
    updateTabCounters();
    return;
  }

  state.orders.slice(0, RECENT_ORDER_LIMIT).forEach((order) => {
    const itemsText = summarizeOrderItems(order.items, 3);
    const itemCount = Array.isArray(order.items)
      ? order.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0)
      : 0;

    const card = document.createElement("article");
    card.className = "order-card";
    card.innerHTML = `
      <div class="order-head">
        <h3 class="order-number">${escapeHtml(orderTag(order))}</h3>
        <div class="badge">${escapeHtml(STATUS_LABEL[order.status] || order.status)}</div>
      </div>
      <div class="order-meta">
        <span>來源 ${escapeHtml(SOURCE_LABEL[order.source] || order.source)}</span>
        <span>付款 ${escapeHtml(PAYMENT_LABEL[order.payment_status] || order.payment_status)}</span>
        <span>品項 ${itemCount}</span>
        <span>總額 $${formatMoney(order.total_amount)}</span>
      </div>
      <div class="order-items">${escapeHtml(itemsText)}</div>
      <div class="order-items">時間 ${formatTaipeiTime(order.created_at)}</div>
      <div class="order-actions"></div>
    `;

    const actionWrap = card.querySelector(".order-actions");

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.textContent = "一鍵復單";
    copyBtn.addEventListener("click", () => refillFromOrder(order));
    actionWrap?.appendChild(copyBtn);

    const amendBtn = document.createElement("button");
    amendBtn.type = "button";
    amendBtn.textContent = "改單";
    if (state.comboCart.length > 0) {
      amendBtn.title = "購物車含套餐時無法改單";
    } else if (state.cart.length === 0) {
      amendBtn.title = "會先載入此訂單，調整後再按一次改單";
    }
    amendBtn.addEventListener("click", () => beginAmendOrder(order));
    actionWrap?.appendChild(amendBtn);

    els.orders.appendChild(card);
  });

  updateTabCounters();
}
function renderHeldOrders() {
  if (!els.heldOrders) return;
  els.heldOrders.innerHTML = "";

  if (!state.heldOrders.length) {
    els.heldOrders.innerHTML = '<div class="held-empty">目前沒有掛單</div>';
    updateTabCounters();
    return;
  }

  state.heldOrders.forEach((hold) => {
    const card = document.createElement("article");
    card.className = "held-card";
    card.innerHTML = `
      <div class="held-head">
        <strong>${escapeHtml(hold.label)}</strong>
        <span class="badge">$${formatMoney(hold.total_amount)}</span>
      </div>
      <div class="held-meta">${escapeHtml(hold.meta || "")}</div>
      <div class="held-meta">${formatTaipeiTime(hold.created_at)}</div>
      <div class="held-actions">
        <button type="button" data-op="resume">取回</button>
        <button type="button" data-op="remove" class="danger">刪除</button>
      </div>
    `;

    card.querySelector('[data-op="resume"]')?.addEventListener("click", () => resumeHeldOrder(hold.id));
    card.querySelector('[data-op="remove"]')?.addEventListener("click", () => removeHeldOrder(hold.id));
    els.heldOrders.appendChild(card);
  });

  updateTabCounters();
}

function beginAmendOrder(order) {
  if (!order) return;
  const amendable = ["pending", "preparing", "ready"].includes(order.status);
  if (!amendable) {
    setMessage(`訂單 ${orderTag(order)} 目前狀態不可改單，請用一鍵復單開新單`, "error");
    return;
  }

  if (state.comboCart.length > 0) {
    setMessage("目前購物車含套餐，請先清空套餐再改單", "error");
    return;
  }

  if (state.cart.length === 0) {
    refillFromOrder(order);
    setMessage(`已載入 ${orderTag(order)}，請調整後再按改單`, "success");
    return;
  }

  amendOrder(order.id, orderTag(order));
}

function buildCartItemsPayload() {
  return state.cart.map((line) => ({
    menu_item_id: line.menu_item_id,
    quantity: line.quantity,
  }));
}

function buildComboPayload() {
  return state.comboCart.map((line) => ({
    combo_id: line.combo_id,
    quantity: 1,
    drink_item_ids: [...line.drink_item_ids],
    side_item_ids: [...line.side_item_ids],
  }));
}

function clearCurrentOrder() {
  state.cart = [];
  state.comboCart = [];
  renderCart();
  setMessage("已清空目前訂單");
}

function createHoldSnapshot() {
  const totalAmount = calcCartTotal();
  const source = els.sourceSelect?.value || "takeout";
  const paymentMethod = els.paymentMethodSelect?.value || "cash";
  const now = new Date();
  const tag = now.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" });

  return {
    id: `H${Date.now()}${Math.random().toString(16).slice(2, 6)}`,
    label: `掛單 ${tag}`,
    meta: `${SOURCE_LABEL[source] || source} / ${state.cart.length + state.comboCart.length} 項`,
    source,
    payment_method: paymentMethod,
    total_amount: totalAmount,
    cart: JSON.parse(JSON.stringify(state.cart)),
    combo_cart: JSON.parse(JSON.stringify(state.comboCart)),
    created_at: now.toISOString(),
  };
}

function holdCurrentOrder() {
  if (!state.cart.length && !state.comboCart.length) {
    setMessage("目前訂單是空的，無法掛單", "error");
    return;
  }

  const snapshot = createHoldSnapshot();
  state.heldOrders.unshift(snapshot);
  state.heldOrders = state.heldOrders.slice(0, 50);
  persistHeldOrders();

  clearCurrentOrder();
  renderHeldOrders();
  switchTab("held");
  setMessage(`已掛單：${snapshot.label}`, "success");
}

function resumeHeldOrder(holdId) {
  const idx = state.heldOrders.findIndex((row) => row.id === holdId);
  if (idx < 0) return;

  const row = state.heldOrders[idx];
  state.cart = Array.isArray(row.cart) ? row.cart : [];
  state.comboCart = Array.isArray(row.combo_cart) ? row.combo_cart : [];

  if (els.sourceSelect) els.sourceSelect.value = row.source || "takeout";
  if (els.paymentMethodSelect) els.paymentMethodSelect.value = row.payment_method || "cash";

  state.heldOrders.splice(idx, 1);
  persistHeldOrders();

  renderCart();
  renderHeldOrders();
  switchTab("current");
  setMessage(`已取回掛單：${row.label}`, "success");
}

function removeHeldOrder(holdId) {
  state.heldOrders = state.heldOrders.filter((row) => row.id !== holdId);
  persistHeldOrders();
  renderHeldOrders();
  setMessage("已刪除掛單");
}

function switchTab(tab) {
  state.selectedTab = tab;

  const tabButtons = Array.from(els.orderTabs?.querySelectorAll(".tab-btn") || []);
  tabButtons.forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });

  const panels = [
    [els.tabCurrent, "current"],
    [els.tabHeld, "held"],
    [els.tabRecent, "recent"],
  ];

  panels.forEach(([panel, key]) => {
    if (!panel) return;
    const active = key === tab;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });

  if (tab === "recent") {
    fetchRecentOrders().catch((err) => setMessage(`載入訂單失敗：${String(err.message || err)}`, "error"));
  }
}

function togglePeakMode() {
  state.peakMode = !state.peakMode;
  document.body.classList.toggle("peak-mode", state.peakMode);
  if (els.peakModeToggle) {
    els.peakModeToggle.textContent = `尖峰模式：${state.peakMode ? "開" : "關"}`;
  }
  if (state.peakMode && state.selectedTab === "recent") {
    switchTab("current");
  }
}

function summarizeDiff(diff) {
  if (!diff) return "無變更";
  const parts = [];
  if (Array.isArray(diff.added) && diff.added.length) parts.push(`新增 ${diff.added.length} 項`);
  if (Array.isArray(diff.removed) && diff.removed.length) parts.push(`移除 ${diff.removed.length} 項`);
  if (Array.isArray(diff.quantity_changed) && diff.quantity_changed.length) parts.push(`數量調整 ${diff.quantity_changed.length} 項`);
  return parts.length ? parts.join(" / ") : "無變更";
}
async function fetchMenu() {
  const res = await Auth.authFetch("/api/menu/items");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

  const rows = await res.json();
  state.menu = sortMenu(rows.map(normalizeMenuItem));
  state.menuById = new Map(state.menu.map((item) => [item.id, item]));

  renderCategoryBar();
  renderMenu();
}

async function fetchCombos() {
  const res = await Auth.authFetch("/api/menu/combos");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

  state.combos = await res.json();
  renderComboQuick();
}

async function fetchRecentOrders() {
  const res = await Auth.authFetch("/api/orders?limit=50");
  if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

  state.orders = await res.json();
  renderRecentOrders();
}

async function submitOrder() {
  if (!state.cart.length && !state.comboCart.length) return;
  if (!els.submitOrderBtn) return;

  setMessage("出單中...");
  els.submitOrderBtn.disabled = true;

  try {
    const payload = {
      source: els.sourceSelect?.value || "takeout",
      auto_pay: true,
      payment_method: els.paymentMethodSelect?.value || "cash",
      items: buildCartItemsPayload(),
      combos: buildComboPayload(),
    };

    const res = await Auth.authFetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(await Auth.readErrorMessage(res));

    const data = await res.json();
    state.cart = [];
    state.comboCart = [];
    renderCart();
    await fetchRecentOrders();
    setMessage(`出單成功：#${shortOrderNo(data.order_number, data.id)}`, "success");
  } catch (err) {
    setMessage(`出單失敗：${String(err.message || err)}`, "error");
  } finally {
    els.submitOrderBtn.disabled = state.cart.length === 0 && state.comboCart.length === 0;
  }
}

async function amendOrder(orderId, orderNumber) {
  if (state.comboCart.length) {
    setMessage("目前購物車含套餐，請先清空套餐再改單", "error");
    return;
  }

  if (!state.cart.length) {
    setMessage("購物車是空的，請先加入要修改的品項", "error");
    return;
  }

  setMessage(`修改訂單 ${orderNumber} 中...`);

  try {
    const res = await Auth.authFetch(`/api/orders/${orderId}/amend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: buildCartItemsPayload() }),
    });

    if (!res.ok) throw new Error(await Auth.readErrorMessage(res));
    const payload = await res.json();
    setMessage(`改單完成：${orderNumber}（${summarizeDiff(payload.diff)}）`, "success");
    await fetchRecentOrders();
  } catch (err) {
    setMessage(`改單失敗：${String(err.message || err)}`, "error");
  }
}

function setupWebsocket() {
  Auth.connectEventSocket({
    onMessage: (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.event && payload.event !== "connected") {
          fetchRecentOrders().catch(() => {});
        }
      } catch (_err) {
        // ignore malformed payload
      }
    },
    onDisconnected: () => {
      setMessage("即時連線中斷，系統會自動重連", "error");
    },
    onConnected: () => {
      if (els.message?.textContent?.includes("即時連線中斷")) setMessage("");
    },
  });
}

function setupComboModalEvents() {
  if (!els.comboModal) return;

  els.comboModalCloseBtn?.addEventListener("click", closeComboModal);
  els.comboModalCancelBtn?.addEventListener("click", closeComboModal);
  els.comboModalConfirmBtn?.addEventListener("click", confirmComboModal);

  els.comboModal.addEventListener("click", (evt) => {
    const target = evt.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.dataset.closeComboModal === "1") closeComboModal();
  });

  document.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && els.comboModal?.classList.contains("open")) {
      closeComboModal();
    }
  });
}

function setupEvents() {
  els.menuSearch?.addEventListener("input", (evt) => {
    state.menuSearch = String(evt.target.value || "");
    renderMenu();
  });

  els.submitOrderBtn?.addEventListener("click", submitOrder);
  els.clearOrderBtn?.addEventListener("click", clearCurrentOrder);
  els.newOrderBtn?.addEventListener("click", clearCurrentOrder);
  els.holdOrderBtn?.addEventListener("click", holdCurrentOrder);
  els.peakModeToggle?.addEventListener("click", togglePeakMode);

  els.orderTabs?.addEventListener("click", (evt) => {
    const target = evt.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest(".tab-btn");
    if (!button) return;
    const tab = button.dataset.tab;
    if (!tab) return;
    switchTab(tab);
  });

  document.addEventListener("keydown", (evt) => {
    if (evt.key === "/" && document.activeElement !== els.menuSearch) {
      evt.preventDefault();
      els.menuSearch?.focus();
      return;
    }

    if (evt.key === "F1") {
      evt.preventDefault();
      clearCurrentOrder();
      return;
    }

    if (evt.key === "F2") {
      evt.preventDefault();
      holdCurrentOrder();
      return;
    }

    if (evt.key === "F3") {
      evt.preventDefault();
      switchTab("recent");
      return;
    }

    if (evt.key === "Enter") {
      const activeTag = document.activeElement?.tagName;
      const isInput = activeTag === "INPUT" || activeTag === "SELECT" || activeTag === "TEXTAREA";
      if (!isInput && !els.comboModal?.classList.contains("open")) {
        evt.preventDefault();
        submitOrder();
      }
    }
  });

  // 快速找零按鈕
  document.querySelectorAll(".quick-change-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const received = parseInt(btn.dataset.amount, 10);
      const total = calculateTotal();
      const change = received - total;
      const changeDisplay = document.getElementById("changeDisplay");

      if (change < 0) {
        changeDisplay.textContent = `金額不足！還需 $${formatMoney(Math.abs(change))}`;
        changeDisplay.className = "change-display error";
      } else {
        changeDisplay.textContent = `找零：$${formatMoney(change)}`;
        changeDisplay.className = "change-display success";
      }

      // 3 秒後清除顯示
      setTimeout(() => {
        changeDisplay.textContent = "";
        changeDisplay.className = "change-display";
      }, 3000);
    });
  });
}

async function bootstrap() {
  await Auth.ensureAuth(["staff", "manager", "owner"]);

  setupEvents();
  setupComboModalEvents();
  setClock();
  setInterval(setClock, 30000);

  await Promise.all([fetchMenu(), fetchCombos(), fetchRecentOrders()]);

  renderCart();
  renderHeldOrders();
  switchTab("current");
  setupWebsocket();

  setInterval(() => {
    fetchRecentOrders().catch(() => {});
  }, 30000);
}

bootstrap().catch((err) => {
  setMessage(`初始化失敗：${String(err.message || err)}`, "error");
});
