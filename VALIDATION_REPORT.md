# Abaqus跨Agent调用包验收报告

验收日期：2026-10-04。版本：1.0.0。

结论：**本机调用封装、只读ODB读取和保护逻辑验收通过；不等于新有限元模型已求解验证。** 本轮没有提交analysis/datacheck，没有停止现有solver，没有修改历史INP/ODB、材料、界面或队列。

## 1. 实际执行的验收

| 项目 | 结果 | 实测范围 |
|---|---|---|
| Skill结构/元数据检查 | PASS | 官方skill-creator的quick_validate返回`Skill is valid!` |
| 自动测试 | PASS | 49项，0失败、0错误、0跳过 |
| Abaqus版本调用 | PASS | 经配置中的BAT launcher实际调用，本机Abaqus2023 |
| MCP stdio | PASS | 独立客户端initialize、工具清单、参数/授权错误路径、ping；7个工具 |
| MCP指导资源 | PASS | 4份文档资源list/read，拒绝未知URI，不开放任意文件读取 |
| ODB真实读取 | PASS | 两个既有Explicit ODB；inventory后使用真实COMPRESSION/加载RP history |
| 完整MCP→Abaqus Python→ODB链 | PASS | S7_E1_X经过实际stdio tools/call，不是伪造工具返回 |
| 共用CLI/backend→Abaqus Python链 | PASS | S7_E2_X实际读取，所有入口使用同一后端 |
| 原ODB不变 | PASS | 两个源文件读取前后SHA-256逐一一致 |

测试按如下命令可重复执行；只会查询版本、读取所列既有ODB和更新本包自己的验收/审计记录，不提交求解：

```powershell
& 'D:\anaconda3\python.exe' 'C:\Users\21050\.codex\skills\abaqus-local-simulation\validation\run_validation.py' --real-odb 'H:\STAGE7_20261003\S7_E1_X\S7_E1_X.odb' --real-odb 'H:\STAGE7_20261003\S7_E2_X\S7_E2_X.odb'
```

迁移到其他机器时，应提供该机器已经授权读取的ODB，并显式修改step、history-region、axis和solver；本机路径/节点号不是通用模板。

完整机器可读证据：[validation/RESULTS.json](validation/RESULTS.json)。其中保留自动测试记录、MCP响应、ODB清单、实际峰值/能量/field信息和被测脚本哈希。它是本调用包的验收证据，不会覆盖旧阶段的结果表或分类。

## 2. 真实ODB读数

| 既有ODB | RF_peak / N | U_peak / mm | 本probe峰资格 | 最大ALLKE/ALLIE | 读取后源文件 |
|---|---:|---:|---|---:|---|
| H:/STAGE7_20261003/S7_E1_X/S7_E1_X.odb | 57818.39453125 | 0.0697973073 | PEAK_VALID，严格5%下降条件满足 | 0.025718% | SHA-256不变 |
| H:/STAGE7_20261003/S7_E2_X/S7_E2_X.odb | 58360.07031250 | 0.0708643869 | PEAK_VALID，严格5%下降条件满足 | 0.028627% | SHA-256不变 |

能量最大值使用RF≥20%candidate的承载段，并包含峰后；没有只取一个峰时值代替全段审核。两份源文件SHA-256分别为：

```text
S7_E1_X: 921e532488155b7aefa6c1132e0116857cc3c083b64c549342aadc22b62c90b0
S7_E2_X: adf8da5cd45d4fffdc644f7a03b402ca25cdd7d09e9dcca708d050001b794658
```

这证明该调用链能读出、配对并验收既有结果，不证明所有力学假设均正确。ALLVD尾段比值、Standard/Explicit差异、空间机制等仍需按任务合同独立审查；不能把这些X结果与不同solver合同的旧Y/Z拼成通过结论。

## 3. 保护逻辑和生命周期测试

49项测试覆盖：

- 正式峰、筛查峰、稳定临时峰、终点最大、后点不足、NaN/Inf、失配/重复和位移方向异常；不将postpeak minimum当峰值下界。
- 允许路径、独立work/scratch、已有结果保护、递归include、依赖缺失/变更、配置/代码冻结和计划token。
- CPU/RAM/并发预算、未知现有solver、PID创建时刻与陈旧状态、Windows BAT安全参数和Explicit命令。
- 未授权提交/停止被拒绝；授权是调用者记录的人类批准，不冒充客户端身份认证。
- 模拟worker的正常终态、DAT输入错误、启动前输入变更、授权超时停止、不授权时不停止。
- MCP握手、工具声明、文档资源、错误路径，以及协议stdout不夹杂普通solver输出。

单元测试中的launcher/worker提交与停止使用模拟进程，**不是新FE求解端到端测试**。

## 4. 现场发现并修复的问题

1. Abaqus2023 Python2.7对JSON解码后的Unicode repository key报`String Expected as dictionary Key`。除了openOdb路径，还必须兼容step/history/energy region的键；已在真实ODB链核验修复。
2. datacheck日志中完成措辞不能覆盖DAT中的输入ERROR。worker先核对错误和返回码，再接受完成标记；对应回归测试通过。
3. shell字符串拼接不能直接承载任意模型路径。BAT逐参数验证/引用，并拒绝cmd元字符；两个真实Abaqus Python子进程验证了本机launcher链。
4. 同一进程号可能被Windows复用，旧缓存也可能残留RUNNING。状态使用PID创建时刻加原始日志核对，不自动重提失联任务。

## 5. 尚未实测、不得夸大的范围

- **没有新analysis/datacheck**：需要用户提供准确模型和授权后，才能验证实际solver签出、输入检查和新分析生命周期。
- **没有重新编译UMAT/UINTER/VUMAT/VUINTER**：编译器路径存在不等于ABI/精度/版本兼容通过。
- **没有实际restart续算**：文件清单不是可恢复state/increment的证明。
- **没有在WorkBuddy UI中导入测试**：已验证标准stdio MCP协议；其是否支持本地MCP、UI入口和权限由该产品实际配置决定。
- **没有许可证可用性证明**：版本查询和只读ODB不等于solver/CAE license checkout。
- **没有Windows重启恢复服务**：worker可独立于客户端运行，不保证跨系统重启继续。
- **没有自动16槽补满/物理排名控制器**：通用后端保护资源和逐job监控；阶段队列/筛选仍须依据单独授权清单实现。
- **没有自动几何建模、材料标定、面积加权或摩擦/黏聚分量分离**：这些需要真实模型及专用审计，不由通用摘要替代。

## 6. 打包与迁移验收

发布脚本`build_package.py`生成逐文件SHA-256清单与ZIP，重新读出压缩成员校验CRC及清单哈希，拒绝覆盖已有发布包。包不包含Abaqus二进制、许可证、研究INP/ODB、私有子程序或Python字节码。

对其他agent，先导入本地MCP或使用CLI，执行doctor和plan；首次新job仍需独立输入/许可证验收。详见[README.md](README.md)。
