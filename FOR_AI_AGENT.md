# CJC-abaqus-local-simulation — 给 AI 代理的完整接入与执行指令

> 这份文档是写给 **AI 代理**读的，不是给人看的简介。
> 你的使用者会把它连同仓库地址一起发给你。你要按本文，在**你自己的 Windows 机器**上，
> 从零完成安装、配置、体检，并在取得授权后跑通第一个 Abaqus 作业。
>
> 全程不要向人类提问"下一步怎么做"——本文已经写全。只有在 §0.3 列出的授权节点才必须停下来等人。

---

## 0. 开始之前：目标、禁止项、授权节点

### 0.1 你的目标

按顺序完成四件事：

1. 拿到代码，确认本机有 Python 3.9+、Abaqus、可用的 launcher。
2. 用 `init-config` 生成**这台机器**的配置，用 `validate-config` 体检到 `READY` 或 `USABLE_WITH_WARNINGS`。
3. 选定一种接入方式（CLI / 本地 stdio MCP / Skill），跑通只读能力（`doctor`、`probe`）。
4. 在人类明确授权后，用 `plan → submit → status → probe` 跑通一个真实作业，并如实报告结果。

### 0.2 硬性禁止（违反任何一条立即停止并向人类报告）

- **不得**在未取得明确授权时调用 `submit` 或 `terminate`。`authorize=true` 只是调用方记录的人工授权，不是身份认证；不要自己替人类勾选。
- **不得**为了让求解器跑通而修改源 INP 的物理内容（材料参数、几何、边界条件、接触、网格）。要改也必须另建独立 attempt 并说明改动，且不得覆盖原作业。
- **不得**把候选峰、`candidate_RF`、终点最大值、平台段当成有效峰值；`PEAK_STABLE_PROVISIONAL` 默认 `usable_peak=false`。
- **不得**用目标强度反推材料参数再宣称"验证成功"。
- **不得**删除 `.lck`、清理未知 scratch、`taskkill` 非本包管理的 solver、接管历史队列。
- **不得**在带注入的沙箱宿主里声称"求解成功"。launcher 返回 0、`.dat` 零错误、文件名存在都不是成功证据。
- **不得**声称许可证已验证——`doctor` 明确写 `license_availability=UNVERIFIED`，只有一次真实授权作业才能验证。
- **不得**把原始 field 均值或单点比例当成面积/体积加权结论。
- **不得**混用 Standard 与 Explicit 的结果；同一张 INP 在两种求解器里算法不同。
- **不得**修改 `assets/local_config.json` 当成"配置好了"——那是作者本机路径示例，必须生成你自己的配置。
- **不得**把作业工作目录或 scratch 放到**系统盘**（Windows 的 C 盘）：几十 GB 临时文件会撑爆系统分区，系统盘 IO 争抢会拖慢求解甚至触发 MPI 超时。本包会在 `validate-config` 和 `plan` 两处拦截；不要为了绕过它去打开 `allow_scratch_on_system_drive=true`，除非人类明确书面批准并接受风险。scratch 必须是非系统物理盘上的绝对路径，每个 job 一个独立空子目录，不用网络盘/映射盘。

### 0.3 必须停下来等人类点头的三个节点

| 节点 | 你需要人类给出 | 你拿到后才能 |
|---|---|---|
| 提交作业 | 明确批准"这个 job 名、这些 cpus/内存、这些停止策略" | 调 `submit`，带 `plan_token`、`--authorize`、事实性的 `--authorization-note` |
| 终止作业 | 针对**这一个**受管 job 的停止授权 | 调 `terminate` |
| 启用自动停止 | `terminate_at_walltime` 或 `stop_after_confirmed_peak` 设为 true 的明确许可 | 在请求里设 true |

除此之外不要因为技术细节反复打断人类；先读文档、先探测、先诊断。

---

## 1. 获取代码与本机盘点

### 1.1 确认 Python

```powershell
Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
python --version
```

要求 **Python 3.9 或更高**的 CPython。如果 `python` 指向 Windows Store 的占位符（版本命令打开商店），改用下面任一种：

```powershell
py -3 --version
# 或直接用 Anaconda / 已安装 Python 的绝对路径，例如：
D:\anaconda3\python.exe --version
```

记下可用的绝对路径，下文记作 `$PY`。**后面所有命令都用绝对路径调用它**，不要依赖 PATH。

### 1.2 获取代码

```powershell
$ROOT = 'D:\AI_ABAQUS\CJC-abaqus-local-simulation'   # 换成你打算放的位置，路径不要含 & | < > ^ % ! 引号
git clone https://github.com/ccqqcc/CJC-abaqus-local-simulation.git $ROOT
```

不会用 git 就从 GitHub 页面 **Code → Download ZIP** 下载并解压，效果一样。

进入目录：

```powershell
Set-Location $ROOT
Get-ChildItem
```

确认至少有这些条目：`LICENSE`、`README.md`、`SKILL.md`、`FOR_FRIENDS.md`、`FOR_AI_AGENT.md`、目录 `assets/`、`references/`、`scripts/`、`tests/`、`validation/`。

### 1.3 完整性自检

```powershell
$need = @(
 'scripts\abaqus_agent.py','scripts\mcp_server.py','scripts\job_worker.py',
 'scripts\host_compat.py','scripts\odb_probe.py','scripts\history_peak.py','scripts\build_package.py',
 'SKILL.md','README.md','references\ABAQUS_CALLING_HANDBOOK.md',
 'references\HOST_COMPATIBILITY.md','references\AGENT_HOST_SANDBOX.md'
)
$missing = $need | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "缺失文件: $($missing -join ', ')" }
Write-Output "FILE_CHECK_OK count=$($need.Count)"
```

任何文件缺失就重新下载，不要凭印象补写。

### 1.4 确认 Abaqus 存在

不需要手工找——skill 会自动探测。但先确认机器确实装了 Abaqus：常见 launcher 是 `C:\SIMULIA\Commands\abaqus.bat` 或 `D:\SIMULIA\Commands\abaqus.bat`。如果没有，本包无法工作，直接如实报告给人类。

---

## 2. 按顺序读文档（不要跳过）

| 顺序 | 文件 | 你要从中得到什么 |
|---|---|---|
| 1 | `SKILL.md` | 总入口、9 条不变量、最小操作闭环、接口说明 |
| 2 | `README.md` | 能力表、本机实例说明、迁移要点、验收范围 |
| 3 | `references/HOST_COMPATIBILITY.md` | 换机器怎么配、`auto` 容量规则、降级行为、**`validate-config` 十项判定表** |
| 4 | `references/ABAQUS_CALLING_HANDBOOK.md` §1–8 | 完整本地调用工作流、精确命令形式、材料/接触/输出卡注意事项 |
| 5 | 同上 §9–11 | 峰值、能量、损伤证据规则——任何强度/损伤结论前必读 |
| 6 | `references/AGENT_HOST_SANDBOX.md` | 如果你自己运行在注入/隔离沙箱里，先读这个 |
| 7 | `references/TROUBLESHOOTING.md` | 出问题时按症状查，不必一开始就通读 |
| 8 | `references/USER_SUBROUTINES.md` | 只有用 UMAT/UINTER/VUMAT/VUINTER 时才读，编译器 ABI 不能跨版本抄 |
| 9 | `references/PROJECT_CONTRACT.md` | **只对作者那个具体 3DPC 项目有效**。不要把它里的几何、材料、目标强度套到你人类的项目上 |

读完再动手。尤其是 §5 的峰值规则，它决定了你后面能不能说"有效峰"。

---

## 3. 生成本机配置

### 3.1 定义路径变量

```powershell
$PY     = 'D:\anaconda3\python.exe'                        # §1.1 得到的绝对路径
$ROOT   = 'D:\AI_ABAQUS\CJC-abaqus-local-simulation'       # §1.2 的目录
$BRIDGE = Join-Path $ROOT 'scripts\abaqus_agent.py'
$CFG    = 'D:\AI_ABAQUS\agent_config.json'                 # 你自己选的绝对路径，不要放在仓库里
$SCRATCH = 'D:\AI_ABAQUS\scratch'                          # 必须选非系统盘（不是 C 盘）的物理盘，auto 会帮你选空闲最大的数据盘
```

所有路径必须是**绝对路径**，且不含 `& | < > ^ % !`、引号或换行。含这些字符会被安全校验拒绝，换路径，不要关校验。

### 3.2 生成配置骨架

```powershell
& $PY $BRIDGE init-config --output $CFG
```

这个命令会：
- 从环境变量、PATH、C/D/E 盘常见安装位置自动发现 `abaqus.bat`；
- 从 PATH 和常见 VS 安装位置发现编译器；
- 按本机逻辑核数和物理内存推导安全容量（留至少 1 核、15% 内存）；
- 生成 `allowed_roots`、`registry_dir`、`scratch_roots` 的建议值。

它**不会覆盖**已存在的文件；如果目标已存在会报错——先确认是不是你自己之前生成的。

### 3.3 检查并按需修改配置

```powershell
Get-Content $CFG
```

逐项核对：

| 字段 | 正确做法 |
|---|---|
| `abaqus_launcher` | 必须指向真实存在的 `abaqus.bat` / `abaqus.exe`。若为空字符串，说明自动探测失败，手工填。 |
| `allowed_roots` | 改成你**确实被授权读写**的项目根目录。所有 INP/include/ODB/work/scratch 都必须落在这些根之内。 |
| `registry_dir` | 本包自己的作业记录目录，不要指向历史 queue 文件。 |
| `scratch_roots` | 改成你打算用的 scratch 根（如 `$SCRATCH`）。该目录**必须预先存在**，否则 launcher 直接拒绝作业。**必须位于非系统盘的物理固定盘**；写成系统盘会被体检和 plan 双重拒绝。 |
| `allow_scratch_on_system_drive` | 默认 `false`，保持不动。只有人类明确书面批准接受系统盘填满风险时才改 `true`，且不要用于真实算例。 |
| `max_total_cpus` / `max_total_memory_mb` / `max_concurrent` | 整数或 `"auto"`。`plan` 返回的 `capacity.limits` 会显示实际生效值。 |
| `min_free_disk_bytes` | 保护下限，默认 8 GiB。 |
| `compiler_candidates` | 只有用用户子程序时才重要；不用 Fortran 可留空。 |

**创建 scratch 目录**（必须，不能跳过）：

```powershell
New-Item -ItemType Directory -Force -Path $SCRATCH | Out-Null
```

每一个具体作业还要在 scratch 根下用自己的独立空子目录，例如 `$SCRATCH\JOB01`，不要多个作业共用。

---

## 4. 提交前体检（必须通过才能往下）

```powershell
& $PY $BRIDGE --config $CFG validate-config --query-release
```

这是**只读**体检：不创建项目文件、不提交作业、不启动求解器。`--query-release` 会在自动清理的临时目录里运行 `abaqus information=release` 查版本。

### 4.1 判定

| `verdict` | 含义 | 你的动作 |
|---|---|---|
| `READY` | 全通过 | 继续 §5 |
| `USABLE_WITH_WARNINGS` | 有警告无致命项 | 读每一项的 `action`，确认警告可接受后继续；不可接受就先修 |
| `BLOCKED` | 至少一项 FAIL | **停止**。按下面表格逐项修，修完重跑体检。不要改模型去迁就环境。 |

### 4.2 常见 FAIL 与修复

| 检查项 | 含义 | 修复 |
|---|---|---|
| `launcher` | launcher 不存在或扩展名异常 | 用 `doctor` 的 `compat.launcher_candidates` 找真实路径，填回配置 |
| `allowed_roots` | 目录不存在 | 创建目录，或改成真实存在的授权根 |
| `registry` | 父目录不存在/不可写 | 创建父目录或 grant 写权限 |
| `scratch_roots` | 目录不存在/不可写；或落在系统盘 | 建目录（必须预先存在）；系统盘则换到非系统数据盘，不要开 `allow_scratch_on_system_drive` 绕过 |
| `scratch_disk_policy` | 不会 FAIL，INFO 汇报系统盘与候选数据盘 | 按提示确认 scratch 在数据盘上 |
| `capacity` | auto 解析失败或非法值 | 三个容量键改成整数或 `"auto"` |
| `free_disk` | 可用空间低于下限 | 释放空间；不要在未授权时下调 `min_free_disk_bytes` |
| `host_injection` | 检出 `tsbx.dll` 等注入 DLL | **换宿主**：真实求解改用无注入的本机终端；当前宿主只能做审计和 ODB 后处理 |

明确边界：体检通过 ≠ 许可证签出成功 ≠ datacheck 通过。这三项是不同证据。

### 4.3 附加探测（可选但建议）

```powershell
& $PY $BRIDGE --config $CFG doctor
```

重点看三个字段：
- `solve_readiness.verdict`：若为 `BLOCKED_BY_AGENT_INJECTION`，当前宿主不能真跑求解；
- `compat.launcher_candidates` / `compat.compilers`：确认自动发现结果；
- `release_query.parsed.version`（加 `--query-release` 时）：作者验证环境是 `2023`，其他版本需自行核对关键字和 ABI。

---

## 5. 选一种接入方式

### 5.1 方式 A：纯命令行（最稳妥，先跑通这个）

所有命令都是 `& $PY $BRIDGE --config $CFG <命令>`。你已经用过 `init-config` / `validate-config` / `doctor`，剩下：

| 命令 | 用途 | 关键参数 |
|---|---|---|
| `plan` | 冻结输入哈希、生成计划 token，**不求解** | `--request <request.json>` |
| `submit` | 提交一个受管作业 | `--request` `--plan-token` `--authorize` `--authorization-note` |
| `status` | 查状态，自带 triage 根因字段 | `--job-id <32位id>` |
| `terminate` | 停止**这一个**受管作业 | `--job-id` `--authorize` `--authorization-note` |
| `restart-audit` | 列 restart 文件清单（不是状态验证） | `--directory` `--job` [--solver] |
| `probe` | 只读 ODB 清单 / 峰值 | `--request <odb_request.json>` |
| `triage` | 对失败作业做根因归类 | `--workdir <job目录>` `--job <job名>` |

用 `--help` 可随时查精确参数：

```powershell
& $PY $BRIDGE --help
& $PY $BRIDGE plan --help
```

### 5.2 方式 B：本地 stdio MCP（给 AI 客户端用）

把 `assets/mcp_client.local.example.json` 的内容作为模板，替换成你的绝对路径：

```json
{
  "mcpServers": {
    "CJC-abaqus-local-simulation": {
      "command": "D:\\anaconda3\\python.exe",
      "args": [
        "D:\\AI_ABAQUS\\CJC-abaqus-local-simulation\\scripts\\mcp_server.py",
        "--config",
        "D:\\AI_ABAQUS\\agent_config.json"
      ]
    }
  }
}
```

把这个配置导入支持 **本地 stdio MCP** 的客户端。连接顺序：

```
initialize → notifications/initialized → tools/list → abaqus_doctor
```

共 **10 个工具**：

| 工具 | 只读/受控 |
|---|---|
| `abaqus_doctor` | 只读 |
| `abaqus_plan_job` | 只读，不求解 |
| `abaqus_submit_job` | 受控，需授权参数 |
| `abaqus_job_status` | 只读 |
| `abaqus_terminate_job` | 受控，需停止授权 |
| `abaqus_restart_audit` | 只读 |
| `abaqus_probe_odb` | 只读，写新审计 JSON 不改 ODB |
| `abaqus_triage_job` | 只读 |
| `abaqus_host_compat` | 只读，换机器时先跑 |
| `abaqus_validate_config` | 只读，提交前必跑 |

另有 **6 个只读文档资源**：`abaqus://handbook`、`abaqus://user-subroutines`、`abaqus://troubleshooting`、`abaqus://agent-host`、`abaqus://host-compat`、`abaqus://project-contract`。

**没有**任意 shell 工具、没有网络监听。这意味着：即使你的 AI 客户端没有命令行权限，也能靠这些工具完成配置体检和 ODB 分析；但真实求解仍需要本机授权。

### 5.3 方式 C：作为 Skill 安装

如果你的 AI 客户端支持 Skill，把整个 `CJC-abaqus-local-simulation` 目录放到它的 skills 目录，然后指示它读 `SKILL.md`。三种入口共用同一后端，不会出现"一个 agent 报 RUNNING、另一个按旧缓存算"的问题。

---

## 6. 跑通第一个真实作业

这一步需要人类提供：一个合法的 INP（及其所有 `*INCLUDE` 依赖），以及 §0.3 的提交授权。

### 6.1 准备请求文件

从 `assets/job_request.example.json` 复制一份，按字段填写：

| 字段 | 说明 |
|---|---|
| `job` | ASCII 字母开头，最多 64 字符，只含字母数字 `_` `-`。**用唯一名字**，不要复用历史 job 名。 |
| `input` | INP 的绝对路径，必须在 `allowed_roots` 内。 |
| `workdir` | 专属空目录，不要指向旧结果目录。 |
| `scratch` | `scratch_roots` 下的独立空子目录，必须预先存在。 |
| `solver` | `standard` 或 `explicit`，默认 `standard`。 |
| `operation` | `analysis` 或 `datacheck`。**第一次建议用 `datacheck`** 验证输入卡，它不是模型验证。 |
| `cpus` / `memory_mb` | 按 §3.3 的容量上限填写，别超。 |
| `additional_files` | 外部 `FILE=` 依赖、Fortran include、头文件等清单。`*INCLUDE` 会自动递归发现，但这些不会。 |
| `user_subroutine` | 用户子程序绝对路径（如果用）。编译器兼容性必须单独验证。 |
| `oldjob` / `restart_state_verified` / `restart_evidence` | 只有带 `*RESTART, READ` 且状态已验证时才填。ODB 不是 restart state。 |
| `walltime_limit_seconds` | 墙时预算。 |
| `terminate_at_walltime` / `stop_after_confirmed_peak` | 默认 false；要改 true 必须先拿到 §0.3 的授权。 |
| `probe` | 可选的实时探针请求（step / history_regions / axis）。 |

### 6.2 审计计划

```powershell
& $PY $BRIDGE --config $CFG plan --request '<request.json>'
```

返回里重点看：

- `sealed`：冻结的输入/include/代码/环境哈希；
- `command_args` 和 `command_preview`：实际会执行的命令；
- `capacity`：含 `limits`，显示生效的 CPU/内存/并发上限；
- `host_readiness`：提交前的宿主裁决；
- `plan_token`：下一步要用，它绑定上面所有内容。

**这一步不产生任何求解文件**。逐项读完再决定要不要提交。

如果 `host_readiness.verdict` 是 `BLOCKED_BY_AGENT_INJECTION`，先换宿主，不要提交。

### 6.3 提交（需授权）

拿到人类对"这个 job / 资源 / 停止策略"的明确批准后：

```powershell
& $PY $BRIDGE --config $CFG submit --request '<request.json>' --plan-token '<token>' --authorize --authorization-note '人类已批准此job名称、cpus/内存与请求中的停止策略'
```

注意：
- token 不是密码，是计划内容哈希。输入、include、用户代码、后端代码或配置任一改变，都必须重做 `plan`。
- 一个 job 一个持久记录和后台 worker。不要重复提交同一个 job。
- 遇到"未知存活 solver"时本包会拒绝提交，不要想办法绕过。

### 6.4 监控

```powershell
& $PY $BRIDGE --config $CFG status --job-id '<32位id>'
```

`status` 会比对 PID 创建时刻和原始日志，返回：

- `observed_state`：真实现状；`STALE_RECORD_NEEDS_RECONCILIATION` 或 `ORPHANED_LAUNCHER` 表示要人工核对，不是重提理由；
- `terminal`：原始 `.log/.msg/.sta/.dat` 尾部 + `exception_kinds`；
- `triage`：自动根因归类（`root_cause` / `confidence` / `basis` / `recommended_action`）。

**不要**因为客户端退出就认为作业取消。worker 是独立进程。

### 6.5 失败时归类

```powershell
& $PY $BRIDGE --config $CFG triage --workdir '<job目录>' --job '<job名>'
```

这个命令同样能分析**历史作业**（路径在 `allowed_roots` 内即可）。根因类：

| `root_cause` | 含义 | 应对 |
|---|---|---|
| `HOST_SANDBOX_DEFECT` | 注入/进程隔离/`.prt` 交接断裂 | 换无注入宿主；**不要改材料网格** |
| `EXTERNAL_INTERRUPT` | 外部 ABORT/INTERRUPT | 查谁停的；不是数值不收敛 |
| `MODEL_INPUT_ERROR` | `.dat` 有 `***ERROR` | 修输入卡，另起 datacheck |
| `NUMERICAL_CONVERGENCE` | 增量不足/过多增量/负特征值/过度畸变 | 检查 loading/contact/mesh/stabilization，不改原模型 |
| `LICENSE_UNAVAILABLE` | 日志出现 license 问题 | 单独验证许可证 |
| `SOLVER_CRASH_UNATTRIBUTED` | 未检出注入的 access violation | 查 `.exception`、子程序 ABI |
| `SUSPECTED_HOST_SANDBOX` | 有注入+abort 但证据不足 | 先在无注入宿主复现 |
| `NO_FAILURE_EVIDENCE` | 有完成标记 | 不要把 rc0/完成当成峰值 |
| `UNDETERMINED` | 无决定性证据 | 手工查原始日志；空 ODB 不能说明原因 |

---

## 7. 读 ODB 与下结论的规矩

### 7.1 先 inventory，再 peak

```powershell
# 写 odb_request.json，先用 inventory 模式
& $PY $BRIDGE --config $CFG probe --request '<odb_request.json>'
```

请求里至少要给 `odb` 绝对路径。inventory 返回真实的 `steps`、`history_regions`、字段名、field keys。

**不要猜 region 名字**。常见陷阱：`historyRegions` 在 Abaqus Python 2.7 里是 Repository，必须 `.keys()`；能量区域形如 `Assembly ASSEMBLY`；加载点形如 `Node SPECIMEN-1.9001`。

### 7.2 peak 模式的硬性要求

- 必须指定**精确存在**的 `step`、`history_regions`、`axis`。
- 多个加载节点时，RF3 要**先有符号求和再取幅值**，不能取单个节点或绝对值求和。
- 只有配对、有限的 RF/U 点才支持峰值证据；终点、候选最大值、`candidate_RF` 都只是诊断。
- `PEAK_STABLE_PROVISIONAL` 默认 `usable_peak=false`；要用必须先拿到人类的明确使用策略。
- 检查 `ALLKE/ALLAE/ALLSD` 能量门和 field 时间偏差；缺项就写 `missing`，不要脑补。
- 不请求的变量不会出现在 ODB（例如 SDEG 必须显式输出）。cohesive 的 `STATUS=1` 表示**未损伤**，不是"未开裂"的充分证据；要看 `SDEG`。

### 7.3 你**不能**下的结论

- 不能说"目标达到"——除非有真实有效峰 + 能量门 + 人类确认的目标定义。
- 不能把标准件/单点的 field 均值说成面积加权损伤。
- 不能把 Standard 的峰直接当成 Explicit 的预测，反之亦然。
- 不能用"没有 CPRESS/SDEG"推出"接触力/损伤不存在"——先看全部 field keys 和输出请求。

---

## 8. 如果你自己运行在注入/隔离沙箱里

有些 AI 宿主会向每个子进程注入 DLL（如 `tsbx.dll`），并给每个子进程独立的文件系统视图。表现极具迷惑性：

- `.dat` 零错误、正常 `END OF USER INPUT PROCESSING`、PROBLEM SIZE 正确；
- 但 launcher 报 `Analysis Input File Processor exited with an error`，ODB **零帧**；
- 或报 `could not be located: <绝对路径>.inp`、`part map file ... does not exist / corrupt`。

判定与处理：

1. `doctor` 看 `solve_readiness.verdict` 和 `host_injection.suspects`；
2. 失败作业用 `triage` 看 `exception_kinds`（`PART_MAP_HANDOFF` / `FAIL_FAST_INJECTED_HOST` 是宿主证据，不是模型问题）；
3. 结论：当前宿主**只能**做 `doctor` / `plan` / 输入审计 / 既有 ODB 的 `probe`；
4. 真实求解交给**无注入的宿主机普通终端**——即让人类在他自己的终端跑，不要试图自己绕过。

绝对不要因为这类错误去改材料、网格或接触参数"修模型"。

---

## 9. 故障决策树（按顺序查，不要跳）

| 症状 | 先查什么 | 禁止动作 |
|---|---|---|
| `validate-config` 是 BLOCKED | 每一项的 `action` | 不要提交，不要改模型 |
| 提交被拒，说未知 solver | 现有 solver 进程与作业归属 | 不要假设空闲核心，不要接管 |
| cache 显示 RUNNING 但无进程 | PID 创建时刻、系统 boot 时间、STA/ODB 修改时间 | 不要无限 heartbeat，不要自动重提 |
| launcher 返回 0 但无结果 | `.log/.dat` 实际内容、probe JSON schema | 不要把 rc0 当成功 |
| `.lck` 存在 | 原 job / PID / ODB 是否仍在写 | 不要删锁解堵 |
| input processor 失败 | `.dat` ERROR 逐条、关键字/数据列/ID/集合/OP/材料 | 不要用改强度"修语法" |
| RF 异常小/大 | 受力面积、单位、RP/节点集合、sumRF、BC 位置 | 单节点不是总力；N/MPa/吨密度分开 |
| Standard 持续 cutback | MSG 的 minimum vs maximum increments、STA accepted 趋势、localstate/eigenvalues | 两类终因不能混写；终点 max 不是峰 |
| X=Y 不随 Ks/strength 变化 | slip/traction/QUADSCRT/SDEG、bulk、激活路径 | 参数未激活先停止扫参 |
| 打开 ODB Python2 TypeError | 路径是否 unicode、filesystem 编码 | 修读取接口，不要给模型判物理 INVALID |
| 找不到 CPRESS/SDEG | 全部 field keys、contact 后缀、cohesive 元素 vs contact vs UINTER | 不要造变量 |
| 换机器后信息不全 | `doctor.hardware_degraded`、`compat.powershell`、`launcher_candidates` | 探测失败≠模型问题 |

更深的属性归类见 `references/TROUBLESHOOTING.md`。

---

## 10. 完成报告格式

全部做完（或中途失败）后，向人类输出一份**结构化报告**，至少包含：

1. **本机与配置**：Python 路径、Abaqus 版本、launcher 路径、配置文件绝对路径、`validate-config` 的 verdict 与各项计数。
2. **接入方式**：你选了 CLI / MCP / Skill 中的哪一种，为什么。
3. **作业情况**：job 名、operation、plan_token 是否生成、是否取得授权、job_id、observed_state。
4. **证据**：`terminal` 的完成/中止标记、`triage.root_cause`、ODB inventory 的帧数、峰值状态（`PEAK_VALID` / `PEAK_STABLE_PROVISIONAL` / `NO_CONFIRMED_PEAK`）及 `usable_peak`。
5. **未能验证的东西**：许可证签出、子程序 ABI、其他版本关键字兼容性——明确写出来，不要含糊带过。
6. **下一步建议**：只在有证据支撑时给；不要用"再试一次"代替诊断。

如果任何一步失败，报告要说清失败在哪一步、原始证据是什么、你排除了什么。异常脚本的非零返回码和 JSON error 不等于"物理模型失败"。

---

## 11. 一句话记住整套规矩

> 先体检再计划，先授权再提交；
> 证据分宿主与模型，峰值分候选与有效；
> 不改源模型迁就求解器，不把零错误当成成功。

这份文档对应 skill 版本：以仓库内 `SKILL.md` 与 `README.md` 为准；若两者冲突，以代码实际行为（`tests/test_bridge.py` 覆盖的行为）为准。
