# CLAUDE.md — 早餐店系統 (青青草原廚房)

## 專案概述

全端早餐店 POS + KDS + 庫存 + 分析系統，店名「青青草原廚房」。
線上環境：`https://081-system.zeabur.app/`

## 技術棧

- **後端**: FastAPI 0.116 + SQLAlchemy 2.0 + Pydantic 2.x + Alembic
- **前端**: 純 HTML/CSS/JS（無框架、無建置步驟），由 FastAPI 掛載靜態檔案
- **資料庫**: 本地 SQLite (`breakfast.db`)，線上 PostgreSQL (Zeabur)
- **即時通訊**: WebSocket (`/ws/events`)，廣播模式
- **認證**: 自製 HMAC-SHA256 token + PBKDF2 密碼雜湊（非 PyJWT）
- **部署**: Docker (Python 3.12-slim) / Zeabur Git service

## 專案結構

```
app/
├── main.py          # FastAPI 入口、lifespan、路由掛載、WS、靜態檔案
├── config.py        # dotenv 環境變數設定
├── database.py      # SQLAlchemy engine/session/Base/get_db
├── models.py        # 全部 12 張 ORM 表
├── schemas.py       # 全部 Pydantic schema + enum
├── security.py      # 密碼雜湊、token 簽發/驗證
├── auth.py          # DI: get_current_user, require_roles, WS 認證
├── seed.py          # 預設使用者 + 範例菜單/食材/配方
├── ws.py            # WebSocket ConnectionManager
├── routers/         # 薄 HTTP handler，委派給 services
│   ├── auth.py      # /api/auth/*
│   ├── menu.py      # /api/menu/*（含 combo rules）
│   ├── orders.py    # /api/orders/*
│   ├── inventory.py # /api/inventory/*
│   ├── analytics.py # /api/analytics/overview
│   └── audit.py     # /api/audit/logs
└── services/        # 業務邏輯層
    ├── orders.py    # 訂單生命週期（建立/付款/修改/狀態轉換）
    ├── inventory.py # 庫存扣減/回復/修改差額/庫存驗證
    ├── analytics.py # 營收/熱銷/日銷/低庫存/庫存價值
    └── audit.py     # 稽核日誌寫入

frontend/
├── index.html       # 入口頁（各模組連結）
├── shared/
│   ├── auth.js      # 共用認證模組（登入 modal、token、authFetch、WS 重連）
│   └── theme.css    # 共用 CSS 變數與基礎樣式
├── pos/             # POS 點餐介面
├── kds/             # 廚房顯示系統（三欄看板）
└── admin/           # 管理後台（庫存/分析/稽核）

alembic/versions/    # 資料庫遷移
tests/test_system.py # 整合測試（10 個測試案例）
scripts/import_menu_api.py  # 批次匯入菜單腳本
imports/             # 菜單 JSON 資料（75 品項 + 2 套餐規則）
```

## 常用指令

```bash
# 啟動（本地開發）
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 測試
pytest -q

# 資料庫遷移
alembic revision --autogenerate -m "描述"
alembic downgrade -1

# 批次匯入菜單
python scripts/import_menu_api.py
python scripts/import_menu_api.py --dry-run  # 預覽
```

PowerShell 快捷腳本：`start_local.ps1`（前景）、`start_local_bg.ps1`（背景）、`stop_local.ps1`（停止）

## 頁面路由

| 路徑 | 說明 |
|------|------|
| `/` | 入口頁 |
| `/pos` | POS 點餐 |
| `/kds` | 廚房顯示 |
| `/admin` | 管理後台 |
| `/docs` | Swagger API 文件 |
| `/health` | 健康檢查 |

## 架構慣例

- **分層**: routers（薄 handler + DI）→ services（業務邏輯）→ models（ORM）
- **API 前綴**: `/api/{domain}`（orders、menu、inventory、auth、analytics、audit）
- **Python 命名**: snake_case；**JS 命名**: camelCase
- **所有 Python 檔案** 使用 `from __future__ import annotations`
- **Pydantic schema** 使用 `model_config = {"from_attributes": True}`
- **前端 UI 文字**: 繁體中文；程式碼識別符: 英文
- **CSS**: 大量使用 CSS custom properties + `clamp()` 響應式

## 角色權限

| 角色 | 權限 |
|------|------|
| `staff` | 建立/付款/修改訂單、查看菜單與訂單 |
| `kitchen` | 查看訂單、更新訂單狀態、查看低庫存 |
| `manager` | kitchen 全部 + 庫存管理 + 分析 + 菜單管理 + 稽核日誌 |
| `owner` | manager 全部 + 使用者管理 |

透過 `require_roles()` 依賴注入守衛實施。

## 關鍵設計決策

1. **交易式庫存**: 訂單自動付款時原子扣減庫存，不足則整筆 409 回滾並回傳缺貨明細
2. **訂單狀態機**: `pending → preparing → ready → completed`，`cancelled` 僅允許從 pending/preparing
3. **庫存異動追蹤**: stock_movements 的 reference 格式為 `ORDER:<號碼>`、`CANCEL:<號碼>`、`AMEND:<號碼>`
4. **WebSocket 廣播**: 無 room/channel 區分，所有已認證客戶端收到所有事件
5. **Alembic 遷移冪等**: 建表前檢查 existing_tables 和 has_index
6. **稽核日誌全面記錄**: 登入、使用者建立、訂單操作、菜單變更、庫存異動皆記錄

## 測試

測試使用獨立的 `test_breakfast.db`，每個測試前透過 `setup_function()` 重置資料庫。
涵蓋：認證守衛、自動付款扣庫存、廚房狀態更新、分析、庫存不足阻擋、取消回復庫存、稽核日誌、訂單修改差額、低庫存可見性、套餐規則 CRUD。

## 環境變數（見 .env.example）

`DATABASE_URL`、`SECRET_KEY`、`TOKEN_EXPIRE_MINUTES`、`APP_ENV`、`CORS_ORIGINS`
