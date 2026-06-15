# REDACTION.md —— 對話紀錄中遮蔽了哪些內容

交付的對話紀錄是**原始的 Claude Code JSONL** 日誌，而非重寫過的摘要。在提交
之前，機密已從這些日誌的*副本*中以機械方式刷除；磁碟上的原始檔從未被改動。

## 遮蔽了哪些內容（分類）

| 類別 | 為什麼 | 佔位符 |
|------|--------|--------|
| **Groq API key**（`gsk_…`） | 第三方的有效憑證。 | `<REDACTED:GROQ_API_KEY>` |
| **JWT 簽章 secret**（`JWT_SECRET`） | 簽署所有驗證 token；外洩 = 可偽造任何 session。 | `<REDACTED:JWT_SECRET>` |
| **PostgreSQL 密碼**（`POSTGRES_PASSWORD`） | 資料庫憑證。 | `<REDACTED:POSTGRES_PASSWORD>` |
| **Super-admin 密碼**（`SUPER_ADMIN_PASSWORD`） | 用於初始化最高權限帳號。 | `<REDACTED:SUPER_ADMIN_PASSWORD>` |
| **已簽發的 JWT**（`eyJ…` bearer token） | 於手動 API 測試期間擷取；在過期前皆可使用。 | `<REDACTED:JWT>` |
| **開發者家目錄路徑**（`C:\Users\<name>`） | 個人/可識別身分的檔案系統路徑。 | `C:\Users\<USER>` |

**未**遮蔽的內容（不敏感）：像 `superadmin` 這類使用者名稱、DB 的
名稱/主機/連接埠、模型名稱（`llama-3.3-70b-versatile`），以及一般非機密的
設定 —— 這些是讓對話紀錄可被理解所必需，且不洩漏任何可被利用的東西。

## 如何進行遮蔽

由一支小而可稽核的腳本執行遮蔽：
[`scripts/redact_transcripts.py`](scripts/redact_transcripts.py)。它套用兩層：

1. **精確機密值**，於*執行期*從本機 `.env` 讀取（任何真實機密都不會被硬編碼
   進此 repo 或腳本中），在所有字面出現之處予以取代。
2. **以樣式為基礎**，針對具可辨識形狀、不受當前 `.env` 影響的憑證：
   `gsk_…` key、三段式的 `eyJ…` JWT，以及家目錄路徑。

```bash
python scripts/redact_transcripts.py \
  --src "C:/Users/<you>/.claude/projects/D--FastAPi-LLM" \
  --out ./transcripts \
  --env ./.env \
  --check
```

`--check` 會重新掃描遮蔽後的輸出，若仍出現任何已知機密值則以非零碼結束 ——
這是針對遮蔽不完整的自我測試。本次執行回報：GROQ_API_KEY ×3、JWT_SECRET ×12、
POSTGRES_PASSWORD ×16、SUPER_ADMIN_PASSWORD ×19、家目錄路徑 ×32、JWT ×2 ——
且 `--check` 通過（無洩漏）。另外對 `./transcripts` 獨立 `grep` `gsk_` /
`eyJ…` 也回傳空結果。

## 重要：最終打包前須重新產生

*當前*這個 session 的對話紀錄在這項工作進行期間仍持續增長，因此必須在**最後
重新執行一次**，就在壓縮成 zip 之前，以擷取最終的訊息。先遮蔽、重跑
`--check`，再將 `./transcripts/` 納入提交。

## 憑證輪替

由於真實憑證曾出現在工作中的 `.env`（因而也出現在未遮蔽的日誌裡），任何曾
曝露的憑證都應在提交前/提交時**輪替**，作為縱深防禦 —— 重新產生 Groq API key
與 `JWT_SECRET`，並更換 Postgres / super-admin 密碼 —— 即使交付的對話紀錄已
不再包含它們。`.env` 本身已被 git 與 docker 忽略，從不提交。
