# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)

跟你的 agent 說要什麼工具，kirby 就從你的 GitHub star 裡找出合適的 skill、plugin 或 MCP server，並在你確認前先檢查它會裝進什麼。

## 用途

kirby 做兩件事，一前一後。

**幫你找到工具。** 你在 GitHub 上 star 了一堆 agent 工具，也整理成 star list。任務需要時，直接在 Claude Code 或 Codex 裡問：kirby 會搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），推薦適合這個任務的工具，並安裝你選的那個，不用離開 session。

**裝之前先幫你檢查。** 安裝對話框出現前，kirby 會先看過要裝的東西：掃描檔案、查詢工具本身和相依套件有沒有已知漏洞或惡意套件，有發現時再請模型審查檔案。每項發現都會列在對話框裡，讓你清楚自己裝的是什麼。安裝仍然只要按一下；只有已知的惡意套件會擋下來。

## 功能

### 找工具

- **優先搜尋你的 star**：你的 GitHub star 和 star list、公開的 GitHub（有 agent 工具類 topic 的 repo），或兩者一起。
- **推薦合適的工具**：模型依你的任務判斷每個候選，每個 repo 都附上 star 數和最後 push 的日期。
- **知道要裝的是什麼**：分辨 marketplace、plugin、skill 和 MCP server，以及安裝需要什麼。

### 安裝前檢查

- **掃描實際要安裝的檔案**：skill 的檔案、plugin 自己的檔案（在另一個 repo 也一樣），或 MCP server 指令所執行的已發布 npm、PyPI 套件（只下載，不安裝也不執行）。找的是值得留意的模式，例如隱藏 Unicode、針對模型的語句、網路呼叫或機密環境變數。這只是 pattern 比對，不是安全審查；被標出的那一行在做什麼，可以直接問模型。
- **查詢已知漏洞和惡意套件**：查工具本身和它的相依套件，來源是 OSV.dev，以及 repo 自己在 GitHub 發布的 advisory。
- **有發現時請模型審查檔案**：掃描或查詢找到 danger 或 warn 的發現時，由一個只能讀檔的 subagent（Claude Code 裡是 kirby 的審查 agent）回報最多五項發現，並標為模型回報。
- **每項發現一行，附上嚴重度**：danger、warn 或 info。沒能執行的部分會標 unchecked，不會當成沒找到；什麼都沒找到的工具只有一行 `check: nothing found`。
- **預設按一下就能裝**：任何發現都不會要你多做一步。只有已知的惡意套件會擋下安裝。
- **裝的就是你看到的**：skill 安裝對話框顯示的那個 commit，即使 repo 之後有新的 commit；plugin 裝完若發現 marketplace 不在檢查過的 commit，會再移除；MCP server 的指令會鎖定在檢查過的套件版本（它的相依套件不會）。

### 安裝

- **安裝前先問你**：要在對話框選「安裝」才會安裝，也可以先看 README 或換一個。接著選 scope：`local`、`project` 或 `user`。
- **用你的語言**：對話框用你使用的語言寫。其中的事實由 kirby 自己寫，有英文、繁體中文和简体中文；模型只選語言。
- **不影響 prompt cache**：在 Claude Code 裡，安裝 skill、plugin 或 MCP server 都不會讓 prompt cache 失效（實測）。唯一的例外是帶有 MCP server 的 plugin，在 tool search 關閉時用 `/reload-plugins` 載入；這種情況對話框會註明，Claude Code 在 reload 前也會先警告。
- **支援 Claude Code 和 Codex**。

## 需求

- 已登入的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`（要讀 `uv.lock` 和 `pyproject.toml` 需 3.11 以上）
- 選用：`npm` 和 `uv`，讓查詢能算出沒有 lockfile 的相依套件版本；沒有的話只用名稱查詢

## 快速開始

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

然後直接問就行，例如：

- 「有沒有能畫架構圖的 skill？」
- 「從我的 AI Tools list 找 code review 的工具」
- 「從公開的 GitHub 找能查 postgres 的 MCP」

在 Claude Code 也可以用 `/kirby:inhale` 叫用。

## 進一步了解

[說明文件](docs/guide.zh-TW.md) 有完整細節：搜尋來源設定；安裝前檢查，包括每個部分檢查什麼、嚴重度、什麼會擋下安裝、模型審查，以及哪些有鎖定；安裝流程每一步和各 scope 裝到哪裡；prompt cache；Codex 版的差異；以及腳本。

## 開發

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
