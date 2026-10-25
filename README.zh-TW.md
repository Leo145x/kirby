# kirby

[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)

從你的 GitHub star 和 star list，或公開的 GitHub 搜尋，找出合適的 skill、plugin 或 MCP server，經你確認後安裝到你選的 scope。

內容分成兩部分：

- **`inhale` skill**：搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），判斷、推薦合適的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`）：提供安裝用的 tool `mcp__kirby__install`。透過這個 tool 安裝時，會先跳兩層對話框等你決定。skill 會要求模型只用這個 tool 安裝，但這只是指示，不是硬性攔截：模型仍然可以用 Bash 直接執行 `claude mcp add` 之類的安裝指令。

只支援 Claude Code。

## 需求

- 已登入的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`

## 安裝

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

## 使用

直接問就行，例如：

- 「有沒有能畫架構圖的 skill？」
- 「從我的 AI Tools list 找 code review 的工具」
- 「從公開的 GitHub 找能查 postgres 的 MCP」

也可以用 `/kirby:inhale` 直接叫用。模型也可能在任務需要時自己使用這個 skill，但不保證每次都會。

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

對話框的語言跟著 Claude Code 的 `language` 設定（例如 `"zh-TW"`、`"繁體中文"`），沒設定時看 `LC_ALL` 或 `LANG`。支援英文、繁體中文、簡體中文，其他語言顯示英文。

### 安裝和 prompt cache

依照 [官方文件](https://code.claude.com/docs/en/prompt-caching)，以及這個專案的實測結果：

- **skill**：裝完後 cache 沒有 miss（實測）。
- **MCP**：`claude mcp add` 要重開 session 才會生效，這個 session 的 cache 不受影響。
- **plugin**：要用 `/reload-plugins` 載入。plugin 裡的 skill、hook 等不影響 cache。如果 plugin 帶有 MCP server，而且 session 的 tool search 是關閉的（預設是開著），載入後 cache 會重建一次。遇到這種情況，Claude Code 會先警告，要加 `--force` 才會套用（實測）。

對話框的 scope 那一層會附上對應的提醒。

## 腳本

都在 `skills/inhale/scripts/`。前三個是唯讀的，skill 執行時不會詢問你：

| 腳本 | 用途 |
| --- | --- |
| `stars.py` | 讀取你的 star 和 star list（GraphQL），快取在 `~/.cache/kirby/stars.json`，24 小時更新一次 |
| `public.py` | 依 agent 工具類的 topic 搜尋公開的 GitHub repo |
| `detect.py` | 判斷 repo 是 marketplace、plugin、skill 還是 MCP server，以及安裝需要的資訊 |
| `install_skill.py` | 把 skill 資料夾複製到指定 scope 的 skills 目錄，來源 commit 記在 `.kirby.json`。加上 `--check` 只列出會安裝的內容，不會寫入。由 mod 呼叫 |

## 開發

```
claude plugin validate .
claude plugin test .
```

## License

[MIT](LICENSE)
