# kirby

[English](README.md) | [繁體中文](README.zh-TW.md) | 简体中文

从你的 GitHub star 和 star list，或公开的 GitHub 搜索中，找出合适的 skill、plugin 或 MCP server，经你确认后安装到你选择的 scope。

内容分为三部分：

- **`inhale` skill**：搜索你的 star 和 star list（也可以搜索公开的 GitHub），判断并推荐合适的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安装用的 tool `mcp__kirby__install`。通过这个 tool 安装时，会先弹出两层对话框等你决定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜索用的 tool，以及同样会弹出两层对话框的 `install` tool。

skill 会要求模型只用这些 tool 安装，但这只是指示，不是硬性拦截：模型仍然可以自己执行 `claude mcp add`、`codex mcp add` 之类的安装命令。

支持 Claude Code 和 Codex，Codex 版的差异见 [Codex](#codex)。

## 依赖

- 已登录的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`

## 安装

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

直接问就行，例如：

- “有没有能画架构图的 skill？”
- “从我的 AI Tools list 找 code review 的工具”
- “从公开的 GitHub 找能查 postgres 的 MCP”

在 Claude Code 也可以用 `/kirby:inhale` 直接调用。模型也可能在任务需要时自行使用这个 skill，但不保证每次都会。

每个 repo 都会附上 star 数和最后 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 默认搜索来源

可选 `stars`（默认）、`public`、`both`，在 `/config` 里 kirby 的 `default_source` 设置。每次也可以在 prompt 里直接指定，例如“从公开的找”。

公开搜索只会找到带有 agent 工具类 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

### 安装流程

你选定要安装的 repo 后，mod 会弹出两层对话框：

1. **下一步**：取消 / 先看 README / 换一个 / 安装。对话框会列出类型、commit、文件数、包含的脚本和扫描结果。
2. **scope**（选择“安装”后才会出现）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.claude/skills/`，并自动加入 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 项目的 `.claude/skills/`，会进 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/` | `--scope user` | `--scope user` |

无论装在哪个 scope，plugin 的 marketplace 都会记录在 user settings 中。

在第一个对话框出现前，tool 会扫描 skill 的文件（就是实际要安装的那份），查找值得留意的模式：Markdown 里的隐藏 Unicode、HTML 注释和针对模型的语句；范围很广的 `allowed-tools`；提到 agent 配置文件和凭据文件；以及脚本里的网络调用、shell 执行、解码、读取机密环境变量和修改 shell 启动文件。对话框会列出每条命中的规则和位置。这只是 pattern 匹配，不是安全审查：有命中不代表有害，没命中也不代表安全。plugin 和 MCP server 不会扫描，对话框会注明。tool 也会把命中位置和扫描的 commit 交给模型，你可以直接问它某一行在做什么。

skill 只会安装对话框显示的那个 commit。如果在实际安装前 repo 有了新的 commit，就不会安装；模型会告诉你，你仍然想装的话，它会重新弹出对话框，显示新的 commit。plugin 和 MCP server 没有锁定版本：plugin 安装的是安装时 marketplace 里的版本，MCP server 则是每次启动时运行它的命令所获取的代码，例如 `npx -y <package>`。

对话框的文字由模型按 skill 规定的格式，用你使用的语言写。上方的事实（repo、star 数、commit、文件、脚本、已存在的文件夹、扫描结果），以及 scope 问题下方的 prompt cache 提醒，由 tool 生成，固定是英文。scope 对话框的选项固定是 `cancel`、`local`、`project`、`user`。没有提供文字或格式不完整时，对话框显示英文。

### 安装与 prompt cache

根据 [官方文档](https://code.claude.com/docs/en/prompt-caching) 以及本项目的实测结果：

- **skill**：安装后 cache 没有 miss（实测）。
- **MCP**：`claude mcp add` 要重启 session 才会生效，当前 session 的 cache 不受影响。
- **plugin**：需要用 `/reload-plugins` 加载。plugin 中的 skill、hook 等不影响 cache。如果 plugin 带有 MCP server，并且 session 的 tool search 是关闭的（默认开启），加载后 cache 会重建一次。遇到这种情况，Claude Code 会先警告，要加 `--force` 才会应用（实测）。

plugin 的提醒由 tool 放在 scope 那一层对话框。MCP 的提醒交给模型：skill 要求它写在第一层对话框。

## Codex

同一个 repo 也是 Codex plugin。Codex 读取 `.codex-plugin/plugin.json`，加载 Codex 版的 skill（`codex/skills/inhale/`）和一个 MCP server（`codex/server.py`，只用 Python 标准库，配置在 `mcp.json`）。Claude Code 的 mod 在 Codex 中不会用到。

和 Claude Code 版的差异：

- **搜索走 MCP tool。** server 的 `stars`、`public`、`detect`、`readme`、`file` 会在 Codex 的 sandbox 外运行同一批脚本，所以每次搜索不会请求联网权限。在 Codex 默认的审批设置下，Codex 仍会先问是否允许 kirby 运行该 tool；选「Always allow」会记住。
- **对话框是 MCP elicitation。** `install` tool 同样弹出两层对话框，和 Claude Code 版一样，文字由模型用你的语言写，事实部分保持英文。
- **没有 `default_source` 设置。** 默认是 `stars`，要搜索公开的或两者都搜，直接在 prompt 里说。
- **scope：**

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.agents/skills/`，并自动加入 `.gitignore` | — | — |
| `project` | 项目的 `.agents/skills/`，会进 git | — | — |
| `user` | `~/.agents/skills/` | `codex plugin add`（`~/.codex/config.toml`） | `codex mcp add`（`~/.codex/config.toml`） |

`codex plugin add` 和 `codex mcp add` 没有 scope 参数，所以 plugin 和 MCP 只能装在 user。如果 Codex 没有提供 session 所在的项目，skill 也只能选 `user`。

装完后，开新的 Codex session 才能使用。

Codex 也读得懂 Claude Code 格式的 marketplace。plugin 来自这种 marketplace 时，对话框的事实会列出 marketplace 文件，skill 也要求模型提醒：只为 Claude Code 写的部分（例如 hooks）可能无法运行。

如果只说「安装 owner/repo」，Codex 可能改用它内置的 `skill-installer` 安装，不会经过 kirby 的对话框（实测遇到过）。它请求运行那个安装程序时，可以拒绝，再请它改用 kirby 安装。

## 脚本

都在 `skills/inhale/scripts/`。前三个是只读的，skill 执行时不会询问你：

| 脚本 | 用途 |
| --- | --- |
| `stars.py` | 读取你的 star 和 star list（GraphQL），缓存在 `~/.cache/kirby/stars.json`，24 小时更新一次 |
| `public.py` | 按 agent 工具类 topic 搜索公开的 GitHub repo |
| `detect.py` | 判断 repo 是 marketplace、plugin、skill 还是 MCP server，以及安装所需的信息 |
| `install_skill.py` | 把 skill 文件夹复制到指定 scope 的 skills 目录，来源 commit 记录在 `.kirby.json`。加上 `--check` 只列出将要安装的内容和扫描结果，不会写入；`--commit` 只安装对话框显示的那个 commit。由 mod 和 Codex 的 MCP server 调用 |

`detect.py --agent codex` 会先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 会装到 `.agents/skills/`。

## 开发

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
