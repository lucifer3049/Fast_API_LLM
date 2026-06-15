# LLM 聊天網頁應用

多使用者 LLM 聊天網頁應用 —— apiflask（後端）+ Vue 3（前端）+
PostgreSQL + Groq，透過 Docker Compose 一鍵啟動。

> 開發依循 [PLAN.md](PLAN.md)。本 README 隨各階段持續增補；目前狀態：
> **Day 7 —— 收斂與交付物**：文件定稿
> （[TOOLING.md](TOOLING.md)、[REDACTION.md](REDACTION.md)）、對話紀錄
> 遮蔽（redaction）、完整測試通過，以及乾淨的一鍵啟動驗證；建立在
> Day 6 的 super-admin 匯出 + 獨立 Vue 3 前端與 Day 5 的真實
> Groq SSE 串流之上。

## 快速開始

```bash
# 1. 由範本建立你的 env 檔並填入機密值。
cp .env.example .env
# 產生一組強度足夠的 JWT secret：
python -c "import secrets; print(secrets.token_urlsafe(48))"
# 在 .env 設定 JWT_SECRET、POSTGRES_PASSWORD、SUPER_ADMIN_USERNAME/PASSWORD。

# 2. 啟動整個服務（Postgres + API）。Migration 會自動執行。
docker compose up --build
```

接著開啟：

- API 文件（OpenAPI / Swagger UI）：http://localhost:8000/docs
- 存活探測（Liveness）：http://localhost:8000/health
- 就緒探測（Readiness，檢查 DB + LLM 上游）：http://localhost:8000/health/ready

## 專案結構

```
backend/                 apiflask 服務（Clean Architecture，PLAN §3.1）
  app/
    domain/              純業務邏輯：Role、RBAC 權限矩陣、訊息角色
    application/         use-case / service 層（Day 2+ 加入）
    infrastructure/      config、db（SQLAlchemy + Alembic）、security、llm
    interface/           apiflask blueprints + schemas
  alembic/               migrations
  Dockerfile            multi-stage、以非 root 身分執行
docker-compose.yml       db + api + frontend，一鍵啟動
.env.example             完整環境變數範本（不提交任何機密）

../vue_llm/              Vue 3 + Vite SPA（獨立前端，PLAN Day 6）
  src/api/               fetch client、SSE 串流解析器、具型別的 endpoints
  src/stores/            Pinia：auth + chat（串流狀態）
  src/views/             Login / Chat / Admin / Account
  Dockerfile, nginx.conf 提供建置後的 SPA，並反向代理 API
```

## 技術選型與理由

詳見 [PLAN.md §2](PLAN.md)。摘要：

- **PostgreSQL** —— production 等級、成熟的 SQLAlchemy + Alembic 生態、
  原生 JSONB；多出來的服務由 compose 一併涵蓋，因此一鍵啟動仍然成立。
- **Groq** —— 有免費額度、相容 OpenAI 的 API、原生 SSE 串流。包裝在
  `LLMProvider` port 之後，因此可透過設定切換供應商。
- **JWT HS256** —— 單一發行者 / 單一服務；HS256 + 環境變數 secret 是
  最簡單而足夠的選擇（在此用 RS256 會是過度設計）。
- **Argon2id** —— 現代、記憶體密集（memory-hard）的密碼雜湊。
- **Gunicorn + gevent worker** —— SSE 串流是長時間的 I/O 等待；
  gevent 可避免 worker 因每條串流而被佔住。

## 身分驗證（Authentication）

- **預設管理員（seed）：** 首次啟動時，一個冪等（idempotent）的 seed 會由
  `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` 建立 `super_admin`。若兩者
  任一缺漏，應用會**快速失敗（fail fast）**，而非在沒有管理員的情況下啟動
  （不變式 I-1）。重複執行為 no-op（絕不重建/覆寫）。
- **登入：** `POST /auth/login`，帶 `{username, password}`，回傳一組 JWT
  access token。在受保護的路由上以 `Authorization: Bearer <token>` 送出。
- **登出：** `POST /auth/logout` —— JWT 為無狀態（stateless），因此登出是
  在客戶端丟棄 token；此 endpoint 的存在是為了對稱性與稽核記錄。
- **變更自己的密碼：** `POST /auth/change-password`。
- **密碼**以 Argon2id 雜湊，絕不以明文儲存。

快速示範（在 `docker compose up` 之後）：

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"superadmin","password":"<your SUPER_ADMIN_PASSWORD>"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
```

## 授權（RBAC）

三種角色 —— `user` / `admin` / `super_admin` —— 由
[domain/user.py](backend/app/domain/user.py) 中的單一權限矩陣驅動。View 上掛有
`@require_permission(...)` 閘門；細緻、依目標而定的規則放在 service 層
（因此業務規則回傳 4xx，而非 500）。

Admin / Super Admin API：

| Method 與 path | 權限 | admin | super_admin |
|---|---|:---:|:---:|
| `GET  /admin/users` | 列出使用者 | ✓ | ✓ |
| `POST /admin/users` (role=user) | 建立使用者 | ✓ | ✓ |
| `POST /admin/users` (role=admin) | 建立 admin | ✗ | ✓ |
| `PATCH /admin/users/{id}/active` (user) | 啟用/停用 user | ✓ | ✓ |
| `PATCH /admin/users/{id}/active` (admin) | 啟用/停用 admin | ✗ | ✓ |
| `POST /admin/users/{id}/promote` | 將 user 升級為 admin | ✗ | ✓ |
| `GET  /admin/export` | 匯出所有對話（JSON） | ✗ | ✓ |

**不變式 I-2 —— 永遠至少有 1 位 active 的 super_admin：** 由結構上保證。
沒有任何 API 路徑會建立、停用或降級 super_admin（他們只能透過 seed 產生），
因此系統永遠不會進入「沒有 super admin」的狀態。任何以 super_admin 為目標的
操作都會被拒絕（403）。

## 聊天（Chat）

每位使用者擁有多個聊天 session（ChatGPT 風格）。Session 與訊息會被持久化；
歷史訊息以時間順序載入。此處的授權為**以使用者為單位的擁有權**——屬於其他
使用者的 session 會回傳 `404`（而非 `403`），如此 API 便不會洩漏哪些
session id 存在。

| Method 與 path | 說明 |
|---|---|
| `POST   /chat/sessions` | 建立 session（`title` 選填） |
| `GET    /chat/sessions` | 列出自己的 session，最近活動者在前 |
| `GET    /chat/sessions/{id}` | 載入某個 session 及其完整訊息歷史 |
| `DELETE /chat/sessions/{id}` | 刪除自己的 session（連帶刪除訊息） |
| `POST   /chat/sessions/{id}/messages` | 送出一則訊息；持久化使用者回合、取得助理回覆、持久化後一併回傳（非串流） |
| `POST   /chat/sessions/{id}/messages/stream` | 同上，但透過 SSE 逐 token 串流助理回覆 |

- **LLM 供應商**抽象於 `LLMProvider` port 之後，有兩種實作：一個確定性的
  離線 **mock**（`LLM_PROVIDER=mock`，無需 API key 即可運作），以及真實的
  **Groq** adapter（`LLM_PROVIDER=groq` + `GROQ_API_KEY`），它是相容 OpenAI
  的 client，因此切換供應商是改設定、而非改程式碼。`LLM_PROVIDER=groq` 但
  沒有 key 時會**快速失敗（fail fast）**。
- **串流（SSE）。** 串流 endpoint 會先持久化使用者回合並 commit，*之後*才開啟
  回應（如此擁有權/驗證錯誤會是真正的 `404`/`422`，且使用者回合在客戶端斷線
  時仍會留存），接著送出 `text/event-stream` 事件：一個 `meta` frame（已持久化
  的使用者訊息 + session 標題）、重複的 `token` frame（內容 delta），以及最終的
  `done`（已持久化的助理訊息）或 `error`。若串流途中上游失敗，目前已收到的部分
  回覆仍會被持久化，因此使用者回合絕不會懸而無答（PLAN §3.5）。以 Bearer header
  傳入 JWT。回傳的回覆把各個 delta 串接後，會與非串流路徑回傳的內容完全一致。
- **第一則訊息**會自動為未命名的 session 取名（截斷處理）；之後標題不會被覆寫。
- **排序**不信任系統時鐘（Postgres `now()` 是交易時間，而 OS 時鐘可能很粗糙）：
  每則訊息的時間戳都嚴格排在同一 session 內前一則之後，因此歷史是確定性的，
  無需額外的 sequence 欄位。

```bash
SID=$(curl -s -X POST localhost:8000/chat/sessions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/chat/sessions/$SID/messages \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Hello!"}'

# 串流版本 —— -N 關閉 curl 的緩衝，使 token 一到達就印出：
curl -N -X POST localhost:8000/chat/sessions/$SID/messages/stream \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Tell me a short joke."}'
```

## 匯出（super_admin）

`GET /admin/export` 回傳一份完整的 JSON 快照，包含每位使用者及其聊天 session
與訊息 —— 用於封存 / 遷移。僅限 super_admin（其他角色會得到 `403`）。Session
以 `selectinload` 載入，因此整個匯出是一次批次查詢取得所有訊息，而非每個
session 查一次（避開 N+1 路徑，PLAN §3.2）。

```bash
curl -s localhost:8000/admin/export -H "Authorization: Bearer $TOKEN" -o export.json
```

結構：`{ exported_at, users: [ { id, username, role, sessions: [ { id, title,
created_at, updated_at, messages: [ { role, content, created_at } ] } ] } ] }`。

## 前端（Vue 3）

一個獨立的 Vue 3 + Vite + TypeScript + Pinia SPA 位於相鄰的 repo
[`../vue_llm`](../vue_llm)（前後端分離）：登入 / 登出 / 變更密碼、
支援**逐 token SSE 串流**與 markdown 渲染的多 session 聊天，以及 Bonus
管理頁面（使用者管理 + 匯出）。

```bash
cd ../vue_llm
npm install
npm run dev          # http://localhost:5173，將 API 代理至 :8000
```

- **API 整合。** 在開發模式下，Vite proxy 會把 `/auth /chat /admin
  /health` 轉發到 `:8000`，讓瀏覽器維持同源（避免 CORS 摩擦）。若想改為直接
  呼叫 API，設定 `VITE_API_BASE=http://localhost:8000` —— 後端便會透過
  **`CORS_ORIGINS`** 允許該來源（設定詳見下方）。
- **串流。** `EventSource` 無法送出 `Authorization` header，因此 SPA 改用
  `fetch` 以 POST 發送，並手動解析 `text/event-stream` 內容
  （`src/api/chat.ts`），消費 `meta` / `token` / `done` / `error` frame。
- **驗證 token。** JWT 保存在 `localStorage`，並以 Bearer header 送出；
  收到 `401` 會清除它並導回 `/login`。*（取捨：比 httpOnly cookie 簡單，但可被
  JS 讀取，因此仰賴 markdown 淨化器來圍堵 XSS —— 見「已知限制」。）*
- **正式環境 / 一鍵啟動。** `docker compose up --build` 同時會建置前端
  （`frontend` 服務）：nginx 提供建置後的 SPA 並反向代理 API，因此瀏覽器為
  同源、無需 CORS。開啟 http://localhost:5173。

## 設定（Configuration）

所有機密與可調參數皆來自環境變數（`.env`）；沒有任何硬編碼。完整清單見
[.env.example](.env.example)。`.env` 已被 git 與 docker 忽略。
**`CORS_ORIGINS`**（以逗號分隔）列出允許跨來源呼叫 API 的來源；預設為 Vite
開發伺服器（`http://localhost:5173`）。當 SPA 由 compose 的 nginx 以同源提供
時，請將其留空。

## 測試

單元測試對 service 使用假的 repository（不接 DB），對 seed/repository 測試
使用記憶體內 SQLite —— 快速且具確定性。

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## 狀態 / 路線圖

- [x] **Day 1** —— 基礎：骨架、設定、DB + Alembic migration、`/docs`、
  健康檢查、Docker Compose 一鍵啟動。
- [x] **Day 2** —— 驗證：Argon2 雜湊、JWT（HS256）、login/logout/me/變更
  密碼、具 fail-fast 的 super_admin 冪等 seed、單元測試。
- [x] **Day 3** —— RBAC：集中式權限矩陣 + `@require_permission`、
  admin/super-admin API（建立/列出/啟停用/升級）、跨角色守衛、
  不變式 I-2（永遠 >=1 位 active super_admin）、完整矩陣測試。
- [x] **Day 4** —— 聊天持久化：session CRUD、時間順序訊息歷史、
  以使用者為單位的擁有權（外部 session 回 404）、`LLMProvider` port + mock、
  第一則訊息自動命名；service + repository 測試。
- [x] **Day 5** —— 真實 Groq SSE 串流：`LLMProvider.stream`、Groq adapter
  （相容 OpenAI、缺 key 時 fail-fast）、帶 token frame 的 SSE endpoint、
  上游斷線時部分持久化；gevent worker 已為長連線配置妥當。Service、factory
  與端對端串流測試。
- [x] **Day 6** —— super-admin 匯出（`GET /admin/export`，避開 N+1）、為
  獨立前端設定 CORS，以及 Vue 3 SPA（`../vue_llm`）：登入、帶 markdown 的
  串流聊天、admin 使用者管理 + 匯出頁面；compose 現在也會建置前端。
  可觀測性 Bonus：帶 request-id 關聯的結構化 JSON 日誌，以及 DB + LLM 就緒
  探測。新增匯出 + 可觀測性測試。
- [x] **Day 7** —— 收斂與交付物：README 定稿，含技術理由 + 已知限制、
  AI 工具揭露（[TOOLING.md](TOOLING.md)）與機密遮蔽說明
  （[REDACTION.md](REDACTION.md)）、一支可稽核的對話紀錄遮蔽腳本
  （[scripts/redact_transcripts.py](scripts/redact_transcripts.py)），
  附 `--check` 洩漏自檢、完整測試通過（112 全綠），以及乾淨的
  `docker compose up` 驗證。尚待完成：錄製示範影片並打包 zip。

## 可觀測性（Observability）

- **結構化日誌。** 每一行日誌都是 stdout 上的一個 JSON 物件
  （`infrastructure/logging.py`）；每個請求有一筆 access log，帶有 method、
  path、status 與耗時。
- **Request-id 關聯。** 每個請求都會取得一個 id（來自傳入的 `X-Request-ID`
  header，或新產生的 uuid），蓋印在每一行日誌上，並在回應的 `X-Request-ID`
  header 回送 —— 如此同一請求的日誌可被一起 grep，並可從上游 proxy 追蹤。
- **就緒探測。** `GET /health/ready` 會驗證 DB 連線與 LLM 上游（mock 永遠
  ok；Groq adapter 會做一次不耗 token 的 `models.list` ping）。Compose 的
  healthcheck 輪詢存活探測（`/health`），因此容器健康狀態不會因外部相依而抖動。

## 已知限制 / 取捨

- **JWT 存放於 `localStorage`**（前端）：比 httpOnly cookie 簡單，對這種
  單頁 bearer-token 流程也夠用，但可被 JS 讀取 —— 助理內容已淨化
  （DOMPurify）以圍堵 XSS。改用 cookie + CSRF 會是強化的下一步。
- **匯出以單次組裝**（`selectinload`），而非分批串流；正確且避開 N+1，但對
  極大型資料集而言，伺服器端分批/串流的回應會更能限制記憶體用量。已記於
  PLAN §3.2。

## 交付物

| 項目 | 位置 |
|------|------|
| 原始碼 + git 歷史（乾淨、依階段切分的 commit） | 本 repo（含 `.git`） |
| README —— 啟動、預設管理員/seed、技術理由、限制 | 本檔 |
| 技術選型與理由 | [PLAN.md §2](PLAN.md) + 上方「技術選型」 |
| AI 工具揭露 | [TOOLING.md](TOOLING.md) |
| 機密遮蔽說明 + 遮蔽腳本 | [REDACTION.md](REDACTION.md)、[scripts/redact_transcripts.py](scripts/redact_transcripts.py) |
| 遮蔽後的原始 JSONL 對話紀錄 | `./transcripts/`（最後再重新產生 —— 見 [REDACTION.md](REDACTION.md)） |
| 示範錄影（3–5 分鐘） | 待錄製 |
