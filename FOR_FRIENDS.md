> 中文版。[English](FOR_FRIENDS_EN.md)

# abaqus-local-simulation 朋友上手指南

这是把本机 Abaqus 调用封装成「Skill + 命令行 + 本地 MCP」的桥接包。
它**不含** Abaqus 求解器、许可证、模型或 ODB；这些必须在你自己机器上独立安装。

## 0. 先搞清楚能不能用

- 需要 **Windows + 已安装 Abaqus**（示例环境为 Abaqus 2023；其他版本需自行核对关键字/ABI）。
- 需要 **Python 3.9+**（任意 CPython；只读 ODB 走 Abaqus 自带 Python，编排走普通 Python）。
- 只需要「能跑命令行」；想接 AI 客户端再配 MCP。
- 检查自己是不是在**带注入/沙箱的 agent** 里：跑 `doctor`，若 `solve_readiness.verdict = BLOCKED_BY_AGENT_INJECTION`，这个宿主只能做审计/后处理，真实求解要换本机普通终端。

## 1. 拿到代码

```powershell
git clone https://github.com/<OWNER>/abaqus-local-simulation.git
cd abaqus-local-simulation
```

不会 git 就直接点 GitHub 页面绿色 **Code → Download ZIP** 解压。

## 2. 三步完成本机配置（不要直接用仓库里的 local_config.json）

那个文件是路径示例，必须换成你自己的：

```powershell
$py = '<PYTHON_EXE>'          # 换成你的 Python
$bridge = '.\scripts\abaqus_agent.py'

# 1) 按你的机器生成配置骨架（自动找 abaqus.bat / 编译器 / 算容量 / 自动选非系统盘做 scratch）
& $py $bridge init-config --output 'D:\my_project\agent_config.json'

# 2) 体检：结果必须是 READY 或 USABLE_WITH_WARNINGS
& $py $bridge --config 'D:\my_project\agent_config.json' validate-config --query-release

# 3) 手动建好配置里 scratch_roots 指向的目录（必须预先存在）
```

体检出现 `BLOCKED` 时，按每一项的 `action` 修配置/换宿主，**不要改材料或网格去迁就环境**。

**重要：工作目录和 scratch 不要放系统盘（一般是 C 盘）。** Abaqus 一次非线性分析能产生几十 GB 临时文件，放 C 盘会撑爆系统分区、拖慢求解甚至触发并行超时。`init-config` 会自动挑空闲最大的非系统物理盘；如果它选的盘不对，手动改 `scratch_roots` 到 D/E 等数据盘。体检和提交计划两处都会拦截系统盘路径，不要为了图省事去开 `allow_scratch_on_system_drive=true`。

## 3. 日常用法

```powershell
# 看环境与宿主裁决
& $py $bridge --config '<config>' doctor

# 审计一个 INP，生成冻结计划（不会求解）
& $py $bridge --config '<config>' plan --request '<request.json>'

# 提交：必须有你本人明确授权 + plan 返回的 token
& $py $bridge --config '<config>' submit --request '<request.json>' --plan-token '<token>' --authorize --authorization-note '我批准此 job/资源/停止策略'

# 看状态（自带 triage 根因归类）
& $py $bridge --config '<config>' status --job-id '<32位id>'

# 失败了要归因
& $py $bridge --config '<config>' triage --workdir '<job目录>' --job '<job名>'

# 只读读 ODB
& $py $bridge --config '<config>' probe --request '<odb_request.json>'
```

## 4. 接 AI 客户端（可选）

支持本地 stdio MCP 的客户端，导入 `assets/mcp_client.local.example.json`，
把里面的 python 路径和 `mcp_server.py` 路径换成你本机的绝对路径。
共 10 个只读/受控工具，没有任意 shell、没有网络监听。
常用顺序：`abaqus_host_compat` → `abaqus_validate_config` → `abaqus_doctor` → `abaqus_plan_job` →（人工批准）→ `abaqus_submit_job` → `abaqus_job_status` / `abaqus_triage_job`。

如果客户端支持 Skill，把整个目录放到它的 skills 目录并让它读 `SKILL.md` 即可。

## 5. 边界与规矩（重要）

- `submit` 需要你的明确授权和说明，token 绑定精确的输入/资源哈希；改任何输入都要重做 plan。
- 包不会自动改你的物理模型、不会自动重启、不会误判候选峰为有效峰。
- 沙箱注入的宿主**不能真跑求解**：会表现为 `.dat` 零错误但 ODB 零帧、`PART_MAP_HANDOFF`。此时换无注入的本机终端。
- 体检通过 ≠ 许可证签出成功；仍需一次授权的真实 datacheck 验证。
- 结果解释看 `references/ABAQUS_CALLING_HANDBOOK.md`、`TROUBLESHOOTING.md`、`AGENT_HOST_SANDBOX.md`、`HOST_COMPATIBILITY.md`。

有问题先看 `VALIDATION_REPORT.md` 和 `tests/test_bridge.py`，那里写明了哪些能力被真实验证、哪些只是模拟测试。