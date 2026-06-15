# TOOLING.md —— AI 輔助開發揭露

本專案在 AI 程式輔助下完成。本文件依作業要求揭露**使用了哪些 AI 工具、
用於什麼、以及產出如何被審查**。由於未提供範本，下方的章節結構是我們自訂的；
如有需要，可依指定範本重新對應。

## 1. 使用的 AI 工具

| 工具 | 版本 / 模型 | 在本專案中的角色 |
|------|-------------|------------------|
| **Claude Code**（Anthropic CLI、桌面應用） | CLI `2.1.170`、模型 Claude Opus 4.x | 後端、前端、測試、基礎設施與文件的主要結對程式夥伴。 |
| （未使用其他 AI 工具） | —— | 未使用 Copilot、Cursor、ChatGPT 或其他助手。 |

所有 AI 互動皆透過 Claude Code 進行。完整、未經編修的對話紀錄以 JSONL
形式交付（機密如何遮蔽見 [REDACTION.md](REDACTION.md)）。

## 2. AI 用於什麼

- **架構與規劃。** 將作業轉化為 [PLAN.md](PLAN.md) 中的分階段計畫
  （技術棧的選擇、分層、7 天拆解、風險清單）。人類設定目標與限制，AI 負責
  起草與迭代。
- **實作。** 撰寫 apiflask 後端（auth/JWT、Argon2 雜湊、RBAC 權限矩陣、
  聊天 session/訊息持久化、SSE 串流、`LLMProvider` port + mock + Groq adapter、
  super-admin 匯出）、Alembic migration、Vue 3 SPA，以及 Docker/compose 設定。
- **測試。** 起草 pytest 測試套件（單元 + 整合 + 串流端對端）—— 撰寫當下
  共 112 個測試。
- **文件與交付物。** README、本檔、`REDACTION.md`，以及對話紀錄遮蔽腳本。

## 3. 人類監督與決策歸屬

人類開發者擁有每一項決策，並審查了所有產出。具體而言：

- **方向與驗收。** 人類選定技術棧的取捨（Groq、PostgreSQL、HS256、Argon2id、
  gevent worker），決定要嘗試哪些 Bonus 項目的範圍，並在進入下一階段前，
  針對各階段的驗收標準逐一核可。
- **程式審查。** 每一處變更在 commit 前都經過閱讀。Commit 切得小且以階段為
  範圍（7 個 commit，各為一個連貫的增量），正是為了讓每份 diff 都可審查、
  且可回溯至對話紀錄。
- **安全判斷。** 具安全影響的決策 —— 不硬編碼任何機密（全部透過 env /
  Pydantic Settings）、super-admin seed 的 fail-fast、保證永遠 ≥1 位 active
  super_admin 的結構性不變式、對他人聊天 session 回 404 而非 403、對渲染的
  助理內容使用 DOMPurify —— 都是由人類明確要求並驗證，而非默默產生。

## 4. 驗證（不只是「看起來對」）

- **自動化測試**在本機跑出全綠（`pytest`，112 通過），且涵蓋作業所指名的
  四個面向：auth、RBAC、chat 與 export。
- **手動 / 執行期檢查。** `docker compose up` 以一道指令啟動整個服務；
  `/docs`、`/health`、`/health/ready`、串流聊天、admin 流程與匯出 endpoint
  皆經人工實測。
- **誠實揭露限制。** 已知的取捨與刻意略過的 Bonus 項目記於 README 的
  「已知限制 / 取捨」一節，而非予以隱藏。

## 5. 給評審的說明

- git 歷史與 JSONL 對話紀錄旨在交叉對照：每個 commit 對應一段被記錄的對話。
- 對話紀錄以**遮蔽後**（移除機密）但其餘原汁原味的形式交付 —— 它們是原始的
  JSONL，而非手工編修的 Markdown 重寫。見 [REDACTION.md](REDACTION.md)。
