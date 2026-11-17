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
$py = 'D:\anaconda3\python.exe'
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
