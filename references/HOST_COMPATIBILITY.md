> 中文版。[English](references/HOST_COMPATIBILITY_EN.md)

# 跨设备兼容与迁移（探测、降级、配置生成）

本文件说明本包如何适应**不同 Windows 机器**：不同 Abaqus 安装路径/版本、不同 PowerShell 版本、不同 CPU/内存/磁盘布局、不同路径大小写习惯。所有探测只读，不启动求解器、不改动已有配置、不证明许可证签出。

原始验证环境是 Windows + Abaqus 2023。其他版本/安装形态只能在目标机上用 `doctor --query-release` 与一次授权的输入核验确认，不得假定关键字、接触算法或子程序 ABI 完全一致。

## 1. 自动探测了什么

| 探测项 | 入口 | 来源与顺序 |
|---|---|---|
| PowerShell | `doctor.compat.powershell`、`abaqus_host_compat` | PATH 中 `powershell.exe` → `pwsh.exe` → `powershell`/`pwsh` → 标准 Windows 系统目录 |
| Abaqus launcher | `doctor.compat.launcher_candidates` | 环境变量 `ABAQUS_BAT`/`ABAQUS_COMMAND`/`ABAQUS_HOME`/`SIMULIA_HOME` → PATH → C/D/E 盘 `SIMULIA/Commands` 与 `SimulationServices/V6R*/.../Commands` |
| Fortran/链接器 | `doctor.compat.compilers` | PATH 中 `ifx`/`ifort`/`link`/`clang`/`gcc` → 常见 VS BuildTools/Community/Professional/Enterprise 的 `Hostx64/x64/link.exe` |
| 硬件 | `doctor.hardware`、`hardware_degraded` | 优先 CIM/WMI（经 PowerShell）；不可用时 `os.cpu_count` + `GlobalMemoryStatusEx` 降级，并标注 `source` |
| Abaqus 版本 | `doctor --query-release` 的 `release_query.parsed.version` | 解析 `abaqus information=release` 输出；解析失败返回结构化空值，不报错退出 |

`launcher_candidates` 只是**发现**，不会自动切换。当前生效的 launcher 始终是配置里的 `abaqus_launcher`；换机器时先核对候选，再更新配置。

## 2. 一键生成目标机配置

```powershell
$py = '<PYTHON_EXE>'
$bridge = 'C:\path\to\abaqus-local-simulation\scripts\abaqus_agent.py'
& $py $bridge init-config --output 'D:\new_project\agent_config.json'
```

生成内容是**建议值**，不会覆盖已有文件：

- `abaqus_launcher`：探测到的第一个候选（找不到时为空字符串，必须手工填写）
- `allowed_roots`：输出文件所在目录（按需扩展为真正授权的项目根）
- `registry_dir`：该目录下的 `agent_integrations/abaqus_runtime`
- `scratch_roots`：该目录下的 `scratch`（**必须预先创建**，否则 launcher 拒绝作业）
- `max_total_cpus` / `max_concurrent` / `max_total_memory_mb`：按本机硬件推导，至少留 1 个逻辑核和 15% 内存
- `compiler_candidates`：PATH/常见安装位置发现的编译器绝对路径

生成后依次：`doctor` → `validate-config --query-release` → 建 scratch → `plan`。任何一步不匹配都先修配置，不要改物理模型去适配环境。

## 2a. 工作目录与 scratch 绝不能放系统盘（强制策略）

这是从大量工程实践里反复验证的硬规则，本包把它做成**代码级拦截**，不只是文档提醒：

- **为什么会出事**：非线性分析会生成几十 GB 乃至上百 GB 的临时文件。scratch 默认落在 C 盘会撑爆系统分区，导致卡死、闪退、算例中断重来；系统盘的并发读写还会和操作系统抢 IO，拖慢求解，甚至在并行作业时触发 MPI 通信超时。社区经验里"大型模型计算崩溃的 80% 原因不是内存不足，而是 scratch 的 IO 吞吐触顶"是常见共识。
- **正确做法**：scratch 指向**非系统盘的物理固定盘（DRIVE_FIXED）**，优先高速 SSD/NVMe，用绝对路径；每个 job 一个独立空子目录；不要用网络盘/映射盘/可移动盘（低延迟随机 IO 会被网络延迟破坏）。
- **三盘分工的经验**：C 盘只放系统和软件；D/数据盘放项目、scratch、运算输出；归档盘放完成的结果做冷数据。本包不强制具体盘符，只要求"非系统盘 + 固定盘"。

本包的实现：

| 位置 | 行为 |
|---|---|
| `init-config` | 自动探测系统盘（`system_drive()`），列出固定数据盘（`data_drives()`），把 `scratch_roots` 选到**空闲最大的非系统盘** `ABAQUS_SCRATCH`；可用 `--prefer-drive D:`（可逗号分隔多个）指定**本机优先盘符**，此时按优先顺序而非空闲大小选择，并把 `preferred_scratch_drives` 写进配置以便审计。无可用数据盘时在 `note` 里给出明确警告 |
| `validate-config` | 新增 `scratch_disk_policy` 检查；scratch 落在系统盘时 `scratch_roots` 判 **FAIL**（除非显式覆盖），并列出系统盘与候选数据盘 |
| `plan` | 提交前硬拦截：work 或 scratch 在系统盘直接拒绝，附修复指引 |
| 首选盘审计 | `scratch_disk_policy` 会记录 `preferred_scratch_drives` 与实际 scratch 是否落在该盘；配了首选盘却没用上会标 **WARN**，提醒修正而不是静默忽略 |
| 显式覆盖 | 只有配置里 `allow_scratch_on_system_drive=true`（需用户明确批准）才放行，此时体检标 WARN/INFO 留痕 |

### 盘符偏好示例（仅示意）

有些用户会把 **D 盘**设为工作任务首选盘，此时在配置里显式写 `preferred_scratch_drives: ["D:"]`，scratch 落在该盘。盘符偏好**只写在个人配置里**，不会作为通用默认值——其他机器可用 `init-config --prefer-drive` 显式指定，或默认按空闲最大的物理盘自动选。本包自带的配置示例不含任何盘符偏好。

注意：`allow_scratch_on_system_drive` 是为测试夹具和特殊环境留的**逃生口**，不是常规选项。开启等于接受系统盘被填满和 IO 争抢的风险，不要用于真实生产算例。

相关诊断函数：`host_compat.system_drive()`、`on_system_drive(path)`、`data_drives()`、`suggest_scratch_root(base)`，均可从 `abaqus_host_compat` MCP 工具的 `compat` 信息中观察结果。

## 2b. 提交前配置体检：`validate-config`

```powershell
& $py $bridge validate-config
& $py $bridge validate-config --query-release   # 额外查 Abaqus 版本
```

MCP 等价工具：`abaqus_validate_config`（可选 `query_release` 布尔参数）。

这是**只读**体检：不创建任何文件、不提交作业。默认不启动外部进程；只有 `--query-release` 才运行 `abaqus information=release`，且工作目录是自动清理的临时目录，不会在项目里留下日志。

十项检查及判定：

| 检查 | FAIL 条件 | WARN 条件 |
|---|---|---|
| `config_keys` | 缺必需键 | — |
| `launcher` | 找不到 | 扩展名非 bat/cmd/exe |
| `allowed_roots` | 目录不存在 | — |
| `registry` | 父目录不存在或不可写 | — |
| `scratch_roots` | 不存在或不可写 | 位于 allowed_roots 之外 |
| `capacity` | auto 解析失败/非法值 | 超过逻辑核数或物理内存 |
| `free_disk` | 可用空间低于下限 | 无 scratch 可测 |
| `compilers` | — | 配置了但都不存在 |
| `powershell` | — | 未找到（硬件/进程快照降级） |
| `host_injection` | 检出 `tsbx.dll` 等注入 DLL | — |
| `abaqus_release`（可选） | launcher 缺失无法查询 | 返回码非零 / 版本解析不出 / 非已验证的 2023 |

顶层 `verdict`：任一 FAIL → `BLOCKED`；只有 WARN → `USABLE_WITH_WARNINGS`；全 PASS → `READY`。`usable` 为 `verdict != BLOCKED` 的布尔值，每项检查都带 `detail` 和 `action`（修复建议）。

注意 `os.access` 是**静态可写性判断**，不是实际写测试；体检通过不替代一次授权的真实 datacheck。注入 FAIL 与 `solve_readiness=BLOCKED_BY_AGENT_INJECTION` 一致时，真实求解必须换无注入宿主。

## 3. `auto` 容量值

配置文件里三个容量键可以是整数，也可以是字符串 `"auto"` 或省略。后端在 `Backend.limits()` 中解析，`plan` 返回的 `capacity.limits` 显示**实际生效值**：

```json
{
  "max_total_cpus": "auto",
  "max_concurrent": "auto",
  "max_total_memory_mb": "auto"
}
```

推导规则在 `host_compat.default_limits()`：`cpus = max(1, 逻辑核-1)`，`concurrent = max(1, min(8, 逻辑核//4))`，`memory = 总内存×0.85`。这些是**安全上界建议**，不是性能承诺；实际算例仍需用户按模型规模授权具体 cpus/memory。

另一个可选键是 `preferred_scratch_drives`（如 `["D:"]`），表达**本机**的盘符偏好。它不改变容量，只影响 `init-config` 选 scratch 的位置；`validate-config` 的 `scratch_disk_policy` 会审计 scratch 是否真的落在该盘。生成器命令：

```powershell
& $py $bridge init-config --output '<config>' --prefer-drive 'D:'        # 单盘
& $py $bridge init-config --output '<config>' --prefer-drive 'D:,E:'     # 按顺序回退
```

## 4. 路径兼容性

`allowed_roots` 与作业路径的比较使用 `os.path.normcase`，因此 Windows 上盘符大小写、斜杠方向、尾部分隔符差异不会让合法路径被误判为越界。`path_is_within` 同时防止 `/data/project` 误包含 `/data/project_other` 这类前缀陷阱。

仍**拒绝相对路径**；命令参数含 `& | < > ^ % !` 引号或换行仍会被 `safe_argument` 拒绝，这是防注入设计，不因换机器放宽。

## 5. 降级行为

| 缺失项 | 行为 |
|---|---|
| PowerShell 完全不可用 | `doctor.hardware` 走 OS API 降级并标 `hardware_degraded=true`；进程快照不可用时 `capacity()` 拒绝提交而不是猜测现有 solver |
| 找不到 Abaqus launcher | `init-config` 生成空 launcher；`doctor.solve_readiness` 给 `NO_LAUNCHER`；提交被拒 |
| 找不到编译器 | `compiler_candidates` 为空；子程序作业需用户自行确认工具链，不会假装可编译 |
| 解析不出版本 | `release_query.parsed.version=null`；不推断关键字/ABI 兼容 |
| 非 Windows | 硬件/进程/注入检测返回结构化不可用；`solve_readiness` 为 `UNSUPPORTED_HOST`；不尝试用 Unix shell 驱动 Abaqus |

## 6. 边界

- 探测不修改环境变量、不安装软件、不替换配置、不启动 `pre.exe`/`standard.exe`/`explicit.exe`。
- `init-config` 只在目标路径不存在时写文件；已存在则报错，不覆盖。
- 探测到候选不等于许可证可用、版本关键字兼容或子程序 ABI 匹配；这些仍需目标机单独验证。
- 本文件不改变物理/材料/验收合同，也不放宽任何授权与哈希冻结规则。

## 7. 参考经验（外部资料，仅取技术共识）

以下资料用于支撑 §2a 的 scratch 磁盘策略。本包只采纳与 IO/磁盘布局有关的技术共识，不采纳其产品推广内容：

- Abaqus 环境文件与 scratch 配置解析（IO 隔离与 MPI 超时、scratch IOPS 是并行瓶颈）：https://tsight.io/articles/11909097?lang=zh
- 临时文件路径定位与 C 盘空间清理（换成非系统盘、计算前预估空间、区分手动/自动清理）：https://www.gofarlic.com/techDocumentDetail?documentId=53715
- "no enough disk" 诊断（相对路径不可靠、避免网络存储做 scratch、作业级覆盖 + 环境级固化）：https://ask.csdn.net/questions/9249221
- Abaqus 改临时路径三步与系统盘风险（新建数据盘目录、`scratch='D:/...'`、统一管理）：https://www.saifanbox.com/news/356.html

这些是社区/厂商经验，不是 Abaqus 官方 SLA；本包把其中可机械验证的部分（系统盘判定、固定盘筛选、绝对路径、每 job 独立目录）变成了拦截规则。