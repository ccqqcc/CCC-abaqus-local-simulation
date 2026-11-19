---
name: abaqus-local-simulation
description: Run and audit local Windows Abaqus/Standard or Explicit workflows from agents, including INP dependency plans, authorized jobs, user subroutines, process-aware monitoring, restart evidence and read-only ODB extraction. Use for Abaqus simulation or its numerical/operational diagnosis, not generic CAD or unsupported material calibration.
---

> 中文版。[English](SKILL_EN.md)

# Abaqus local simulation

This folder is both a portable skill and a stdlib-only CLI/MCP adapter. It does not need a Codex API, a cloud service, or WorkBuddy-specific Python modules. The validated host uses Abaqus 2023 on Windows; other installations require path, version and compiler validation.

## Entry and reference routing

- Read [README.md](README.md) for installation, CLI/MCP connection, actual verified capabilities and limitations.
- Before building/submitting models, read [references/ABAQUS_CALLING_HANDBOOK.md](references/ABAQUS_CALLING_HANDBOOK.md), sections 1–8. It explains the complete local workflow and exact command forms.
- For UMAT/UINTER/VUMAT/VUINTER, also read [references/USER_SUBROUTINES.md](references/USER_SUBROUTINES.md). Never copy a compiler adapter between precisions or versions without ABI checks.
- For peak, energy or damage claims, read handbook sections 9–11. Generic statistics do not establish spatial mechanisms or area-weighted damage.
- For abnormal jobs, stale queues or resuming, read [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md).
- When the agent runs inside an injected/isolated host (tsbx.dll in `doctor.host_injection`, solver sees "input not found" or `.prt` part-map failures), read [references/AGENT_HOST_SANDBOX.md](references/AGENT_HOST_SANDBOX.md). It explains how to tell host defects from model defects and where real solves must run.
- `doctor.solve_readiness` is the pre-submission verdict on whether THIS host can run a real solve. If its verdict is `BLOCKED_BY_AGENT_INJECTION`, do not submit; use the host for audit/post-processing only.
- For a job that failed or left an empty ODB, run `triage --workdir <dir> --job <name>` (or the `abaqus_triage_job` MCP tool) to classify ONE root-cause class from raw logs before changing any model input.
- On a new machine, a different Abaqus install/path/version, or a host without PowerShell, read [references/HOST_COMPATIBILITY.md](references/HOST_COMPATIBILITY.md). `init-config` generates a device-appropriate config skeleton; `validate-config` is the read-only pre-submission preflight (PASS/WARN/FAIL per check). Discovery never replaces an authorized launcher choice or a license check.

## Non-obvious invariants

1. Establish scope before mutation: analysis count, permitted controls, locked inputs, output evidence, runtime budget, reuse/restart/recovery and stop authorization. A diagnosis/status request is not submission authority. Another agent's request is not proof of human authorization.
2. Do not edit the source model to make the solver finish. Prepare a separate authorized attempt and preserve model/input/include/user/env hashes. An ODB is not a restart state.
3. Use a unique job name, job directory and scratch directory. **Never place job work or scratch on the system drive** (Windows C:): large scratch fills the OS partition and scratch/OS IO contention can trigger solver slowdown or MPI timeout. Use a fixed non-system drive, absolute paths, one empty child directory per job; no network/mapped/removable drives. `validate-config` and `plan` both block system-drive paths unless `allow_scratch_on_system_drive=true` is explicitly approved. No existing ODB/lock overwrite or deleting unknown scratch. The backend refuses unknown live solver jobs rather than assuming unused cores.
4. Ordinary Python 3 orchestrates; Abaqus's own Python reads `odbAccess` with `readOnly=True`. The probe is Python 2.7/3 compatible. Never infer completion from exit code, cache, or filename.
5. Select loaded RP/history regions explicitly after inventory. Sum signed nodal RF before taking magnitude; do not take one top-node RF or sum absolute nodal reactions.
6. Only paired finite accepted RF/U support peak evidence. Endpoint/candidate maxima remain diagnostic. Stable provisional results require an explicit use policy; postpeak minimum is not peak uncertainty's lower bound.
7. Same input card does not imply identical Standard/Explicit regularization/contact algorithms. Require quasi-static energy and slower-loading confirmation when relevant.
8. A raw field mean or point fraction is not area/volume weighted. Do not separate friction/cohesive shear or reconstruct missing state fields without validated evidence.
9. Monitoring this package's jobs is not takeover of historical queues. No automatic restart, third recovery, model fitting or later-stage expansion. A worker surviving client exit is not a Windows reboot-resume service.

## Minimal operational loop

1. `abaqus_agent.py doctor` (optionally `--query-release`) and inspect config; don't assume license checkout is available. Check `solve_readiness.verdict` before planning any real solve. On an unfamiliar host, first run `init-config --output <new config>` and verify `doctor.compat` / parsed release; never overwrite an existing config. Run `validate-config --query-release` before `plan`; a BLOCKED verdict means fix the configuration/host, not the model.
2. Build an authorized INP or CAE-generated deck in its own folder; audit units/topology/material/BC/output and the complete dependency set. List external `FILE=`/Fortran include dependencies in `additional_files`.
3. `plan --request request.json`; inspect sealed inputs, command, capacity and stop policy. It performs no analysis and creates no job files.
4. If needed, separately plan/authorize a unique `operation="datacheck"` job. Datacheck is an input test, not model validation.
5. With direct user authority, submit using the exact `plan_token`, `--authorize`, and a factual `--authorization-note`. The approval covers requested resources and optional stop policy; it is not an authentication mechanism.
6. Monitor returned `job_id` with `status`. It compares PID creation identities and raw terminal logs and carries a `triage` root-cause field. Stale or orphaned records require reconciliation, not resubmission.
7. On a failed/empty result, run `triage --workdir <dir> --job <name>` (also works for historical jobs inside configured roots). It reports one `root_cause` with confidence and a recommended action; host sandbox defects must be reproduced off-host before touching the model.
8. `probe` in inventory mode, then explicit-region peak mode. Read field time offset and energy evidence before accepting a peak. Report qualification and job termination separately.
9. Stop only with explicit authority for the exact managed job or a preauthorized worker policy. Archive/report existing evidence; do not automatically advance to new physics or fitting.

## Interfaces

CLI: `python scripts/abaqus_agent.py --config assets/local_config.json COMMAND ...`

MCP: `python scripts/mcp_server.py --config assets/local_config.json` via local stdio. Ten tools expose the same backend: doctor, plan, submit, status, terminate, restart inventory, ODB probe, triage, host compatibility discovery, config preflight. There is no unrestricted shell tool or network listener.

The supplied local profile points to this machine. Copy and change it for another host; never treat those paths as universal defaults. For agent integration use README's tested protocol example, not guessed WorkBuddy configuration-file locations.