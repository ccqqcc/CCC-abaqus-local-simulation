# Agent 宿主环境对 Abaqus 子进程的影响（实测诊断与边界）

适用范围：agent 有本机命令执行权限，但运行在带**进程注入**或**进程级文件系统隔离**的宿主中（例如 WorkBuddy/Cursor 一类带沙箱的桌面 agent）。本文件只讲"调用能否成立"，不改变任何物理/材料/验收合同。普通本机直跑、无注入宿主可忽略本文件。

## 1. 为什么 doctor 要先看 host_injection

`doctor` 现在返回 `host_injection` 字段，用 Toolhelp32 枚举**当前 python 进程**加载的模块，命中 `tsbx.dll`/`sandbox`/`inject` 等即列为 `suspects`。

- 命中 `tsbx.dll`：宿主会向**它启动的每个子进程**注入 DLL。Abaqus 的 `pre.exe`/`standard.exe`/`explicit.exe` 加载后可能以 `0xc0000409`（fail-fast）崩溃，或出现难以解释的文件可见性错误。
- 这是**宿主证据**，不是"这个模型一定失败"的判决；但它解释了"零错误却求解失败"这一类怪象。遇到 `suspects` 时，真实求解优先在没有注入的宿主（用户本机终端/直连 MCP）执行。
- 检测是只读的，不改配置、不提交作业、不关闭宿主沙箱。

`doctor` 现在同时返回 `solve_readiness`，给出**提交前裁决**：

| verdict | suitable | 含义 |
|---|---|---|
| `BLOCKED_BY_AGENT_INJECTION` | false | 当前进程检出注入 DLL；不要在此宿主提交真实求解，改用 plan/审计/ODB后处理 |
| `READY_LICENSE_UNVERIFIED` | true | 未检出注入且 launcher 存在；许可证签出仍未验证，先用 `doctor --query-release` |
| `NO_LAUNCHER` | false | 配置的 launcher 不存在，修配置 |
| `UNSUPPORTED_HOST` | false | 非 Windows，超出已验证范围 |

"未检出注入"**不等于**子进程环境干净：检测只覆盖当前 python 进程可见的 DLL。该裁决只是静态宿主判断，不证明许可证可用，也不证明模型有效。

诊断顺序：先 `doctor` 看 `solve_readiness.verdict` 和 `host_injection.suspects`；失败后用 `triage --workdir <dir> --job <name>`（或 MCP `abaqus_triage_job`）得到单一 `root_cause`；两者都指向模型才怀疑模型/数值本身。

## 2. `terminal_evidence.exception_kinds` 的根因分类

Abaqus 在 solver rank 异常退出时写 `<job>.<seq>.exception`。有些失败（特别是 Standard 的部件映射交接）**只有这里有痕迹**：`.dat` 可以是零错误、`.log` 可以正常走到 END OF USER INPUT PROCESSING、PROBLEM SIZE 正确，但 ODB 没有帧。

`terminal_evidence()` 现在解析这些文件并给出 `exception_kinds`：

| kind | 典型 Details | 含义/处理 |
|---|---|---|
| `PART_MAP_HANDOFF` | `part map file ... does not exist / corrupt` | Standard 的 `.prt` 部件映射文件没有被 solver 读到；常见于进程级 FS 隔离或 scratch 交接断裂。不要改材料/网格去"修"它 |
| `FAIL_FAST_INJECTED_HOST` | `0xc0000409` / fail-fast | 宿主注入 DLL 导致子进程 fail-fast；与模型无关，换无注入宿主 |
| `ACCESS_VIOLATION` | `0xc0000005` | solver 段错误；可能与注入、内存或 Abaqus 本身有关，查 callstack 与事件日志再判 |
| `EXTERNAL_INTERRUPT` | `INTERRUPT/ABORT signal` | 外部终止（墙时策略、用户 kill 或宿主回收）；不是数值不收敛 |

`exception_files` 里保留原始 `description`/`details`/`phases` 供复核。判据是证据，不等于通用因果诊断。

## 2b. 一键归类：`triage`

手动拼 `.dat`、`.msg`、`.exception` 容易顾此失彼。用 `triage --workdir <job目录> --job <job名>`（MCP：`abaqus_triage_job`）把证据归为**一个** `root_cause`；它只读文件，不改模型、不重启作业。`status` 对受管作业也会自动带同一份 `triage`。

| root_cause | 触发证据 | confidence |
|---|---|---|
| `HOST_SANDBOX_DEFECT` | `PART_MAP_HANDOFF`/`FAIL_FAST_INJECTED_HOST` 异常；或 access violation + 检出注入 | HIGH/MEDIUM |
| `EXTERNAL_INTERRUPT` | `.exception` 报 ABORT/INTERRUPT 信号 | HIGH |
| `MODEL_INPUT_ERROR` | `.dat` 有 `***ERROR` | HIGH |
| `LICENSE_UNAVAILABLE` | 日志出现 license 相关文本 | MEDIUM |
| `NUMERICAL_CONVERGENCE` | minimum increment / too many increments / negative eigenvalues / excessive distortion | MEDIUM |
| `SOLVER_CRASH_UNATTRIBUTED` | access violation 但当前进程未检出注入 | MEDIUM |
| `SUSPECTED_HOST_SANDBOX` | 有注入 + abort 标记，但无明确 solver 证据 | LOW |
| `NO_FAILURE_EVIDENCE` | 存在完成标记；不要把 rc0/完成当成峰 | LOW |
| `UNDETERMINED` | 无决定性证据；空 ODB 本身不能说明原因 | LOW |

优先级：显式 solver 异常 > `.dat` 输入错误 > license/数值标记 > 注入嫌疑 > undetermined。每种结果都带 `basis`、`evidence_summary`、`recommended_action`。这是启发式归类，不证明模型正确。

真实样本：`SPLIT_G9` → `HOST_SANDBOX_DEFECT` / HIGH；`CT_ANALYTIC` → `EXTERNAL_INTERRUPT` / HIGH。

## 3. 注入/隔离宿主下的调用要点（本机实测）

以下不是普遍真理，是本机 Abaqus 2023 + 带注入沙箱宿主上的实测现象，遇到同类症状时按此排查：

1. **绝对路径 `input=` 在 `cmd /d /s /c` 包装下可能失败**：solver 报 `could not be located: <绝对路径>.inp`，即使该文件在 agent 视图中存在。可先 `cd`/`cwd` 到 job 目录，用**相对文件名** `input=<job>.inp` 再试。这是调用路径问题，不要改 INP 内容。
2. **`.prt` 交接失败是进程级 FS 隔离的表现**：`pre.exe` 写部件映射文件，另一个子进程（`standard.exe`）在隔离视图里读不到，表现为 `PART_MAP_HANDOFF`。与 `scratch` 位置、`cpus`、模型无关；已知成功的输入在同宿主同法重报同一错误即可证伪"模型问题"。
3. **`scratch` 必须预先存在**：不存在的 scratch 子目录会让 launcher 直接拒绝，和隔离是两件事，先排除。
4. **真实求解交给无注入宿主**：用户本机终端、或不注入的直连 MCP 执行 `submit`。带注入宿主适合做 `plan`/输入审计/既有 ODB 的 `probe`（`abaqus python` 读 ODB 通常可用，因为不启动 solver 子进程链）。
5. **不要因为 launcher 返回 0 或 `.dat` 无错误就认为求解成功**：以 `terminal_evidence` 的完成标记 + ODB 帧/SDEG 证据为准。

## 4. 能力边界

- 本文件不提供"关闭宿主沙箱""绕过注入"的通用方法；那属于宿主配置，不由本 skill 决定。
- 升级本 skill 代码后，历史 `RUNNING`/`SUPERVISOR_FAILED` 记录的密封哈希会与新代码不一致；这些 stale 记录本来就要求 reconciliation，不得直接当作可续跑作业。
- 注入检测只覆盖当前 python 进程；如果 solver 经另一条链启动（不同父进程），需在那条链上另行验证。
