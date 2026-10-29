# kirby 说明

[English](guide.md) | [繁體中文](guide.zh-TW.md) | 简体中文

[README](../README.zh-CN.md) 背后的细节：kirby 的组成、怎么搜索、安装前检查做了什么、安装每一步在做什么，以及 Codex 版的差异。

## 组成

kirby 分为三部分：

- **`inhale` skill**：搜索你的 star 和 star list（也可以搜索公开的 GitHub），判断并推荐合适的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安装用的 tool `mcp__kirby__install`、两个供模型审查用的只读 tool（`mcp__kirby__check` 不弹对话框、只运行安装前检查，`mcp__kirby__file` 从检查读取的位置读取单个文件），以及只能使用这两个 tool 的审查 agent `kirby:reviewer`。kirby 让这两个只读 tool 不经权限询问就运行。通过安装 tool 安装时，会先弹出两层对话框等你决定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜索用的 tool、同样的 `check` 和 `file` tool，以及同样会弹出两层对话框的 `install` tool。

skill 会要求模型只用这些 tool 安装，但这只是指示，不是硬性拦截：模型仍然可以自己执行 `claude mcp add`、`codex mcp add` 之类的安装命令。

## 搜索

在 Claude Code 也可以用 `/kirby:inhale` 直接调用。模型也可能在任务需要时自行使用这个 skill，但不保证每次都会。

每个 repo 都会附上 star 数和最后 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 默认搜索来源

可选 `stars`（默认）、`public`、`both`，在 `/config` 里 kirby 的 `default_source` 设置。每次也可以在 prompt 里直接指定，例如“从公开的找”。

公开搜索只会找到带有 agent 工具类 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

## 安装前检查

第一层安装对话框出现之前，kirby 会先检查要安装的东西，让你知道自己装的是什么。检查分为四个部分：

- **pattern 扫描**：拿要安装的文件匹配固定的文本模式。
- **漏洞查询**：查工具本身和它依赖的包有没有已公开的漏洞和安全公告（advisory）。
- **恶意包查询**：查工具本身或它依赖的包是不是已知的恶意包。
- **模型审查**：由模型读取文件，报告看起来有害的地方。只有其他部分有发现时才会运行。

检查不会安装任何东西，也不会运行工具的任何代码。查询只用除了你的 `gh` 登录之外不需要任何密钥的公开服务：[OSV.dev](https://osv.dev) 和 GitHub。检查的发现会列在第一层对话框，每个结果也都会把同样的发现交给模型，你可以直接问它某一项。

### 各类工具检查的对象

**skill。** 对话框显示的那个 commit 里的 skill 文件夹，也就是实际要安装的那份文件。扫描读取这些文件；查询读取其中的依赖文件，也查这个 commit 本身。

**plugin。** 按它在 marketplace 里的条目所写的来源检查，用的是 marketplace 的 commit（你已经添加的 marketplace 用的是哪个 commit，见下面的“哪些有锁定”）：

- **marketplace repo 里的文件夹**（`"source": "./plugins/x"`）：检查那个文件夹，commit 就是对话框显示的那个。
- **另一个 GitHub repo**（`github`、`url` 或 `git-subdir`）：条目有 `sha` 时，检查那个 repo 的这个 commit。没有 `sha` 时检查它当前的样子，对话框会注明来源没有锁定，实际安装的可能和检查的不同。
- **其他来源**（npm 包、压缩包、命令、GitHub 以外的 git 主机）：不会获取，所以扫描和两项查询都是 unchecked。

对话框的 `source:` 那行会说明是哪一种。之后扫描和查询跟 skill 一样运行在这些文件上。plugin 可以依赖其他 plugin，agent CLI 会把它们一起装上。kirby 不检查这些 plugin，对话框用一行 `installed along with it, not checked:` 列出。

**MCP server。** MCP server 每次启动时运行的是它的命令获取的包（`npx -y <package>`、`uvx <package>`），所以检查的是那个包，不是 repo 的文件：

- **哪个包。** repo 只用来得知它写了哪些包：`server.json` 的 `packages`，其次是 `package.json`（不含 private 的）的 `name`，再其次是 `pyproject.toml` 的 name，位置可以在根目录或往下最多两层文件夹，所以一个 repo 放了好几个 server 也行。kirby 检查其中命令实际运行的那一个：交给 `npx`、`uvx` 这类工具运行的那个包（`--package` 或 `--from` 的值，否则是工具和它的选项之后的第一个词），而不是命令行上更后面的词，那些是传给该包的参数。命令指定的是范围时，例如 `pkg@^1.2` 或 `pkg>=1,<2`，kirby 取 registry 上符合该范围的最高版本，检查并锁定那个版本。包和 repo 之间没有任何绑定（MCP registry 验证的是包和 server 名称的对应，不是和 repo 的对应），所以对话框的 `package:` 那行会写明是哪个文件写了它，并注明没有验证它出自这个 repo。
- **哪个版本。** 命令指定的版本（`pkg@1.2.3`、`pkg==1.2.3`，或 `pkg@next` 这类 tag）；没有的话用 `server.json` 给的版本；再没有就用 registry 上的最新版。
- **检查什么。** 那个版本的 npm tarball，或它适用所有平台的 PyPI wheel（没有的话用 sdist），从 registry 下载、和 registry 给的 hash 比对后，解开到一个临时文件夹：只解出普通文件，不会写到那个文件夹之外，也不会安装、import 或运行其中任何东西。扫描运行在这些文件上。查询则查包本身的这个版本，以及它的依赖，版本的算法和 skill 一样（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。repo 自己发布的安全公告，只算写到这个包或没写任何包的那些。

发现的位置是包里的路径。模型有那个包的 `check` tool 响应时，会用 `file` tool 从检查过的包读取（见下面的模型审查）；否则它会告诉你去哪里看那个文件（npm 用 unpkg，PyPI 用 inspector.pypi.io）。

### pattern 扫描

扫描会读取每个要检查的文件，查找值得留意的模式。任何文件里的：隐藏 Unicode（`hidden-unicode`）、针对模型的语句（`injection-phrase`）、提到 agent 配置文件（`agent-config`）和凭据文件（`credentials`），以及很长的 base64 字符串（`long-base64`）。Markdown 里的：范围很广的 `allowed-tools`（`broad-tools`）和 HTML 注释（`html-comment`）。脚本里的：网络调用（`network`）、shell 执行（`exec`）、解码（`decode`）、读取机密环境变量（`env-secret`）和修改 shell 启动文件（`startup-files`）。二进制文件和超过 2 MB 的文件不扫描，扫描那行会写明有几个。

同一个工具在任何文件里匹配到 `network`，又匹配到 `env-secret`、`exec` 或 `decode` 时，会再多一项组合发现，写明是哪两条规则：`send-secrets`（可能把机密发送出去）、`download-run`（可能下载并运行代码）和 `download-decode`（可能下载并解码一段内容）。

对话框先列组合发现，再列每条匹配到的规则和位置。这只是 pattern 匹配，不是安全审查：有发现不代表有害，没有发现也不代表安全。tool 也会把这些发现和扫描的 commit 交给模型，你可以直接问它某一行在做什么；模型用 kirby 的只读 `file` tool 读取那个 commit 的那个文件。

### 漏洞查询和恶意包查询

- **依赖包。** 对于 skill 和 plugin，查询读取检查文件里的 `package-lock.json`（或 `package.json`）、`uv.lock`、`requirements.txt` 和 `pyproject.toml`；对于 MCP server，则是安装那个版本的包时会一并装上的依赖。没有 lockfile 时，用 `npm install --package-lock-only --ignore-scripts` 或 `uv pip compile --no-build` 算出版本，不会安装任何东西，也不会运行包的代码（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。这时对话框会注明版本是检查时算出的，实际运行时可能不同。没有 npm 或 uv 时只知道包名，恶意包查询仍会按包名查，漏洞查询则是 unchecked。`package.json`，或 MCP server 运行的包，有来自 git、URL 或本地路径的依赖时也一样：npm 为了算出版本会去拉取它，而构建 git 依赖时可能运行它的 `prepare` 脚本，所以这时 kirby 不运行 npm。
- **漏洞查询。** 向 OSV.dev 查每个依赖包的那个版本，以及检查对象本身：检查的那个 commit（OSV 会把 commit 对应到记录里的 git 范围），或 MCP server 那个版本的包。向 GitHub 查 repo 为自己发布的安全公告。
- **恶意包查询。** 查 OSV.dev 里 id 以 `MAL-` 开头的记录，这些来自 OpenSSF Malicious Packages；检查对象本身和每个依赖包都会查。

### 严重度

每项发现前面都标着严重度，表示它值得多少关注：

| 严重度 | 哪些发现 |
| --- | --- |
| `danger` | 已知的恶意包（这一种还会拦下安装，见下方）；依赖包有 critical 或 high 的漏洞；OSV 对应到检查的这个 commit 的任何记录；MCP server 的包本身的任何安全公告 |
| `warn` | 扫描规则 `hidden-unicode`、`injection-phrase`、`credentials`、`startup-files`，这些在正常的工具里较少见；组合发现；依赖包的其他漏洞；无法对应到检查的 commit 或包的 repo 安全公告，对话框会说无法判断它是否有影响；模型审查的每一项发现 |
| `info` | 其他扫描规则 |

有了组合发现，读取机密再发送出去的工具就不会全部只是 `info`，尽管这几条规则单独匹配到时都是 `info`（[ADR 0005](adr/0005-one-click-by-default.md)）。扫描部分，组合发现和 warn 的规则排在前面；查询部分，恶意包排在最前面，接着是检查对象本身的安全公告，再是评级最严重的依赖包。

### 拦下安装

只有已知的恶意包会拦下安装：恶意包查询在 OpenSSF Malicious Packages 里找到工具本身或它的某个依赖包。这时对话框会显示 `blocked:`，只剩取消、先看 README 和换一个，模型会告诉你原因，也不会做模型审查。仍然要装的话，只能自己手动安装。其他情况都不会拦：pattern 扫描的发现、漏洞和模型审查的发现不论多严重，都由你判断，因为很多正常的工具也会请求 URL、执行 shell 命令，或依赖有已知 CVE 的包（[ADR 0001](adr/0001-block-only-on-confirmed-malware.md)）。

### unchecked

没能运行的部分会显示为 `unchecked` 并附上原因，不会当成没找到，“安装”也仍然可选：

- 查询失败或超时；
- 算不出版本的依赖包的漏洞查询（没有 npm 或 uv、它们运行失败，或有些包不是来自 npm registry）；
- 第十个之后的依赖文件的两项查询，kirby 不读这些文件；那行会写明有几个、是哪些；
- 来源不在 GitHub 上，或 kirby 拉取不到来源 repo 的 plugin（扫描和两项查询）；
- 列出你的 marketplace 失败时，某个 marketplace 是否已经添加过；以及在 Codex 里，kirby 读不到你已添加的 marketplace 停在哪个 commit 时：检查的是 repo 当前的状态，安装后若 kirby 无法确认 plugin 来自那个 commit，就会再把它移除；
- kirby 解不开的 MCP server 压缩包（加密了，或用了 Python 读不了的压缩方式）：扫描；
- 用 container image（`docker run …`）运行或通过 URL 连接的远程 MCP server、没写任何 npm 或 PyPI 包的 repo，以及命令运行的不是 repo 写的任何包：一行 `unchecked:` 说明原因，命令保持原样；
- kirby 无法确定会拿到哪个版本的 MCP server（registry 没有响应、没有版本符合命令指定的范围，或 kirby 读不懂那个范围）：对话框会显示 `not pinned:`，扫描是 unchecked，只用包名做恶意包查询；
- 在 Claude Code 里，GitHub 没有响应，无法判断你已经添加的 marketplace 是否落后于它的 repo；
- 该做却没做成的模型审查（见下面的模型审查）。

### 默认点一下就能装

这个检查是为了让你知道自己装的是什么，不是为了让安装变麻烦（[ADR 0005](adr/0005-one-click-by-default.md)）。kirby 遇到的每个限制都只是对话框里的一行，不会因此拒绝安装，也不会多一个步骤：没能运行的部分、没有锁定的版本、只是 repo 自称是自己的包、安装时会一并更新的 marketplace，都是如此。唯一的例外是拦下安装。

检查什么都没找到、也没有没扫到或没查成的部分时，只有一行，例如 `check: nothing found (12 files, 3 npm dependencies, advisory and malware lookups)`；否则每个部分各自列出。

kirby 能自己多做一些事来省掉一个步骤时，就会去做：repo 之后有了新的 commit，skill 仍安装对话框显示的那个；plugin 则是在安装后检查，而不是事先拒绝（见下面的“哪些有锁定”）。

### 模型审查

扫描或查询找到 `danger` 或 `warn` 的发现（包括组合发现）时，还会由模型读取文件，报告看起来有害的地方（[ADR 0002](adr/0002-model-review-in-a-subagent.md)）。什么都没找到、或只有 `info` 发现的工具不做审查，所以不必多等，也不多花 token。被拦下的安装也不做：反正不会提供“安装”。

- **流程。** 调用安装 tool 之前，模型先调用 `check` tool：它不弹对话框，运行同样的安装前检查，说明需不需要审查、文件在哪里（检查的那个 commit 的 repo，或 MCP server 的包）、是哪些文件。需要审查时，模型启动一个 subagent：Claude Code 用 Agent tool 启动 kirby 的审查 agent `kirby:reviewer`，Codex 用它的多 agent tool 启动 subagent，并给它 skill 里固定的提示。subagent 只通过 `file` tool 读取那个 commit 或那个包里的文件，也不会被告知其他检查找到什么，所以是独立审查。接着模型调用安装 tool，传入审查结果和检查给出的 sha。
- **Claude Code 的审查 agent。** `kirby:reviewer` 只能使用 `check` 和 `file`，所以即使被审查的文件里有针对它的指令，它也没有 Bash 或写入的 tool 可以滥用。它的指示是它自己的；模型只告诉它文件在哪里、是哪些。kirby 的 hook 让 `check` 和 `file` 不经权限询问就运行，其他 tool 一律不放行：这两个 tool 只读取 GitHub 和包的内容，不会写入你的电脑。你的设置或组织设置里的 deny 规则仍然会拦下它们。在 Codex 里，这些 tool 声明自己只读取，所以 Codex 直接运行、不先询问。
- **审查的对象。** 就是要安装的东西：skill 的文件、plugin 的来源（在另一个 repo 也一样），MCP server 则是检查时解开的已发布包。读取包时，`file` 会重新下载同一个归档文件，比对 registry 的哈希和检查给出的 sha256，再解开到临时文件夹；里面的东西都不会安装或运行。
- **结果。** 最多 5 项发现，每项是检查列出的某个文件、行号，以及一句不超过 120 个字符、不引用文件内容的理由；或是附上理由的 `could_not_run`。安装 tool 会检查这个结构、去掉隐藏字符和控制字符；不符合的结果在任何对话框出现前就会被拒绝，让模型重新发送。
- **在对话框里。** 每项发现是一行 `warn`，排在检查的各行之后，标上 `(model review, as reported by the model)`；没有发现时则用一行说明。审查的发现只会增加：不会移除或降低其他发现，也不会拦下安装。
- **没有审查。** 需不需要审查由安装 tool 按自己的检查决定。需要却没有传入、审查无法运行，或审查读取的不是检查的那个 commit 或包时，对话框用一行 `model review: unchecked (…)` 说明，“安装”仍然保留。

结果是由模型转交的，kirby 无法证明审查途中没有被改动、也确实做了，所以这些发现都标为模型报告。

### 哪些有锁定

在每类工具允许的范围内，装的就是你看到的那一份：

| 类型 | 有锁定 | 没有锁定 |
| --- | --- | --- |
| skill | 它的文件，锁定在对话框显示的 commit | 没有 lockfile 的依赖包：版本是检查时算出的，skill 运行时可能不同 |
| plugin | marketplace 的 commit，安装后检查；另一个 repo 的来源，在 marketplace 条目给了 `sha` 时 | 没有 `sha` 的另一个 repo 来源；跟着一起装的 plugin；没有 lockfile 的依赖包，和 skill 一样 |
| MCP server | 命令运行的包，锁定在检查过的版本 | 这个包的依赖（[#13](https://github.com/Leo145x/kirby/issues/13)）；container image，以及 kirby 无法确定版本的命令，这些都按原样安装 |

**skill。** 文件是 kirby 自己复制的，所以 skill 会安装对话框显示的那个 commit，即使在实际安装前 repo 有了新的 commit 也一样：你不必再回答一次对话框（[ADR 0005](adr/0005-one-click-by-default.md)）。只有那个 commit 已经获取不到时（force-push 可能把它移除），安装才会失败；不会安装任何东西，结果会说明原因，你仍然想装的话，模型会重新弹出对话框，显示当前的 commit。

**plugin。** 锁定的是 marketplace 的 commit（[ADR 0003](adr/0003-verify-plugin-commit-after-adding-marketplace.md)）：

- **两个 CLI 都一样**：两边都没有 kirby 能用的方式安装指定的 commit，所以安装 tool 在你还没添加 marketplace 时照常添加（不指定 ref），安装 plugin，再读取 marketplace 的 clone 在哪个 commit。不是检查过的那个 commit，就把 plugin 移除并说明原因；marketplace 保留。
- **Claude Code**，已经添加 marketplace：Claude Code 从落后于 repo 的 marketplace 安装时会先更新它。所以 kirby 检查的是 repo 当前的 commit，也就是安装会带来的那个，对话框会说明：`installs from it as it is`，或 `behind its repo; installing refreshes it to <commit>`。kirby 读不到你的 marketplace 所在的 commit 时，不会说 `behind its repo`，只说读不到那个 commit，以及安装会把它更新到检查过的 commit。kirby 无法判断它是否落后时（GitHub 没有响应），对话框会用一行 `unchecked:` 说明，检查的则是你的 marketplace 当前所在的 commit。
- **Codex**，已经添加 marketplace：`codex plugin add` 不会更新它，所以 kirby 检查它当前所在的 commit，并从它安装。

**MCP server。** 命令会改写成检查过的版本（`npx -y pkg@1.2.3`、`uvx pkg==1.2.3`），对话框显示的就是改写后的命令。只有那个包会锁定：它的依赖通常写成版本范围，版本是检查时算出的，server 启动时 npm 或 uv 可能会选到别的版本。对话框的 `pinned:` 那行会注明。所以 MCP server 不像 skill 那样，装的就是检查过的那一份。

## 安装流程

你选定要安装的 repo 后，mod 会弹出两层对话框：

1. **下一步**：取消 / 先看 README / 换一个 / 安装。对话框会列出类型、commit、文件数、包含的脚本和安装前检查的结果（见上方）。检查拦下安装时，不会提供“安装”。
2. **scope**（选择“安装”后才会出现）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.claude/skills/`，并自动加入 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 项目的 `.claude/skills/`，会进 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/`（设置了 `CLAUDE_CONFIG_DIR` 时是 `$CLAUDE_CONFIG_DIR/skills/`） | `--scope user` | `--scope user` |

无论装在哪个 scope，plugin 的 marketplace 都会记录在 user settings 中。

### 对话框语言

对话框的文字由模型按 skill 规定的格式，用你使用的语言写。上方的事实（repo、star 数、commit、文件、脚本、已存在的文件夹、安装前检查的结果），以及 scope 问题下方的 prompt cache 提醒，由 tool 生成，固定是英文。scope 对话框的选项固定是 `cancel`、`local`、`project`、`user`。没有提供文字或格式不完整时，对话框显示英文。

### 安装与 prompt cache

根据 [官方文档](https://code.claude.com/docs/en/prompt-caching) 以及本项目的实测结果：

- **skill**：安装后 cache 没有 miss（实测）。
- **MCP**：`claude mcp add` 要重启 session 才会生效，当前 session 的 cache 不受影响。
- **plugin**：需要用 `/reload-plugins` 加载。plugin 中的 skill、hook 等不影响 cache。如果 plugin 带有 MCP server，并且 session 的 tool search 是关闭的（默认开启），加载后 cache 会重建一次。遇到这种情况，Claude Code 会先警告，要加 `--force` 才会应用（实测）。

plugin 的提醒由 tool 放在 scope 那一层对话框。MCP 的提醒交给模型：skill 要求它写在第一层对话框。

## Codex

同一个 repo 也是 Codex plugin。Codex 读取 `.codex-plugin/plugin.json`，加载 Codex 版的 skill（`codex/skills/inhale/`）和一个 MCP server（`codex/server.py`，只用 Python 标准库，配置在 `mcp.json`）。Claude Code 的 mod 在 Codex 中不会用到。

和 Claude Code 版的差异：

- **搜索和读取文件走 MCP tool。** server 的 `stars`、`public`、`detect` 会运行同一批脚本，`readme` 和 `file` 从 GitHub 读取 README 或某个 commit 的单个文件（模型审查时也从 MCP server 的包读取），`check` 不弹对话框、只运行安装前检查，全都在 Codex 的 sandbox 外运行，所以不会每次都请求联网权限。这六个 tool 声明自己只读取，在 Codex 默认的审批设置下，Codex 会直接运行、不先询问。kirby 的 `install` 运行前，Codex 仍会先问；选「Always allow」会记住。
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
| `install_skill.py` | 把 skill 文件夹复制到指定 scope 的 skills 目录，来源 commit 记录在 `.kirby.json`。加上 `--check` 只列出将要安装的内容、扫描和查询结果，不会写入（加上 `--json` 时，对话框的那几行是 `lines`，告诉模型的内容是 `note`，`review` 说明要不要做模型审查、读取哪些文件）；`--commit` 安装对话框显示的那个 commit，即使 repo 之后又有新的 commit。由 mod 和 Codex 的 MCP server 调用 |
| `check_plugin.py` | marketplace plugin 的安装前检查：获取 marketplace（已经添加的用 `--commit` 指定它所在的 commit），按 plugin 的来源找到它的文件，再运行扫描和查询。输出 JSON，也含上述的 `review`；不会安装任何东西。由 mod 和 Codex 的 MCP server 调用 |
| `check_mcp.py` | MCP server 的安装前检查：`check_mcp.py owner/repo '<mcp_args 的 JSON>'` 找出 repo 写的、命令实际运行的包，下载并解开那个版本（不安装），再运行扫描和查询。输出 JSON，其中 `mcp_args` 是锁定在那个版本的命令，`review` 同上（它的 `sha` 是归档文件的 sha256）。`check_mcp.py --read '<JSON>'` 为 `file` tool 打印这种包里的单个文件。不会安装任何东西。由 mod 和 Codex 的 MCP server 调用 |
| `lookups.py` | `install_skill.py --check`、`check_plugin.py` 和 `check_mcp.py` 运行的漏洞查询和恶意包查询：读取依赖文件、不安装就算出版本，再向 OSV.dev 和 GitHub 查询。不会单独运行 |

`detect.py --agent codex` 会先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 会装到 `.agents/skills/`。
