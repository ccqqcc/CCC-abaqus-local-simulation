> English version. [中文版](VALIDATION_REPORT.md)



# Abaqus Cross-Agent Invocation Package: Acceptance Scope Description

This package ships reproducible acceptance scripts and never submits new finite element analyses. The following describes the acceptance scope and contains no specific research project, model, ODB, or numerical result.

## Acceptance Coverage

| Item | Method | Boundary |
|---|---|---|
| Skill structure and metadata | Official validation script | Validates structure and fields only |
| Automated tests | `python -m unittest discover -s tests` | Command planning, guard logic, peak algorithm, MCP handshake, and error paths |
| Abaqus version query | Read-only query via the configured launcher | Does not verify whether a license can actually be checked out |
| MCP stdio | Standalone client handshake/tools/resources/error paths | No HTTP port |
| ODB reading | User-provided, locally licensed ODB | Read-only; source hash unchanged before and after |

## Reproducible Commands

```powershell
$py = '<PYTHON_EXE>'
& $py validation\run_validation.py --config <your-config-path>
```

When `--real-odb` is not passed, only the unit tests and the read-only version query run; no model files are needed. When passing a real ODB, you must specify the step, history-region, axis, and solver yourself; local paths/node numbers are not a general template.

## Limitations

- Submission/stop and authorization guards are covered only by simulated processes, not by end-to-end verification of a new solve.
- User subroutine compilation and binary restart continuation were not re-executed within this package.
- License availability cannot be proven by a version query or ODB reading.
- A non-zero return code from an exceptional script and a JSON error do not equal a physical model failure.
