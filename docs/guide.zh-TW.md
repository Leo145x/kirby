# kirby 說明

[English](guide.md) | 繁體中文 | [简体中文](guide.zh-CN.md)

[README](../README.zh-TW.md) 背後的細節：kirby 的組成、怎麼搜尋、安裝前檢查做了什麼、安裝每一步在做什麼，以及 Codex 版的差異。

## 組成

kirby 分成三部分：

- **`inhale` skill**：搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），判斷、推薦合適的 skill、plugin 或 MCP server。
- **mod**（`hooks/register.ts`，Claude Code 用）：提供安裝用的 tool `mcp__kirby__install`、兩個給模型審查用的唯讀 tool（`mcp__kirby__check` 不跳對話框、只執行安裝前檢查，`mcp__kirby__file` 從檢查讀取的位置讀單一檔案），以及只能用這兩個 tool 的審查 agent `kirby:reviewer`。kirby 讓這兩個唯讀 tool 不經權限詢問就執行。透過安裝 tool 安裝時，會先跳兩層對話框等你決定。
- **MCP server**（`codex/server.py`，Codex 用）：提供搜尋用的 tool、同樣的 `check` 和 `file` tool，以及同樣會跳兩層對話框的 `install` tool。

skill 會要求模型只用這些 tool 安裝，但這只是指示，不是硬性攔截：模型仍然可以自己執行 `claude mcp add`、`codex mcp add` 之類的安裝指令。

## 搜尋

在 Claude Code 也可以用 `/kirby:inhale` 直接叫用。模型也可能在任務需要時自己使用這個 skill，但不保證每次都會。

每個 repo 都會附上 star 數和最後 push 的日期，格式是 `owner/repo ★N · pushed DATE`。

### 預設搜尋來源

可選 `stars`（預設）、`public`、`both`，在 `/config` 裡 kirby 的 `default_source` 設定。每次也可以在 prompt 裡直接指定，例如「從公開的找」。

公開搜尋只會找到有 agent 工具類 topic（`agent-skills`、`claude-code-plugin`、`mcp-server` 等）的 repo。

## 安裝前檢查

第一層安裝對話框出現前，kirby 會先檢查要安裝的東西，讓你知道自己裝的是什麼。檢查分成四個部分：

- **pattern 掃描**：拿要安裝的檔案比對固定的文字模式。
- **漏洞查詢**：查工具本身和它依賴的套件有沒有已公開的漏洞和安全公告（advisory）。
- **惡意套件查詢**：查工具本身或它依賴的套件是不是已知的惡意套件。
- **模型審查**：由模型讀檔案，回報看起來有害的地方。只有其他部分有發現時才會執行。

檢查不會安裝任何東西，也不會執行工具的任何程式碼。查詢只用除了你的 `gh` 登入之外不需要任何金鑰的公開服務：[OSV.dev](https://osv.dev) 和 GitHub。檢查的發現會列在第一層對話框，每個結果也都會把同樣的發現交給模型，你可以直接問它某一項。

### 各種工具檢查的對象

**skill。** 對話框顯示的那個 commit 裡的 skill 資料夾，也就是實際要安裝的那份檔案。掃描讀這些檔案；查詢讀其中的相依套件檔案，也查這個 commit 本身。

**plugin。** 依它在 marketplace 裡的條目所寫的來源檢查，用的是 marketplace 的 commit（你已經加入的 marketplace 用的是哪個 commit，見下面的「哪些有鎖定」）：

- **marketplace repo 裡的資料夾**（`"source": "./plugins/x"`）：檢查那個資料夾，commit 就是對話框顯示的那個。
- **另一個 GitHub repo**（`github`、`url` 或 `git-subdir`）：條目有 `sha` 時，檢查那個 repo 的這個 commit。沒有 `sha` 時檢查它目前的樣子，對話框會註明來源沒有鎖定，實際安裝的可能和檢查的不同。
- **其他來源**（npm 套件、壓縮檔、指令、GitHub 以外的 git 主機）：不會抓取，所以掃描和兩項查詢都是 unchecked。

對話框的 `source:` 那行會說是哪一種。之後掃描和查詢跟 skill 一樣跑在這些檔案上。plugin 可以依賴其他 plugin，agent CLI 會把它們一起裝上。kirby 不檢查這些 plugin，對話框用一行 `installed along with it, not checked:` 列出。

**MCP server。** MCP server 每次啟動時執行的是它的指令抓到的套件（`npx -y <package>`、`uvx <package>`），所以檢查的是那個套件，不是 repo 的檔案：

- **哪個套件。** repo 只用來得知它寫了哪些套件：`server.json` 的 `packages`，其次是 `package.json`（不含 private 的）的 `name`，再其次是 `pyproject.toml` 的 name，位置可以在根目錄或往下最多兩層資料夾，所以一個 repo 放了好幾個 server 也行。kirby 檢查其中指令實際執行的那一個：交給 `npx`、`uvx` 這類工具執行的那個套件（`--package` 或 `--from` 的值，否則是工具和它的選項之後的第一個字），而不是指令列上更後面的字，那些是傳給該套件的參數。指令指定的是範圍時，例如 `pkg@^1.2` 或 `pkg>=1,<2`，kirby 取 registry 上符合該範圍的最高版本，檢查並鎖定那個版本。套件和 repo 之間沒有任何綁定（MCP registry 驗證的是套件和 server 名稱的對應，不是和 repo 的對應），所以對話框的 `package:` 那行會寫出是哪個檔案寫了它，並註明沒有驗證它出自這個 repo。
- **哪個版本。** 指令指定的版本（`pkg@1.2.3`、`pkg==1.2.3`，或 `pkg@next` 這類 tag）；沒有的話用 `server.json` 給的版本；再沒有就用 registry 上的最新版。
- **檢查什麼。** 那個版本的 npm tarball，或它適用所有平台的 PyPI wheel（沒有的話用 sdist），從 registry 下載、和 registry 給的 hash 比對後，解開到一個暫存資料夾：只解出一般檔案，不會寫到那個資料夾之外，也不會安裝、import 或執行其中任何東西。掃描跑在這些檔案上。查詢則查套件本身的這個版本，以及它的相依套件，版本的算法和 skill 一樣（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。repo 自己發布的安全公告，只算有寫到這個套件或沒寫任何套件的那些。

發現的位置是套件裡的路徑。模型有那個套件的 `check` tool 回應時，會用 `file` tool 從檢查過的套件讀取（見下面的模型審查）；否則它會告訴你去哪裡看那個檔案（npm 用 unpkg，PyPI 用 inspector.pypi.io）。

### pattern 掃描

掃描會讀每個要檢查的檔案，找值得留意的模式。任何檔案裡的：隱藏 Unicode（`hidden-unicode`）、針對模型的語句（`injection-phrase`）、提到 agent 設定檔（`agent-config`）和憑證檔（`credentials`），以及很長的 base64 字串（`long-base64`）。Markdown 裡的：範圍很廣的 `allowed-tools`（`broad-tools`）和 HTML 註解（`html-comment`）。腳本裡的：網路呼叫（`network`）、shell 執行（`exec`）、解碼（`decode`）、讀取機密環境變數（`env-secret`）和修改 shell 啟動檔（`startup-files`）。二進位檔和超過 2 MB 的檔案不掃描，掃描那行會寫出有幾個。

同一個工具在任何檔案裡比對到 `network`，又比對到 `env-secret`、`exec` 或 `decode` 時，會再多一項組合發現，寫出是哪兩條規則：`send-secrets`（可能把機密送出去）、`download-run`（可能下載並執行程式碼）和 `download-decode`（可能下載並解碼一段內容）。

對話框先列組合發現，再列每條比對到的規則和位置。這只是 pattern 比對，不是安全審查：有發現不代表有害，沒有發現也不代表安全。tool 也會把這些發現和掃描的 commit 交給模型，你可以直接問它某一行在做什麼；模型用 kirby 的唯讀 `file` tool 讀那個 commit 的那個檔案。

### 漏洞查詢和惡意套件查詢

- **相依套件。** skill 和 plugin 的話，查詢讀取檢查檔案裡的 `package-lock.json`（或 `package.json`）、`uv.lock`、`requirements.txt` 和 `pyproject.toml`；MCP server 的話，則是安裝那個版本的套件時會一併裝上的相依套件。沒有 lockfile 時，用 `npm install --package-lock-only --ignore-scripts` 或 `uv pip compile --no-build` 算出版本，不會安裝任何東西，也不會執行套件的程式碼（[ADR 0004](adr/0004-resolve-dependencies-without-installing.md)）。這時對話框會註明版本是檢查當下算出的，實際執行時可能不同。沒有 npm 或 uv 時只知道套件名稱，惡意套件查詢仍會用名稱查，漏洞查詢則是 unchecked。`package.json`，或 MCP server 執行的套件，有來自 git、URL 或本機路徑的相依套件時也一樣：npm 為了算出版本會去抓它，而建置 git 相依套件時可能執行它的 `prepare` 腳本，所以這時 kirby 不執行 npm。
- **漏洞查詢。** 向 OSV.dev 查每個相依套件的那個版本，以及檢查對象本身：檢查的那個 commit（OSV 會把 commit 對到記錄裡的 git 範圍），或 MCP server 那個版本的套件。向 GitHub 查 repo 為自己發布的安全公告。
- **惡意套件查詢。** 查 OSV.dev 裡 id 以 `MAL-` 開頭的記錄，這些來自 OpenSSF Malicious Packages；檢查對象本身和每個相依套件都會查。

### 嚴重度

每項發現前面都標著嚴重度，表示它值得多少注意：

| 嚴重度 | 哪些發現 |
| --- | --- |
| `danger` | 已知的惡意套件（這一種還會擋下安裝，見下方）；相依套件有 critical 或 high 的漏洞；OSV 對到檢查的這個 commit 的任何記錄；MCP server 的套件本身的任何安全公告 |
| `warn` | 掃描規則 `hidden-unicode`、`injection-phrase`、`credentials`、`startup-files`，這些在正常的工具裡較少見；組合發現；相依套件的其他漏洞；無法對到檢查的 commit 或套件的 repo 安全公告，對話框會說無法判斷它是否有影響；模型審查的每一項發現 |
| `info` | 其他掃描規則 |

有組合發現，讀取機密再送出去的工具就不會全部只是 `info`，雖然這幾條規則單獨比對到時都是 `info`（[ADR 0005](adr/0005-one-click-by-default.md)）。掃描的部分，組合發現和 warn 的規則排在前面；查詢的部分，惡意套件排最前面，接著是檢查對象本身的安全公告，再來是評級最嚴重的相依套件。

### 擋下安裝

只有已知的惡意套件會擋下安裝：惡意套件查詢在 OpenSSF Malicious Packages 裡找到工具本身或它的某個相依套件。這時對話框會顯示 `blocked:`，只剩取消、先看 README 和換一個，模型會告訴你原因，也不會做模型審查。仍然要裝的話，只能自己手動安裝。其他情況都不會擋：pattern 掃描的發現、漏洞和模型審查的發現不論多嚴重，都由你判斷，因為很多正常的工具也會抓 URL、執行 shell 指令，或依賴有已知 CVE 的套件（[ADR 0001](adr/0001-block-only-on-confirmed-malware.md)）。

### unchecked

沒能執行的部分會顯示為 `unchecked` 並附上原因，不會當成沒找到，「安裝」也仍然可選：

- 查詢失敗或逾時；
- 算不出版本的相依套件的漏洞查詢（沒有 npm 或 uv、它們執行失敗，或有些套件不是來自 npm registry）；
- 第十個之後的相依套件檔案的兩項查詢，kirby 不讀這些檔案；那行會寫出有幾個、是哪些；
- 來源不在 GitHub 上，或 kirby 抓不到來源 repo 的 plugin（掃描和兩項查詢）；
- 列出你的 marketplace 失敗時，某個 marketplace 是否已經加過；以及在 Codex 裡，kirby 讀不到你已加過的 marketplace 停在哪個 commit 時：檢查的是 repo 目前的樣子，安裝後若 kirby 無法確認 plugin 來自那個 commit，就會再把它移除；
- kirby 解不開的 MCP server 壓縮檔（加密了，或用了 Python 讀不了的壓縮方式）：掃描；
- 用 container image（`docker run …`）執行或用 URL 連線的遠端 MCP server、沒寫任何 npm 或 PyPI 套件的 repo，以及指令執行的不是 repo 寫的任何套件：一行 `unchecked:` 說明原因，指令維持原樣；
- kirby 無法確定會拿到哪個版本的 MCP server（registry 沒有回應、沒有版本符合指令指定的範圍，或 kirby 讀不懂那個範圍）：對話框會顯示 `not pinned:`，掃描是 unchecked，只用套件名稱做惡意套件查詢；
- 在 Claude Code 裡，GitHub 沒有回應，無法判斷你已經加入的 marketplace 是否落後於它的 repo；
- 該做卻沒做成的模型審查（見下面的模型審查）。

### 預設按一下就能裝

這個檢查是為了讓你知道自己裝的是什麼，不是為了讓安裝變麻煩（[ADR 0005](adr/0005-one-click-by-default.md)）。kirby 遇到的每個限制都只是對話框裡的一行，不會因此拒絕安裝，也不會多一個步驟：沒能執行的部分、沒有鎖定的版本、只是 repo 自稱是自己的套件、安裝時會一併更新的 marketplace，都是如此。唯一的例外是擋下安裝。

檢查什麼都沒找到、也沒有沒掃到或沒查成的部分時，只有一行，例如 `check: nothing found (12 files, 3 npm dependencies, advisory and malware lookups)`；否則每個部分各自列出。

kirby 能自己多做一些事來省掉一個步驟時，就會去做：repo 之後有新的 commit，skill 仍安裝對話框顯示的那個；plugin 則是在安裝後檢查，而不是事先拒絕（見下面的「哪些有鎖定」）。

### 模型審查

掃描或查詢找到 `danger` 或 `warn` 的發現（包括組合發現）時，還會由模型讀檔案，回報看起來有害的地方（[ADR 0002](adr/0002-model-review-in-a-subagent.md)）。什麼都沒找到、或只有 `info` 發現的工具不做審查，所以不必多等，也不多花 token。被擋下的安裝也不做：反正不會提供「安裝」。

- **流程。** 呼叫安裝 tool 之前，模型先呼叫 `check` tool：它不跳對話框，執行同樣的安裝前檢查，說明需不需要審查、檔案在哪裡（檢查的那個 commit 的 repo，或 MCP server 的套件）、是哪些檔案。需要審查時，模型啟動一個 subagent：Claude Code 用 Agent tool 啟動 kirby 的審查 agent `kirby:reviewer`，Codex 用它的多 agent tool 啟動 subagent，並給它 skill 裡固定的提示。subagent 只透過 `file` tool 讀那個 commit 或那個套件裡的檔案，也不會被告知其他檢查找到什麼，所以是獨立審查。接著模型呼叫安裝 tool，傳入審查結果和檢查給的 sha。
- **Claude Code 的審查 agent。** `kirby:reviewer` 只能用 `check` 和 `file`，所以即使被審查的檔案裡有針對它的指令，它也沒有 Bash 或寫入的 tool 可以濫用。它的指示是它自己的；模型只告訴它檔案在哪裡、是哪些。kirby 的 hook 讓 `check` 和 `file` 不經權限詢問就執行，其他 tool 一律不放行：這兩個 tool 只讀 GitHub 和套件內容，不會寫入你的電腦。你的設定或組織設定裡的 deny 規則仍然會擋下它們。在 Codex 裡，這些 tool 宣告自己只讀取，所以 Codex 直接執行、不先詢問。
- **審查的對象。** 就是要安裝的東西：skill 的檔案、plugin 的來源（在另一個 repo 也一樣），MCP server 則是檢查時解開的已發布套件。讀套件時，`file` 會重新下載同一個封存檔，比對 registry 的雜湊和檢查給的 sha256，再解開到暫存資料夾；裡面的東西都不會安裝或執行。
- **結果。** 最多 5 項發現，每項是檢查列出的某個檔案、行號，以及一句不超過 120 個字元、不引用檔案內容的理由；或是附上理由的 `could_not_run`。安裝 tool 會檢查這個結構、去掉隱藏字元和控制字元；不符合的結果在任何對話框出現前就會被拒絕，讓模型重新送出。
- **在對話框裡。** 每項發現是一行 `warn`，排在檢查的各行之後，標上 `(model review, as reported by the model)`；沒有發現時則用一行說明。審查的發現只會增加：不會移除或降低其他發現，也不會擋下安裝。
- **沒有審查。** 需不需要審查由安裝 tool 依自己的檢查決定。需要卻沒有傳入、審查無法執行，或審查讀的不是檢查的那個 commit 或套件時，對話框用一行 `model review: unchecked (…)` 說明，「安裝」仍然保留。

結果是由模型轉交的，kirby 無法證明審查途中沒被改過、也確實做了，所以這些發現都標為模型回報。

### 哪些有鎖定

在每種工具允許的範圍內，裝的就是你看到的那一份：

| 種類 | 有鎖定 | 沒有鎖定 |
| --- | --- | --- |
| skill | 它的檔案，鎖定在對話框顯示的 commit | 沒有 lockfile 的相依套件：版本是檢查時算出的，skill 執行時可能不同 |
| plugin | marketplace 的 commit，安裝後檢查；另一個 repo 的來源，在 marketplace 條目有給 `sha` 時 | 沒有 `sha` 的另一個 repo 來源；跟著一起裝的 plugin；沒有 lockfile 的相依套件，和 skill 一樣 |
| MCP server | 指令執行的套件，鎖定在檢查過的版本 | 這個套件的相依套件（[#13](https://github.com/Leo145x/kirby/issues/13)）；container image，以及 kirby 無法確定版本的指令，這些都照原樣安裝 |

**skill。** 檔案是 kirby 自己複製的，所以 skill 會安裝對話框顯示的那個 commit，即使在實際安裝前 repo 有了新的 commit 也一樣：你不必再回答一次對話框（[ADR 0005](adr/0005-one-click-by-default.md)）。只有那個 commit 已經抓不到時（force-push 可能把它移除），安裝才會失敗；不會安裝任何東西，結果會說明原因，你仍然想裝的話，模型會重新跳出對話框，顯示目前的 commit。

**plugin。** 鎖定的是 marketplace 的 commit（[ADR 0003](adr/0003-verify-plugin-commit-after-adding-marketplace.md)）：

- **兩個 CLI 都一樣**：兩邊都沒有 kirby 能用的方式安裝指定的 commit，所以安裝 tool 在你還沒加入 marketplace 時照常加入（不指定 ref），安裝 plugin，再讀 marketplace 的 clone 在哪個 commit。不是檢查過的那個 commit，就把 plugin 移除並說明原因；marketplace 保留。
- **Claude Code**，已經加入 marketplace：Claude Code 從落後於 repo 的 marketplace 安裝時會先更新它。所以 kirby 檢查的是 repo 目前的 commit，也就是安裝會帶來的那個，對話框會說明：`installs from it as it is`，或 `behind its repo; installing refreshes it to <commit>`。kirby 讀不到你的 marketplace 所在的 commit 時，不會說 `behind its repo`，只說讀不到那個 commit，以及安裝會把它更新到檢查過的 commit。kirby 無法判斷它是否落後時（GitHub 沒有回應），對話框會用一行 `unchecked:` 說明，檢查的則是你的 marketplace 目前所在的 commit。
- **Codex**，已經加入 marketplace：`codex plugin add` 不會更新它，所以 kirby 檢查它目前所在的 commit，並從它安裝。

**MCP server。** 指令會改寫成檢查過的版本（`npx -y pkg@1.2.3`、`uvx pkg==1.2.3`），對話框顯示的就是改寫後的指令。只有那個套件會鎖定：它的相依套件通常寫成版本範圍，版本是檢查時算出的，server 啟動時 npm 或 uv 可能會挑到別的版本。對話框的 `pinned:` 那行會註明。所以 MCP server 不像 skill 那樣，裝的就是檢查過的那一份。

## 安裝流程

你選定要裝的 repo 後，mod 會跳兩層對話框：

1. **下一步**：取消 / 先看 README / 換一個 / 安裝。對話框會列出種類、commit、檔案數、內含的腳本和安裝前檢查的結果（見上方）。檢查擋下安裝時，不會提供「安裝」。
2. **scope**（選了「安裝」才會出現）：

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | 專案的 `.claude/skills/`，並自動加進 `.gitignore` | `--scope local`（`.claude/settings.local.json`） | `--scope local` |
| `project` | 專案的 `.claude/skills/`，會進 git | `--scope project`（`.claude/settings.json`） | `--scope project`（`.mcp.json`） |
| `user` | `~/.claude/skills/`（有設 `CLAUDE_CONFIG_DIR` 時是 `$CLAUDE_CONFIG_DIR/skills/`） | `--scope user` | `--scope user` |

plugin 不論裝在哪個 scope，它的 marketplace 都會記錄在 user settings。

### 對話框語言

對話框的文字由模型依 skill 規定的格式，用你使用的語言寫。上方的事實（repo、star 數、commit、檔案、腳本、已存在的資料夾、安裝前檢查的結果），以及範圍問題下方的 prompt cache 提醒，由 tool 產生，固定是英文。範圍對話框的選項固定是 `cancel`、`local`、`project`、`user`。沒有提供文字或格式不完整時，對話框顯示英文。

### 安裝和 prompt cache

依照 [官方文件](https://code.claude.com/docs/en/prompt-caching)，以及這個專案的實測結果：

- **skill**：裝完後 cache 沒有 miss（實測）。
- **MCP**：`claude mcp add` 要重開 session 才會生效，這個 session 的 cache 不受影響。
- **plugin**：要用 `/reload-plugins` 載入。plugin 裡的 skill、hook 等不影響 cache。如果 plugin 帶有 MCP server，而且 session 的 tool search 是關閉的（預設是開著），載入後 cache 會重建一次。遇到這種情況，Claude Code 會先警告，要加 `--force` 才會套用（實測）。

plugin 的提醒由 tool 放在 scope 那一層對話框。MCP 的提醒交給模型：skill 要求它寫在第一層對話框。

## Codex

同一個 repo 也是 Codex plugin。Codex 讀 `.codex-plugin/plugin.json`，載入 Codex 版的 skill（`codex/skills/inhale/`）和一個 MCP server（`codex/server.py`，只用 Python 標準函式庫，設定在 `mcp.json`）。Claude Code 的 mod 在 Codex 不會用到。

和 Claude Code 版的差異：

- **搜尋和讀檔走 MCP tool。** server 的 `stars`、`public`、`detect` 會執行同一批腳本，`readme` 和 `file` 從 GitHub 讀取 README 或某個 commit 的單一檔案（模型審查時也從 MCP server 的套件讀），`check` 不跳對話框、只執行安裝前檢查，全都在 Codex 的 sandbox 外執行，所以不會每次都要求連網權限。這六個 tool 宣告自己只讀取，在 Codex 預設的核准設定下，Codex 會直接執行、不先詢問。kirby 的 `install` 執行前，Codex 仍會先問；選「Always allow」會記住。
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
| `install_skill.py` | 把 skill 資料夾複製到指定 scope 的 skills 目錄，來源 commit 記在 `.kirby.json`。加上 `--check` 只列出會安裝的內容、掃描和查詢結果，不會寫入（加上 `--json` 時，對話框的那幾行是 `lines`，告訴模型的內容是 `note`，`review` 說明要不要做模型審查、讀哪些檔案）；`--commit` 安裝對話框顯示的那個 commit，即使 repo 之後又有新的 commit。由 mod 和 Codex 的 MCP server 呼叫 |
| `check_plugin.py` | marketplace plugin 的安裝前檢查：抓取 marketplace（已經加入的用 `--commit` 指定它所在的 commit），依 plugin 的來源找到它的檔案，再執行掃描和查詢。輸出 JSON，也含上述的 `review`；不會安裝任何東西。由 mod 和 Codex 的 MCP server 呼叫 |
| `check_mcp.py` | MCP server 的安裝前檢查：`check_mcp.py owner/repo '<mcp_args 的 JSON>'` 找出 repo 寫的、指令實際執行的套件，下載並解開那個版本（不安裝），再執行掃描和查詢。輸出 JSON，其中 `mcp_args` 是鎖定在那個版本的指令，`review` 同上（它的 `sha` 是封存檔的 sha256）。`check_mcp.py --read '<JSON>'` 為 `file` tool 印出這種套件裡的單一檔案。不會安裝任何東西。由 mod 和 Codex 的 MCP server 呼叫 |
| `lookups.py` | `install_skill.py --check`、`check_plugin.py` 和 `check_mcp.py` 執行的漏洞查詢和惡意套件查詢：讀取相依套件檔案、不安裝就算出版本，再向 OSV.dev 和 GitHub 查詢。不會單獨執行 |

`detect.py --agent codex` 會先找 Codex 的 marketplace（`.agents/plugins/marketplace.json`）；`install_skill.py --agent codex` 會裝到 `.agents/skills/`。
