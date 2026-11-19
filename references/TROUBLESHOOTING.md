> 中文版。[English](references/TROUBLESHOOTING_EN.md)

# 故障判断与有限恢复

| 症状 | 必查证据 | 禁止捷径/可复用规则 |
|---|---|---|
| 无solver进程但cache RUNNING | PID创建时刻、系统boot、STA/ODB修改时间、原始结束标记 | 不无限heartbeat、不自动重提；先STALE/ORPHANED分类 |
| launcher返回0但无结果 | stdout/.log/.dat/probe JSON真实schema | 不是成功；后处理error需非零退出并保留异常 |
| `.lck`存在 | 原job/PID/ODB是否仍写入、文件所有者/阶段授权 | 不删锁解堵，更不能全局清scratch |
| input processor失败 | DAT ERROR逐条、关键字/数据列/ID/集合/OP选项/材料 | 不用改物理强度“修语法”；先最小输入核验 |
| RF非常小/非常大 | 受力面积、单位、RP/节点集合、sumRF、BC定位 | 单节点不是总力；N/MPa/吨密度分开 |
| X=Y不受Ks/strength变化 | slip/traction/QUADSCRT/SDEG、bulk、激活路径 | 参数未激活先停扫，不压到噪声级强度 |
| Standard持续cutback | MSG minimum vs maximum increments，STA accepted趋势，localstate/eigenvalues | 两类终因不能混写；终点max不是峰；有限恢复/solver分流 |
| candidate后0点 | accepted RF/U原始history | NO_CONFIRMED_PEAK，不按可行窗口/目标直接分类 |
| trace/ierr0但accepted异常 | NaN/inf、unpaired、properties、平衡/energy | ierr0不代表本构返回可靠；trace试探不能计accepted |
| 打开ODB Python2 TypeError | path是否unicode、filesystem编码、版本 | 修读取接口，不给模型判INVALID物理；异常必须非零 |
| String Expected as dictionary Key | JSON中的step/history/energy region是否unicode | 部分版本的 repository key 也需转 native string，不仅仅是 ODB 路径 |
| 找不到CPRESS/SDEG | 全部field keys、contact后缀、cohesive元素vscontactvsUINTER | 不造变量、不凭裸key缺失说压力不存在 |
| fine mesh改变比例 | facet geometry/platform/topology是否同步变化 | geometry reconstruction和pure h-refinement分开 |
| tied模型过强/PEEQ近0 | MONO/TIE/internal DOF/Poisson、理论约束上限 | 接近target也可能端面锁死，不调材料补偿 |
| Explicit有峰但动能/耗散高 | KE/IE峰时与全承载段、AE/VD/CD、加载速度/质量缩放 | peak下降不是准静态充分条件；缺能量仍missing |
| friction share超容量 | pressure符号、总shear、damage、slip定义、μp及完整传递法则 | 无独立分量则MECHANISM_ATTRIBUTION_LIMITED |
| source文件无变化但solver不同 | CDP viscosity语义、contact算法、精度、ramp/时间 | hash一致不等于有效数值实现一致 |
| 输入文件同名但结果不同 | material/geometry/BC/ramp/solver/precision/output/source哈希 | 不按名称复用，不混Standard与Explicit XYZ |
| worker或MCP崩溃 | managed record、worker/launcher identity、solver logs | 不认为客户端退出取消job；不自动retry |
| `.dat`零错误却求解失败/ODB零帧 | `triage --workdir <dir> --job <name>` 给出的单一 `root_cause`；提交前看 `doctor.solve_readiness.verdict`；原始证据为 `*.exception` Details/Phase | 宿主注入/进程隔离优先于模型嫌疑；见 AGENT_HOST_SANDBOX.md；不改材料/网格“修”宿主问题 |
| `could not be located: <绝对路径>.inp` 但文件在agent视图存在 | 宿主注入、命令`cmd /d /s /c`包装、cwd是否job目录 | 先试相对路径`input=<job>.inp`+cwd；已知成功输入同法重报即宿主问题，非INP错误 |
| part map file does not exist/corrupt (PART_MAP_HANDOFF) | exception Phase=std、pre/standard是否视图隔离、scratch是否预建 | `.prt`交接断裂≠模型错误；真实求解移到无注入宿主；不删scratch/不改模型 |
| submission.lock遗留 | 只检查registry锁内PID/创建时刻和写入是否进行 | 不自动删除；人工确认无提交进程后可恢复自身registry，不碰solver锁 |
| 换机器后 doctor 信息不全/硬件报 error | `doctor.hardware_degraded`、`doctor.compat.powershell`、`launcher_candidates`、`release_query.parsed.version` | 硬件走 OS API 降级不冒充CIM；先 `init-config --output <新配置>` 核对，探测失败≠模型问题；见 HOST_COMPATIBILITY.md |
| 提交前不确定配置是否可用 | `validate-config` / `abaqus_validate_config` 的 `verdict` 与各项 `action` | BLOCKED 先修配置/宿主再 `plan`；体检只读不写文件，也不替代一次授权的真实datacheck |
| plan报work/scratch在system drive | `scratch_disk_policy` 的 `system_drive`/`data_drives`、`scratch_roots` 的 `on_system_drive` | scratch/work 换到非系统物理盘；不要开 `allow_scratch_on_system_drive` 绕过；C盘临时文件会撑爆系统分区并引发IO争抢/MPI超时 |
| 并行慢/磁盘寻道声/计算中途崩 | scratch 剩余空间与吞吐、是否在系统盘或网络盘、每job是否独立空目录 | 先查scratch的IOPS和空间，不要先改cpus/mp_mode；只用非系统固定盘、绝对路径、每job独立；确认结束后只清自己的过期scratch |
| Windows路径大小写/斜杠导致越界误报 | `allowed_roots` 与实际路径的 normcase 结果 | 比较已忽略大小写与斜杠方向；仍拒绝相对路径与 cmd 元字符，不放宽安全校验 |

## 有限数值恢复合同

用户批准前：只诊断、提出数值选项，不实施。批准后：独立attempt名、同物理模型hash、改动列表、预算、最大attempt数、结束条件。可按任务考虑更小initial/min increment、更多increment、line search、很小stabilization或其他solver；这些不保证等价，应查能量/率/BC。

存在可验证restart state时先从已保存稳定increment继续；没有state不能把ODB当state。无论restart还是从头recovery，都不改原job，不抹除自然终止事实。

达到重试上限/无峰：NUMERICALLY_INCONCLUSIVE，不写NOT_EFFECTIVE。物理route否决需有效结果或正确的必要条件证据。用户明确禁止第三次时没有“再试一下”的例外。

## 查日志的最小顺序

1. 是否提交成功/许可等待/编译失败：stdout和LOG。
2. 是否输入错误：DAT。
3. accepted推进与最后时间：STA。
4. 收敛/损伤/畸变/终因：MSG（Explicit另查STA/LOG）。
5. 真实峰与energy/field：ODB read-only。
6. cache仅作为索引，用raw证据收口，不反过来覆盖raw。

此顺序是定位逻辑，不是把所有阶段权限统一成“可以停止”。自然运行合同继续有效，不能用诊断工具擅自终止历史作业。