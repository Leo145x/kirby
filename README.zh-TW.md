# kirby

[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)

從你的 GitHub star 和 star list，或公開的 GitHub 搜尋，找出合適的 skill、plugin 或 MCP server，經你確認後安裝到你選的 scope。

內容分成三部分：

- **`inhale` skill**：搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），判斷、推薦合適的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安裝用的 tool `mcp__kirby__install`。透過這個 tool 安裝時，會先跳兩層對話框等你決定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜尋用的 tool，以及同樣會跳兩層對話框的 `install` tool。

skill 會要求模型只用這些 tool 安裝，但這只是指示，不是硬性攔截：模型仍然可以自己執行 `claude mcp add`、`codex mcp add` 之類的安裝指令。

支援 Claude Code 和 Codex，Codex 版的差異見 [Codex](#codex)。

## 需求

- 已登入的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`

## 安裝

Claude Code：

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

Codex：

```
codex plugin marketplace add Leo145x/kirby
codex plugin add kirby@kirby
```

## 使用

直接問就行，例如：

- 「有沒有能畫架構圖的 skill？」
- 「從我的 AI Tools list 找 code review 的工具」
- 「從公開的 GitHub 找能查 postgres 的 MCP」

在 Claude Code 也可以用 `/kirby:inhale` 直接叫用。模型也可能在任務需要時自己使用這個 skill，但不保證每次都會。

每個 repo 都會附上 star 數和最後 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 預設搜尋來源

可選 `stars`（預設）、`public`、`both`，在 `/config` 裡 kirby 的 `default_source` 設定。每次也可以在 prompt 裡直接指定，例如「從公開的找」。

公開搜尋只會找到有 agent 工具類 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

### 安裝流程

你選定要裝的 repo 後，mod 會跳兩層對話框：

1. **下一步**：取消 / 先看 README / 換一個 / 安裝。對話框會列出種類、commit、檔案數和內含的腳本。
2. **scope**（選了「安裝」才會出現）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 專案的 `.claude/skills/`，並自動加進 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 專案的 `.claude/skills/`，會進 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/` | `--scope user` | `--scope user` |

plugin 不論裝在哪個 scope，它的 marketplace 都會記錄在 user settings。

skill 只會安裝對話框顯示的那個 commit。如果在實際安裝前 repo 有了新的 commit，就不會安裝；模型會告訴你，你仍然想裝的話，它會重新跳出對話框，顯示新的 commit。plugin 和 MCP server 沒有鎖定版本：plugin 裝的是安裝當下 marketplace 裡的版本，MCP server 則是每次啟動時執行它的指令所抓到的程式碼，例如 `npx -y <package>`。

對話框的文字由模型依 skill 規定的格式，用你使用的語言寫。上方的事實（repo、star 數、commit、檔案、腳本、已存在的資料夾），以及範圍問題下方的 prompt cache 提醒，由 tool 產生，固定是英文。範圍對話框的選項固定是 `cancel`、`local`、`project`、`user`。沒有提供文字或格式不完整時，對話框顯示英文。

### 安裝和 prompt cache

依照 [官方文件](https://code.claude.com/docs/en/prompt-caching)，以及這個專案的實測結果：

- **skill**：裝完後 cache 沒有 miss（實測）。
- **MCP**：`claude mcp add` 要重開 session 才會生效，這個 session 的 cache 不受影響。
- **plugin**：要用 `/reload-plugins` 載入。plugin 裡的 skill、hook 等不影響 cache。如果 plugin 帶有 MCP server，而且 session 的 tool search 是關閉的（預設是開著），載入後 cache 會重建一次。遇到這種情況，Claude Code 會先警告，要加 `--force` 才會套用（實測）。

plugin 的提醒由 tool 放在 scope 那一層對話框。MCP 的提醒交給模型：skill 要求它寫在第一層對話框。

## Codex

同一個 repo 也是 Codex plugin。Codex 讀 `.codex-plugin/plugin.json`，載入 Codex 版的 skill（`codex/skills/inhale/`）和一個 MCP server（`codex/server.py`，只用 Python 標準函式庫，設定在 `mcp.json`）。Claude Code 的 mod 在 Codex 不會用到。

和 Claude Code 版的差異：

- **搜尋走 MCP tool。** server 的 `stars`、`public`、`detect`、`readme` 會在 Codex 的 sandbox 外執行同一批腳本，所以每次搜尋不會要求連網權限。在 Codex 預設的核准設定下，Codex 仍會先問是否允許 kirby 執行該 tool；選「Always allow」會記住。
- **對話框是 MCP elicitation。** `install` tool 一樣跳兩層對話框，和 Claude Code 版一樣，文字由模型用你的語言寫，事實部分維持英文。
- **沒有 `default_source` 設定。** 預設是 `stars`，要搜公開的或兩者都搜，直接在 prompt 裡說。
- **scope：**

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 專案的 `.agents/skills/`，並自動加進 `.gitignore` | — | — |
| `project` | 專案的 `.agents/skills/`，會進 git | — | — |
| `user` | `~/.agents/skills/` | `codex plugin add`（`~/.codex/config.toml`） | `codex mcp add`（`~/.codex/config.toml`） |

`codex plugin add` 和 `codex mcp add` 沒有 scope 參數，所以 plugin 和 MCP 只能裝在 user。如果 Codex 沒有提供 session 所在的專案，skill 也只能選 `user`。

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
| `install_skill.py` | 把 skill 資料夾複製到指定 scope 的 skills 目錄，來源 commit 記在 `.kirby.json`。加上 `--check` 只列出會安裝的內容，不會寫入；`--commit` 只安裝對話框顯示的那個 commit。由 mod 和 Codex 的 MCP server 呼叫 |

`detect.py --agent codex` 會先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 會裝到 `.agents/skills/`。

## 開發

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
