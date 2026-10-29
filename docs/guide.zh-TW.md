# kirby 說明

[English](guide.md) | 繁體中文 | [简体中文](guide.zh-CN.md)

[README](../README.zh-TW.md) 背後的細節：kirby 的組成、安裝每一步在做什麼，以及 Codex 版的差異。

## 組成

kirby 分成三部分：

- **`inhale` skill**：搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），判斷、推薦合適的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安裝用的 tool `mcp__kirby__install`。透過這個 tool 安裝時，會先跳兩層對話框等你決定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜尋用的 tool，以及同樣會跳兩層對話框的 `install` tool。

skill 會要求模型只用這些 tool 安裝，但這只是指示，不是硬性攔截：模型仍然可以自己執行 `claude mcp add`、`codex mcp add` 之類的安裝指令。

## 搜尋

在 Claude Code 也可以用 `/kirby:inhale` 直接叫用。模型也可能在任務需要時自己使用這個 skill，但不保證每次都會。

每個 repo 都會附上 star 數和最後 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 預設搜尋來源

可選 `stars`（預設）、`public`、`both`，在 `/config` 裡 kirby 的 `default_source` 設定。每次也可以在 prompt 裡直接指定，例如「從公開的找」。

公開搜尋只會找到有 agent 工具類 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

## 安裝流程

你選定要裝的 repo 後，mod 會跳兩層對話框：

1. **下一步**：取消 / 先看 README / 換一個 / 安裝。對話框會列出種類、commit、檔案數、內含的腳本和安裝前檢查的結果（下面的掃描和查詢）。惡意套件查詢找到已知的惡意套件時，不會提供「安裝」。
2. **scope**（選了「安裝」才會出現）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 專案的 `.claude/skills/`，並自動加進 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 專案的 `.claude/skills/`，會進 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/`（有設 `CLAUDE_CONFIG_DIR` 時是 `$CLAUDE_CONFIG_DIR/skills/`） | `--scope user` | `--scope user` |

plugin 不論裝在哪個 scope，它的 marketplace 都會記錄在 user settings。

### 掃描

在第一個對話框出現前，tool 會掃描 skill 的檔案（就是實際要安裝的那份），找值得留意的模式：Markdown 裡的隱藏 Unicode、HTML 註解和針對模型的語句；範圍很廣的 `allowed-tools`；提到 agent 設定檔和憑證檔；以及腳本裡的網路呼叫、shell 執行、解碼、讀取機密環境變數和修改 shell 啟動檔。對話框會列出每條命中的規則和位置，前面標上嚴重度：`hidden-unicode`、`injection-phrase`、`credentials`、`startup-files` 在正常的 skill 裡較少見，標 `warn`，其他標 `info`；`warn` 的規則排在前面。這只是 pattern 比對，不是安全審查：有命中不代表有害，沒命中也不代表安全，所以任何命中都不會擋下安裝。plugin 的檔案也用同樣的方式掃描（見下面的 plugin）；MCP server 不會掃描，對話框會註明。tool 也會把命中位置和掃描的 commit 交給模型，你可以直接問它某一行在做什麼。在 Claude Code 裡，模型用 `gh api` 讀那個檔案，skill 沒有預先允許這個指令，所以除非你的權限模式允許，Claude Code 會先問你。

### 漏洞查詢和惡意套件查詢

對 skill 和 plugin，安裝前檢查還會查詢已公開的漏洞和已知的惡意套件，只用除了你的 `gh` 登入之外不需要任何金鑰的公開服務：[OSV.dev](https://osv.dev) 和 GitHub。

- **相依套件。** tool 讀取 skill 在鎖定 commit 的 `package-lock.json`（或 `package.json`）、`uv.lock`、`requirements.txt` 和 `pyproject.toml`。沒有 lockfile 時，用 `npm install --package-lock-only --ignore-scripts` 或 `uv pip compile --no-build` 算出版本，不會安裝任何東西，也不會執行套件的程式碼（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。這時對話框會註明版本是檢查當下算出的，實際執行時可能不同。沒有 npm 或 uv 時只知道套件名稱，惡意套件查詢仍會用名稱查，漏洞查詢則標為 unchecked。
- **漏洞查詢。** 向 OSV.dev 查每個相依套件的那個版本，以及鎖定的 commit 本身（OSV 會把 commit 對到記錄裡的 git 範圍）；向 GitHub 查 repo 為自己發布的 advisory。相依套件有 critical 或 high 的漏洞，或 OSV 對到這個 commit 的任何記錄，是 `danger`；其他漏洞是 `warn`，無法對到這個 commit 的 repo advisory 也是 `warn`，對話框會說無法判斷它是否影響這個 commit。
- **惡意套件查詢。** OSV.dev 裡 id 以 `MAL-` 開頭的記錄，來自 OpenSSF Malicious Packages。查到就是 `danger`，而且會**擋下**安裝：第一層對話框只剩取消、先看 README 和換一個，模型會告訴你原因。仍然要裝的話，只能自己手動安裝。其他情況都不會擋：掃描命中和漏洞不論多嚴重，都由你判斷（[ADR 0001](adr/0001-block-only-on-confirmed-malware.md)）。
- **unchecked。** 查詢失敗或逾時，會顯示為 `unchecked`，不會當成沒找到，「安裝」也仍然可選。

每個結果都會把同樣的發現交給模型，你可以直接問它某一項。MCP server 目前還不會查詢。

### plugin

plugin 依它在 marketplace 裡的條目所寫的來源檢查，用的是 marketplace 的 commit：

- **marketplace repo 裡的資料夾**（`"source": "./plugins/x"`）：檢查那個資料夾，commit 就是對話框顯示的那個。
- **另一個 GitHub repo**（`github`、`url` 或 `git-subdir`）：條目有 `sha` 時，檢查那個 repo 的這個 commit。沒有 `sha` 時檢查它目前的樣子，對話框會註明來源沒有鎖定，實際安裝的可能和檢查的不同。
- **其他來源**（npm 套件、壓縮檔、指令、GitHub 以外的 git 主機）：不會抓取，對話框會把掃描和兩項查詢標為 unchecked。

對話框的 `source:` 那行會說是哪一種。之後掃描和查詢跟 skill 一樣跑在這些檔案上，查到已知的惡意套件也同樣會擋下安裝。

### 鎖定 commit

skill 和 plugin 只會安裝對話框顯示的那個 commit。如果在實際安裝前 repo 有了新的 commit，就不會留下安裝；模型會告訴你，你仍然想裝的話，它會重新跳出對話框，顯示新的 commit。MCP server 沒有鎖定版本：它每次啟動時執行的是它的指令所抓到的程式碼，例如 `npx -y <package>`。

plugin 鎖定的是 marketplace 的 commit（[ADR 0003](adr/0003-verify-plugin-commit-after-adding-marketplace.md)）：

- **兩邊都一樣**：兩個 CLI 都沒有 kirby 能用的方式安裝指定的 commit，所以 tool 在你還沒加入 marketplace 時照常加入（不指定 ref），安裝 plugin，再讀 marketplace 的 clone 在哪個 commit。不是檢查過的那個 commit，就把 plugin 移除並說明原因；marketplace 保留。
- **Claude Code**，已經加入 marketplace：Claude Code 從落後於 repo 的 marketplace 安裝時會先更新它。所以 tool 檢查的是 repo 目前的 commit，也就是安裝會帶來的那個，對話框會說明：`installs from it as it is`，或 `behind its repo; installing refreshes it to <commit>`。tool 無法判斷它是否落後時（GitHub 沒有回應），對話框會用一行 `unchecked:` 說明，檢查的則是你的 marketplace 目前所在的 commit。
- **Codex**，已經加入 marketplace：`codex plugin add` 不會更新它，所以 tool 檢查它目前所在的 commit，並從它安裝。

plugin 可以依賴其他 plugin，這些會跟著一起安裝。tool 不檢查它們；對話框用一行 `installed along with it, not checked:` 列出。

### 對話框語言

對話框的文字由模型依 skill 規定的格式，用你使用的語言寫。上方的事實（repo、star 數、commit、檔案、腳本、已存在的資料夾、掃描和查詢結果），以及範圍問題下方的 prompt cache 提醒，由 tool 產生，固定是英文。範圍對話框的選項固定是 `cancel`、`local`、`project`、`user`。沒有提供文字或格式不完整時，對話框顯示英文。

### 安裝和 prompt cache

依照 [官方文件](https://code.claude.com/docs/en/prompt-caching)，以及這個專案的實測結果：

- **skill**：裝完後 cache 沒有 miss（實測）。
- **MCP**：`claude mcp add` 要重開 session 才會生效，這個 session 的 cache 不受影響。
- **plugin**：要用 `/reload-plugins` 載入。plugin 裡的 skill、hook 等不影響 cache。如果 plugin 帶有 MCP server，而且 session 的 tool search 是關閉的（預設是開著），載入後 cache 會重建一次。遇到這種情況，Claude Code 會先警告，要加 `--force` 才會套用（實測）。

plugin 的提醒由 tool 放在 scope 那一層對話框。MCP 的提醒交給模型：skill 要求它寫在第一層對話框。

## Codex

同一個 repo 也是 Codex plugin。Codex 讀 `.codex-plugin/plugin.json`，載入 Codex 版的 skill（`codex/skills/inhale/`）和一個 MCP server（`codex/server.py`，只用 Python 標準函式庫，設定在 `mcp.json`）。Claude Code 的 mod 在 Codex 不會用到。

和 Claude Code 版的差異：

- **搜尋和讀檔走 MCP tool。** server 的 `stars`、`public`、`detect` 會執行同一批腳本，`readme` 和 `file` 則從 GitHub 讀取 README 或某個 commit 的單一檔案，全都在 Codex 的 sandbox 外執行，所以不會每次都要求連網權限。這五個 tool 宣告自己只讀取，在 Codex 預設的核准設定下，Codex 會直接執行、不先詢問。kirby 的 `install` 執行前，Codex 仍會先問；選「Always allow」會記住。
- **對話框是 MCP elicitation。** `install` tool 一樣跳兩層對話框，和 Claude Code 版一樣，文字由模型用你的語言寫，事實部分維持英文。
- **沒有 `default_source` 設定。** 預設是 `stars`，要搜公開的或兩者都搜，直接在 prompt 裡說。
- **scope：**

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 專案的 `.agents/skills/`，並自動加進 `.gitignore` | — | — |
| `project` | 專案的 `.agents/skills/`，會進 git | — | — |
| `user` | `~/.agents/skills/` | `codex plugin add`（`~/.codex/config.toml`） | `codex mcp add`（`~/.codex/config.toml`） |

`codex plugin add` 和 `codex mcp add` 沒有 scope 參數，所以 plugin 和 MCP 只能裝在 user。如果 Codex 沒有提供 session 所在的專案，skill 也只能選 `user`。這些情況下，第一層對話框會多一行說明裝到哪裡（`installs at: user …`）；scope 對話框的選項是 `cancel` 和 `install at user (…)`，等於用 tool 自己寫的文字再確認一次。

裝完後，開新的 Codex session 才能使用。

Codex 也讀得懂 Claude Code 格式的 marketplace。plugin 來自這種 marketplace 時，對話框的事實會列出 marketplace 檔案，skill 也要求模型提醒：只為 Claude Code 寫的部分（例如 hooks）可能無法運作。

如果只說「安裝 owner/repo」，Codex 可能改用它內建的 `skill-installer` 安裝，不會經過 kirby 的對話框（實測遇過）。它要求執行那個安裝程式時，可以拒絕，再請它改用 kirby 安裝。

## 腳本

都在 `skills/inhale/scripts/`。前三個是唯讀的，skill 執行時不會詢問你：

| 腳本 | 用途 |
| --- | --- |
| `stars.py` | 讀取你的 star 和 star list（GraphQL），快取在 `~/.cache/kirby/stars.json`，24 小時更新一次 |
| `public.py` | 依 agent 工具類的 topic 搜尋公開的 GitHub repo |
| `detect.py` | 判斷 repo 是 marketplace、plugin、skill 還是 MCP server，以及安裝需要的資訊 |
| `install_skill.py` | 把 skill 資料夾複製到指定 scope 的 skills 目錄，來源 commit 記在 `.kirby.json`。加上 `--check` 只列出會安裝的內容、掃描和查詢結果，不會寫入；`--commit` 只安裝對話框顯示的那個 commit。由 mod 和 Codex 的 MCP server 呼叫 |
| `check_plugin.py` | marketplace plugin 的安裝前檢查：抓取 marketplace（已經加入的用 `--commit` 指定它所在的 commit），依 plugin 的來源找到它的檔案，再執行掃描和查詢。輸出 JSON，不會安裝任何東西。由 mod 和 Codex 的 MCP server 呼叫 |
| `lookups.py` | `install_skill.py --check` 和 `check_plugin.py` 執行的漏洞查詢和惡意套件查詢：讀取相依套件檔案、不安裝就算出版本，再向 OSV.dev 和 GitHub 查詢。不會單獨執行 |

`detect.py --agent codex` 會先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 會裝到 `.agents/skills/`。
