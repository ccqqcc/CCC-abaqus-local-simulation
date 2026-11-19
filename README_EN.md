> English version. [中文版](README.md)



# CCC-abaqus-local-simulation: Abaqus Cross-Agent Invocation Package (Skill + CLI + MCP)

> **First time getting this repository?**
> - You plan to send the instructions to an AI agent and have it install and run everything itself → use [`FOR_AI_AGENT.md`](FOR_AI_AGENT_EN.md) (complete executable instructions, recommended)
> - You want a quick start for yourself → use [`FOR_FRIENDS.md`](FOR_FRIENDS_EN.md) (concise version)

This package packages a field-tested approach to Abaqus invocation, common pitfalls, and evidence rules into a portable entry point. All three entry points share the same backend, avoiding situations where one agent reports RUNNING while another computes results from stale caches. No third-party Python packages are required; authoring/scheduling uses Python ≥ 3.9, while ODB reading uses the Python bundled with the local Abaqus installation.

Complete calling handbook: [ABAQUS_CALLING_HANDBOOK.md](references/ABAQUS_CALLING_HANDBOOK_EN.md). For subroutine and troubleshooting topics, see `references/`.

## 1. What capabilities are actually included

| Capability | Entry point | Behavior / boundary |
|---|---|---|
| Environment check | `doctor` / `abaqus_doctor` | Local version, hardware, drives, toolchain paths, existing solver, `host_injection` (host-injected DLL detection); license checkout is not claimed as verified |
| Cross-device discovery | `doctor.compat` / `abaqus_host_compat` | Automatically discovers PowerShell, Abaqus launcher candidates, compilers, memory and capacity recommendations; falls back to OS APIs for hardware when PowerShell is missing; read-only, does not activate |
| Target-machine config generation | `init-config` | Generates a config skeleton for the current machine (absolute paths, `auto` capacity, discovered launcher/compiler); does not overwrite existing files; scratch must still be created manually |
| Pre-submission config preflight | `validate-config` / `abaqus_validate_config` | Eleven PASS/WARN/FAIL checks: required keys, launcher, roots, registry/scratch writability, **scratch not on the system drive (`scratch_disk_policy`)**, capacity vs hardware, disk minimum, compiler, PowerShell, host injection, optional version; read-only, writes no files, submits nothing |
| Working-directory disk policy | `init-config` + `plan` double interception | Automatically detects the system drive and selects the non-system physical drive with the most free space for scratch; work/scratch on the system drive is rejected outright (unless `allow_scratch_on_system_drive` is explicitly approved); avoids filling the system drive with temporary files and IO contention causing MPI timeouts |
| Host / anomaly diagnosis | `doctor.host_injection` + `status.terminal_evidence.exception_kinds` | Identifies root causes such as tsbx injection and `.prt`/fail-fast/interruption anomalies; distinguishes host defects from model defects; see `abaqus://agent-host` |
| Pre-submission host verdict | `doctor.solve_readiness` / `plan.host_readiness` | Clearly returns verdicts such as `BLOCKED_BY_AGENT_INJECTION`/`READY_LICENSE_UNVERIFIED` and whether a real solve is appropriate; license is still not claimed as verified; does not alter `sealed` hashes |
| Failure root-cause classification | `triage` / `abaqus_triage_job` | Classifies `.exception`/`.dat`/log evidence into **one** root_cause (HOST_SANDBOX_DEFECT, MODEL_INPUT_ERROR, NUMERICAL_CONVERGENCE, LICENSE_UNAVAILABLE, EXTERNAL_INTERRUPT, etc.) + confidence + recommended action; supports historical jobs not managed by this skill; read-only |
| Input / dependency audit | `plan` / `abaqus_plan_job` | Recursive INCLUDE, extra files, code/environment hashes, CPU/RAM budget, command, plan token; performs no analysis |
| Input pre-check | request `operation=datacheck` | Independent, explicitly authorized job; does not automatically overwrite the original job |
| Standard/Explicit submission | `submit` / `abaqus_submit_job` | One persistent record/background worker per job; Explicit double-precision domain; requires authorization and token |
| Numerical control | INP/request files | Parameters are determined by the user's task; the backend does not change stiffness/materials/BC/incrementation on its own |
| User subroutine | request `user_subroutine` | Adds `user=`; the compilation environment must be independently verified; does not claim all Fortran code will run |
| Status | `status` / `abaqus_job_status` | PID creation time + LOG/MSG/STA/DAT, flags lost/stale records, does not wait based on cache; includes a `triage` root-cause field |
| Limited automatic stop | two stop boolean switches in the request | Both default to false; with user approval, wall-time stop-loss / strict post-peak stop; no taskkill |
| Precise stop | `terminate` / `abaqus_terminate_job` | Only one job registered by itself with matching identity; additionally requires stop authorization |
| Restart evidence | `restart-audit` / `abaqus_restart_audit` | File inventory; does not fabricate increments/state; continuing an oldjob requires additional state verification |
| ODB inventory | `probe mode=inventory` | steps, regions, RF/U fields, field keys; read-only |
| ODB peak | `probe mode=peak` | explicit region, pairing/finiteness, 5%/2%/stable provisional rules, candidates kept separate from valid peaks |
| Energy / near-peak field | same as above | KE/IE etc., at-peak/throughout, field time offset, real field names, missing-item reporting |

The following are not packaged: "automatic creation of material constitutive laws", "automatic calibration of targets", "automatic recovery of unknown jobs", "automatic Windows reboot", "remote Abaqus cluster". Geometry modeling, complex spatial mechanisms, units, and experimental authenticity still require the agent to handle them based on the real task.

## 2. Current machine and migration

Verified on Windows + Abaqus 2023; launcher and Python paths vary by machine, so use `init-config` for automatic discovery. The presence of a compiler candidate does not mean all UMAT/UINTER have been verified to compile.

The Skill installation location varies by machine; the paths below are illustrative only—replace them with your actual locations.

Migration: extract the entire skill directory to a location accessible to the target agent; on a new machine, first use `init-config --output <NEW_CONFIG_PATH>` to generate a suggested config (automatically detecting the launcher/compiler/hardware and giving capacity as `auto`), then check `doctor.compat`, `doctor --query-release`, and `solve_readiness`, use `validate-config --query-release` for the pre-submission preflight (when BLOCKED, fix the config/host first—do not change the model), and finally modify the launcher, project roots, registry, scratch, and capacity as authorized. Workspace scopes in the config must be explicitly authorized; path comparison already supports Windows case/slash differences. Abaqus and a valid license must be installed independently on the target machine; the package does not include a solver, license, proprietary models/ODB, or private compiler. See `references/HOST_COMPATIBILITY_EN.md`.

Config key points:

- `registry_dir`: this package's own task and audit records; do not point it to historical queue files.
- `allowed_roots`: all INP/include/user/ODB/work/scratch must be within it.
- `scratch_roots`: each job may use only a separate, empty subdirectory under it; **must be on a fixed physical non-system drive**; do not use the C drive or network/mapped drives. `init-config` automatically selects the data drive with the most free space; both the preflight and `plan` block system-drive paths.
- `preferred_scratch_drives`: optional local drive-letter preference, e.g. `["D:"]`. Written by `init-config --prefer-drive D:`; the preflight audits whether scratch lands on that drive. Drive-letter preferences vary by machine—specify according to your actual situation; do not copy the example verbatim.
- `allow_scratch_on_system_drive`: defaults to false. Set it to true only when the user has explicitly given written approval to accept the risk of filling the system drive; not for real production cases.
- `max_total_cpus`: physical-core budget; constrained together with `max_concurrent` and the total memory budget.
- An existing solver that is unregistered/unrecognized blocks new submissions; it does not silently take over old queue resources.
- Paths containing cmd metacharacters are rejected; use a safe working path instead—do not disable validation.

## 3. CLI usage

The paths below are examples only; on other machines, replace them with your extraction location. The example INP/region names are contract templates only and do not imply an immediately submittable model exists.

```powershell
$abaqusPython = '<PYTHON_EXE>'
$abaqusBridge = '<SKILL_DIR>\scripts\abaqus_agent.py'
& $abaqusPython $abaqusBridge init-config --output 'D:\new_project\agent_config.json'  # new machines only; verify after generation
& $abaqusPython $abaqusBridge validate-config --query-release  # pre-submission preflight; if BLOCKED, fix config/host first
& $abaqusPython $abaqusBridge doctor --query-release
# if solve_readiness.verdict is BLOCKED_BY_AGENT_INJECTION, do not submit a real solve on this host
& $abaqusPython $abaqusBridge plan --request 'D:\my_authorized_project\request.json'
```

Review the returned `sealed`, `command_preview`, and `plan_token`; after the user approves the job and its numerical/resource/stop policy:

```powershell
& $abaqusPython $abaqusBridge submit --request 'D:\my_authorized_project\request.json' --plan-token '<token-from-plan>' --authorize --authorization-note 'user approved the exact job, resources and stop policy'
& $abaqusPython $abaqusBridge status --job-id '<32-char-id-from-submit>'
# failure or empty ODB frames: one-click root-cause attribution (also works for historical jobs not managed by this skill; path must be within allowed_roots)
& $abaqusPython $abaqusBridge triage --workdir 'D:\my_authorized_project\job_dir' --job 'JOB_NAME'
```

The token is not a license/password; it is bound to the plan content. After any change to inputs, include, user code, local env, backend code, or configuration, the plan must be redone. `authorize=true` is a human authorization recorded by the caller, not authentication against malicious clients. MCP clients should still enable tool approval.

When reading an ODB, first run inventory and use its real step/region; do not pick "the largest displacement that looks like an RP":

```json
{"mode":"inventory","odb":"<EXAMPLE_ODB>"}
```

Save as a new request file, then run `probe --request <file path>`. Fill in `assets/odb_peak_request.example.json` based on the inventory. New evidence is written to the registry; the original ODB is read-only.

## 4. WorkBuddy and other MCP agents

Choose a client that supports **local stdio MCP** and add one server. Import UI and config file locations differ between products; this package does not modify WorkBuddy settings on its own, nor does it assume it supports any proprietary skill format.

An importable example JSON: `assets/mcp_client.local.example.json`. Its common `mcpServers` form is:

```json
{
  "mcpServers": {
    "CCC-abaqus-local-simulation": {
      "command": "<PYTHON_EXE>",
      "args": [
        "<SKILL_DIR>/scripts/mcp_server.py",
        "--config",
        "<SKILL_DIR>/assets/local_config.json"
      ]
    }
  }
}
```

If the target agent has no MCP but can invoke the command line: use the CLI JSON interface directly and read SKILL/the handbook. If Skills can be imported: import the complete directory and instruct it to use `$abaqus-local-simulation` or read SKILL.md. The three entry points do not depend on each other.

The target agent must have local command-execution permission or be able to connect to local stdio MCP. Merely sending the Skill text to a cloud agent without local access cannot make it invoke this machine's Abaqus.

**Agent with command permission but still in an injected/isolated sandbox** (e.g., `doctor.host_injection.suspects` contains `tsbx.dll`): it can safely perform `doctor`/`plan`/input audit/`probe` of existing ODBs, but the solver subprocess for a real solve may be crashed by the injected DLL or lose file visibility (appearing as `.dat` with zero errors yet failure, `PART_MAP_HANDOFF`, `input not found`). For such symptoms, first read `references/AGENT_HOST_SANDBOX_EN.md` or the `abaqus://agent-host` resource, and gather evidence with `doctor.solve_readiness`/`triage`; leave real solves to an injection-free host (the user's local terminal/direct MCP).

Suggested first task for other agents:

> Read this package's SKILL.md and README. First run abaqus_doctor, check paths, physical cores, drives, and existing jobs. Only audit the model I provide and generate a plan; do not submit yet; do not change physical parameters, take over old queues, or treat a candidate RF as a peak.

## 5. Validation scope

See `VALIDATION_REPORT.md` and the actual records in `validation/`. Tests cover command planning/protection, peak algorithms, MCP stdio handshake and error paths, as well as read-only Abaqus version queries and read-only tests on existing ODBs. Packaging itself does not submit any new finite-element analysis. If new submission/compilation/restart paths are covered only by simulated tests, the report states this explicitly and does not pass them off as end-to-end validation of new jobs.

License checkout, real solves, user-subroutine version compatibility, and WorkBuddy product UI import still need to be verified at time of use. An abnormal script's nonzero return code and JSON error must not be written up as a physical model failure.

## 6. License and sources

The newly written bridge code is used under the root LICENSE; Abaqus/SIMULIA and official documentation are not superseded by that license. The package does not include third-party software or full documentation text. The MCP implementation follows the [official stdio specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports), the [tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), and the [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle).
