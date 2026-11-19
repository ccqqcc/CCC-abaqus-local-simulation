> 中文版。[English](VALIDATION_REPORT_EN.md)

# Abaqus跨Agent调用包验收范围说明

本包随附可重复的验收脚本，绝不提交新的有限元分析。以下内容描述验收范围，不含任何具体研究项目、模型、ODB 或数值结果。

## 验收覆盖

| 项目 | 方法 | 边界 |
|---|---|---|
| Skill结构与元数据 | 官方校验脚本 | 只校验结构与字段 |
| 自动测试 | `python -m unittest discover -s tests` | 命令规划、保护逻辑、峰值算法、MCP握手与错误路径 |
| Abaqus版本查询 | 经配置的 launcher 只读查询 | 不验证许可证是否真能签出 |
| MCP stdio | 独立客户端握手/工具/资源/错误路径 | 无HTTP端口 |
| ODB读取 | 由使用者提供本机已授权ODB | 只读，源哈希前后一致 |

## 可重复命令

```powershell
$py = '<PYTHON_EXE>'
& $py validation\run_validation.py --config <你的配置路径>
```

不传入 `--real-odb` 时只跑单元测试与只读版本查询，不需要任何模型文件。传入真实 ODB 时需你自己指定 step、history-region、axis 与 solver，本机路径/节点号不是通用模板。

## 限制

- 提交/停止与授权守卫仅由模拟进程覆盖，不是新求解端到端验证。
- 用户子程序编译、二进制 restart 续算未在本包内重新执行。
- 许可证可用性不能由版本查询或 ODB 读取证明。
- 异常脚本非零返回码与 JSON error 不等于物理模型失败。