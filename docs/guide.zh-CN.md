# kirby 说明

[English](guide.md) | [繁體中文](guide.zh-TW.md) | 简体中文

[README](../README.zh-CN.md) 背后的细节：kirby 的组成、安装每一步在做什么，以及 Codex 版的差异。

## 组成

kirby 分为三部分：

- **`inhale` skill**：搜索你的 star 和 star list（也可以搜索公开的 GitHub），判断并推荐合适的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安装用的 tool `mcp__kirby__install`。通过这个 tool 安装时，会先弹出两层对话框等你决定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜索用的 tool，以及同样会弹出两层对话框的 `install` tool。

skill 会要求模型只用这些 tool 安装，但这只是指示，不是硬性拦截：模型仍然可以自己执行 `claude mcp add`、`codex mcp add` 之类的安装命令。

## 搜索

在 Claude Code 也可以用 `/kirby:inhale` 直接调用。模型也可能在任务需要时自行使用这个 skill，但不保证每次都会。

每个 repo 都会附上 star 数和最后 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 默认搜索来源

可选 `stars`（默认）、`public`、`both`，在 `/config` 里 kirby 的 `default_source` 设置。每次也可以在 prompt 里直接指定，例如“从公开的找”。

公开搜索只会找到带有 agent 工具类 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

## 安装流程

你选定要安装的 repo 后，mod 会弹出两层对话框：

1. **下一步**：取消 / 先看 README / 换一个 / 安装。对话框会列出类型、commit、文件数、包含的脚本和安装前检查的结果（下面的扫描和查询）。检查什么都没找到、也没有没扫到或没查成的部分时，只有一行，例如 `check: nothing found (12 files, 3 npm dependencies, advisory and malware lookups)`；否则每个部分各自列出。恶意包查询找到已知的恶意包时，不会提供“安装”。
2. **scope**（选择“安装”后才会出现）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.claude/skills/`，并自动加入 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 项目的 `.claude/skills/`，会进 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/`（设置了 `CLAUDE_CONFIG_DIR` 时是 `$CLAUDE_CONFIG_DIR/skills/`） | `--scope user` | `--scope user` |

无论装在哪个 scope，plugin 的 marketplace 都会记录在 user settings 中。

### 扫描

在第一个对话框出现前，tool 会扫描 skill 的文件（就是实际要安装的那份），查找值得留意的模式：Markdown 里的隐藏 Unicode、HTML 注释和针对模型的语句；范围很广的 `allowed-tools`；提到 agent 配置文件和凭据文件；以及脚本里的网络调用、shell 执行、解码、读取机密环境变量和修改 shell 启动文件。对话框会列出每条命中的规则和位置，前面标上严重度：`hidden-unicode`、`injection-phrase`、`credentials`、`startup-files` 在正常的 skill 里较少见，标 `warn`，其他标 `info`；`warn` 的规则排在前面。同一个工具在任何文件里命中 `network`，又命中 `env-secret`、`exec` 或 `decode` 时，会再多一项标 `warn` 的发现，写明是哪两条规则：`send-secrets`（可能把机密发送出去）、`download-run`（可能下载并运行代码）和 `download-decode`（可能下载并解码一段内容）。这几条规则单独命中时仍是 `info`，所以读取机密再发送出去的 skill 不会全部只是 `info`（[ADR 0005](adr/0005-one-click-by-default.md)）；这些发现排在最前面。这只是 pattern 匹配，不是安全审查：有命中不代表有害，没命中也不代表安全，所以任何命中都不会拦下安装。plugin 的文件也用同样的方式扫描（见下面的 plugin）；MCP server 不会扫描，对话框会注明。tool 也会把命中位置和扫描的 commit 交给模型，你可以直接问它某一行在做什么。在 Claude Code 里，模型用 `gh api` 读取那个文件，skill 没有预先允许这个命令，所以除非你的权限模式允许，Claude Code 会先询问你。

### 漏洞查询和恶意包查询

对 skill 和 plugin，安装前检查还会查询已公开的漏洞和已知的恶意包，只用除了你的 `gh` 登录之外不需要任何密钥的公开服务：[OSV.dev](https://osv.dev) 和 GitHub。

- **依赖包。** tool 读取 skill 在锁定 commit 的 `package-lock.json`（或 `package.json`）、`uv.lock`、`requirements.txt` 和 `pyproject.toml`。没有 lockfile 时，用 `npm install --package-lock-only --ignore-scripts` 或 `uv pip compile --no-build` 算出版本，不会安装任何东西，也不会运行包的代码（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。这时对话框会注明版本是检查时算出的，实际运行时可能不同。没有 npm 或 uv 时只知道包名，恶意包查询仍会按包名查，漏洞查询则标为 unchecked。
- **漏洞查询。** 向 OSV.dev 查每个依赖包的那个版本，以及锁定的 commit 本身（OSV 会把 commit 对应到记录里的 git 范围）；向 GitHub 查 repo 为自己发布的 advisory。依赖包有 critical 或 high 的漏洞，或 OSV 对应到这个 commit 的任何记录，是 `danger`；其他漏洞是 `warn`，无法对应到这个 commit 的 repo advisory 也是 `warn`，对话框会说无法判断它是否影响这个 commit。
- **恶意包查询。** OSV.dev 里 id 以 `MAL-` 开头的记录，来自 OpenSSF Malicious Packages。查到就是 `danger`，而且会**拦下**安装：第一层对话框只剩取消、先看 README 和换一个，模型会告诉你原因。仍然要装的话，只能自己手动安装。其他情况都不会拦：扫描命中和漏洞不论多严重，都由你判断（[ADR 0001](adr/0001-block-only-on-confirmed-malware.md)）。
- **unchecked。** 查询失败或超时，会显示为 `unchecked`，不会当成没找到，“安装”也仍然可选。

每个结果都会把同样的发现交给模型，你可以直接问它某一项。MCP server 目前还不会查询。

### plugin

plugin 按它在 marketplace 里的条目所写的来源检查，用的是 marketplace 的 commit：

- **marketplace repo 里的文件夹**（`"source": "./plugins/x"`）：检查那个文件夹，commit 就是对话框显示的那个。
- **另一个 GitHub repo**（`github`、`url` 或 `git-subdir`）：条目有 `sha` 时，检查那个 repo 的这个 commit。没有 `sha` 时检查它当前的样子，对话框会注明来源没有锁定，实际安装的可能和检查的不同。
- **其他来源**（npm 包、压缩包、命令、GitHub 以外的 git 主机）：不会获取，对话框会把扫描和两项查询标为 unchecked。

对话框的 `source:` 那行会说明是哪一种。之后扫描和查询跟 skill 一样运行在这些文件上，查到已知的恶意包也同样会拦下安装。

### 锁定 commit

skill 会安装对话框显示的那个 commit，即使在实际安装前 repo 有了新的 commit 也一样：kirby 会自己去获取那个 commit，你不必再回答一次对话框（[ADR 0005](adr/0005-one-click-by-default.md)）。只有那个 commit 已经获取不到时（force-push 可能把它移除），安装才会失败；不会安装任何东西，结果会说明原因，你仍然想装的话，模型会重新弹出对话框，显示当前的 commit。plugin 则从对话框显示的 marketplace commit 安装（见下方）。MCP server 没有锁定版本：它每次启动时运行的是它的命令所获取的代码，例如 `npx -y <package>`。

plugin 锁定的是 marketplace 的 commit（[ADR 0003](adr/0003-verify-plugin-commit-after-adding-marketplace.md)）：

- **两边都一样**：两个 CLI 都没有 kirby 能用的方式安装指定的 commit，所以 tool 在你还没添加 marketplace 时照常添加（不指定 ref），安装 plugin，再读取 marketplace 的 clone 在哪个 commit。不是检查过的那个 commit，就把 plugin 移除并说明原因；marketplace 保留。
- **Claude Code**，已经添加 marketplace：Claude Code 从落后于 repo 的 marketplace 安装时会先更新它。所以 tool 检查的是 repo 当前的 commit，也就是安装会带来的那个，对话框会说明：`installs from it as it is`，或 `behind its repo; installing refreshes it to <commit>`。tool 无法判断它是否落后时（GitHub 没有响应），对话框会用一行 `unchecked:` 说明，检查的则是你的 marketplace 当前所在的 commit。
- **Codex**，已经添加 marketplace：`codex plugin add` 不会更新它，所以 tool 检查它当前所在的 commit，并从它安装。

plugin 可以依赖其他 plugin，这些会跟着一起安装。tool 不检查它们；对话框用一行 `installed along with it, not checked:` 列出。

### 对话框语言

对话框的文字由模型按 skill 规定的格式，用你使用的语言写。上方的事实（repo、star 数、commit、文件、脚本、已存在的文件夹、扫描和查询结果），以及 scope 问题下方的 prompt cache 提醒，由 tool 生成，固定是英文。scope 对话框的选项固定是 `cancel`、`local`、`project`、`user`。没有提供文字或格式不完整时，对话框显示英文。

### 安装与 prompt cache

根据 [官方文档](https://code.claude.com/docs/en/prompt-caching) 以及本项目的实测结果：

- **skill**：安装后 cache 没有 miss（实测）。
- **MCP**：`claude mcp add` 要重启 session 才会生效，当前 session 的 cache 不受影响。
- **plugin**：需要用 `/reload-plugins` 加载。plugin 中的 skill、hook 等不影响 cache。如果 plugin 带有 MCP server，并且 session 的 tool search 是关闭的（默认开启），加载后 cache 会重建一次。遇到这种情况，Claude Code 会先警告，要加 `--force` 才会应用（实测）。

plugin 的提醒由 tool 放在 scope 那一层对话框。MCP 的提醒交给模型：skill 要求它写在第一层对话框。

## Codex

同一个 repo 也是 Codex plugin。Codex 读取 `.codex-plugin/plugin.json`，加载 Codex 版的 skill（`codex/skills/inhale/`）和一个 MCP server（`codex/server.py`，只用 Python 标准库，配置在 `mcp.json`）。Claude Code 的 mod 在 Codex 中不会用到。

和 Claude Code 版的差异：

- **搜索和读取文件走 MCP tool。** server 的 `stars`、`public`、`detect` 会运行同一批脚本，`readme` 和 `file` 则从 GitHub 读取 README 或某个 commit 的单个文件，全都在 Codex 的 sandbox 外运行，所以不会每次都请求联网权限。这五个 tool 声明自己只读取，在 Codex 默认的审批设置下，Codex 会直接运行、不先询问。kirby 的 `install` 运行前，Codex 仍会先问；选「Always allow」会记住。
- **对话框是 MCP elicitation。** `install` tool 同样弹出两层对话框，和 Claude Code 版一样，文字由模型用你的语言写，事实部分保持英文。
- **没有 `default_source` 设置。** 默认是 `stars`，要搜索公开的或两者都搜，直接在 prompt 里说。
- **scope：**

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.agents/skills/`，并自动加入 `.gitignore` | — | — |
| `project` | 项目的 `.agents/skills/`，会进 git | — | — |
| `user` | `~/.agents/skills/` | `codex plugin add`（`~/.codex/config.toml`） | `codex mcp add`（`~/.codex/config.toml`） |

`codex plugin add` 和 `codex mcp add` 没有 scope 参数，所以 plugin 和 MCP 只能装在 user。如果 Codex 没有提供 session 所在的项目，skill 也只能选 `user`。这些情况下，第一层对话框会多一行说明装到哪里（`installs at: user …`）；scope 对话框的选项是 `cancel` 和 `install at user (…)`，相当于用 tool 自己写的文字再确认一次。

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
| `install_skill.py` | 把 skill 文件夹复制到指定 scope 的 skills 目录，来源 commit 记录在 `.kirby.json`。加上 `--check` 只列出将要安装的内容、扫描和查询结果，不会写入（加上 `--json` 时，对话框的那几行是 `check_lines`）；`--commit` 安装对话框显示的那个 commit，即使 repo 之后又有新的 commit。由 mod 和 Codex 的 MCP server 调用 |
| `check_plugin.py` | marketplace plugin 的安装前检查：获取 marketplace（已经添加的用 `--commit` 指定它所在的 commit），按 plugin 的来源找到它的文件，再运行扫描和查询。输出 JSON，不会安装任何东西。由 mod 和 Codex 的 MCP server 调用 |
| `lookups.py` | `install_skill.py --check` 和 `check_plugin.py` 运行的漏洞查询和恶意包查询：读取依赖文件、不安装就算出版本，再向 OSV.dev 和 GitHub 查询。不会单独运行 |

`detect.py --agent codex` 会先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 会装到 `.agents/skills/`。
