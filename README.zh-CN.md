# kirby

[English](README.md) | [繁體中文](README.zh-TW.md) | 简体中文

从你的 GitHub star 和 star list，或公开的 GitHub 搜索中，找出合适的 skill、plugin 或 MCP server，经你确认后安装到你选择的 scope。

内容分为两部分：

- **`inhale` skill**：搜索你的 star 和 star list（也可以搜索公开的 GitHub），判断并推荐合适的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`）：提供安装用的 tool `mcp__kirby__install`。通过这个 tool 安装时，会先弹出两层对话框等你决定。skill 会要求模型只用这个 tool 安装，但这只是指示，不是硬性拦截：模型仍然可以用 Bash 直接执行 `claude mcp add` 之类的安装命令。

只支持 Claude Code。

## 依赖

- 已登录的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`

## 安装

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

## 使用

直接问就行，例如：

- “有没有能画架构图的 skill？”
- “从我的 AI Tools list 找 code review 的工具”
- “从公开的 GitHub 找能查 postgres 的 MCP”

也可以用 `/kirby:inhale` 直接调用。模型也可能在任务需要时自行使用这个 skill，但不保证每次都会。

每个 repo 都会附上 star 数和最后 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 默认搜索来源

可选 `stars`（默认）、`public`、`both`，在 `/config` 里 kirby 的 `default_source` 设置。每次也可以在 prompt 里直接指定，例如“从公开的找”。

公开搜索只会找到带有 agent 工具类 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

### 安装流程

你选定要安装的 repo 后，mod 会弹出两层对话框：

1. **下一步**：取消 / 先看 README / 换一个 / 安装。对话框会列出类型、commit、文件数和包含的脚本。
2. **scope**（选择“安装”后才会出现）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 项目的 `.claude/skills/`，并自动加入 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 项目的 `.claude/skills/`，会进 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/` | `--scope user` | `--scope user` |

无论装在哪个 scope，plugin 的 marketplace 都会记录在 user settings 中。

对话框的语言跟随 Claude Code 的 `language` 设置（例如 `"zh-CN"`、`"简体中文"`），未设置时看 `LC_ALL` 或 `LANG`。支持英文、繁体中文、简体中文，其他语言显示英文。

### 安装与 prompt cache

根据 [官方文档](https://code.claude.com/docs/en/prompt-caching) 以及本项目的实测结果：

- **skill**：安装后 cache 没有 miss（实测）。
- **MCP**：`claude mcp add` 要重启 session 才会生效，当前 session 的 cache 不受影响。
- **plugin**：需要用 `/reload-plugins` 加载。plugin 中的 skill、hook 等不影响 cache。如果 plugin 带有 MCP server，并且 session 的 tool search 是关闭的（默认开启），加载后 cache 会重建一次。遇到这种情况，Claude Code 会先警告，要加 `--force` 才会应用（实测）。

对话框的 scope 那一层会附上相应的提醒。

## 脚本

都在 `skills/inhale/scripts/`。前三个是只读的，skill 执行时不会询问你：

| 脚本 | 用途 |
| --- | --- |
| `stars.py` | 读取你的 star 和 star list（GraphQL），缓存在 `~/.cache/kirby/stars.json`，24 小时更新一次 |
| `public.py` | 按 agent 工具类 topic 搜索公开的 GitHub repo |
| `detect.py` | 判断 repo 是 marketplace、plugin、skill 还是 MCP server，以及安装所需的信息 |
| `install_skill.py` | 把 skill 文件夹复制到指定 scope 的 skills 目录，来源 commit 记录在 `.kirby.json`。加上 `--check` 只列出将要安装的内容，不会写入。由 mod 调用 |

## 开发

```
claude plugin validate .
claude plugin test .
```

## License

[MIT](LICENSE)
