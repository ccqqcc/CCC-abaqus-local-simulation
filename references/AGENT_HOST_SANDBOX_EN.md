> English version. [中文版](AGENT_HOST_SANDBOX.md)



# Impact of the Agent Host Environment on Abaqus Child Processes (Empirical Diagnosis and Boundaries)

Scope: the agent has local command-execution permission but runs in a host with **process injection** or **process-level filesystem isolation** (e.g., sandboxed desktop agents such as WorkBuddy/Cursor). This document only addresses "whether the invocation can succeed"; it does not change any physical/material/acceptance contract. Ordinary local direct runs on hosts without injection can ignore this document.

## 1. Why doctor Must Check host_injection First

`doctor` now returns a `host_injection` field, using Toolhelp32 to enumerate modules loaded by the **current python process**; hits on `tsbx.dll`/`sandbox`/`inject` etc. are listed as `suspects`.

- A `tsbx.dll` hit: the host injects a DLL into every child process it starts. Abaqus's `pre.exe`/`standard.exe`/`explicit.exe` may crash with `0xc0000409` (fail-fast) after loading, or exhibit inexplicable file-visibility errors.
- This is **host evidence**, not a verdict that "this model will definitely fail"; however, it explains the class of anomalies where "the solve fails with zero errors." When `suspects` are present, prefer to run the real solve on a host without injection (user's local terminal / direct MCP connection).
- The detection is read-only; it does not change configuration, submit jobs, or shut down the host sandbox.

`doctor` now also returns `solve_readiness`, giving a **pre-submission verdict**:

| verdict | suitable | Meaning |
|---|---|---|
| `BLOCKED_BY_AGENT_INJECTION` | false | Injection DLL detected in the current process; do not submit a real solve on this host; use plan/audit/ODB post-processing instead |
| `READY_LICENSE_UNVERIFIED` | true | No injection detected and launcher exists; license checkout still unverified; first use `doctor --query-release` |
| `NO_LAUNCHER` | false | Configured launcher does not exist; fix the configuration |
| `UNSUPPORTED_HOST` | false | Non-Windows, outside the verified scope |

"No injection detected" does **not** mean the child-process environment is clean: the detection covers only DLLs visible to the current python process. This verdict is only a static host judgment; it does not prove the license is available, nor that the model is valid.

Diagnostic order: first run `doctor` and check `solve_readiness.verdict` and `host_injection.suspects`; on failure use `triage --workdir <dir> --job <name>` (or MCP `abaqus_triage_job`) to obtain a single `root_cause`; only suspect the model/numerics themselves when both point to the model.

## 2. Root-Cause Classification by terminal_evidence.exception_kinds

Abaqus writes `<job>.<seq>.exception` when a solver rank exits abnormally. Some failures (especially Standard's part-map handoff) leave traces only here: `.dat` may have zero errors, `.log` may proceed normally to `END OF USER INPUT PROCESSING`, `PROBLEM SIZE` may be correct, yet the ODB has no frames.

`terminal_evidence()` now parses these files and gives `exception_kinds`:

| kind | Typical Details | Meaning / Handling |
|---|---|---|
| `PART_MAP_HANDOFF` | `part map file ... does not exist / corrupt` | Standard's `.prt` part-map file was not read by the solver; commonly caused by process-level FS isolation or broken scratch handoff. Do not modify materials/mesh to "fix" it |
| `FAIL_FAST_INJECTED_HOST` | `0xc0000409` / fail-fast | Host-injected DLL causes child-process fail-fast; unrelated to the model; switch to a host without injection |
| `ACCESS_VIOLATION` | `0xc0000005` | Solver segmentation fault; may relate to injection, memory, or Abaqus itself; check the call stack and event log before judging |
| `EXTERNAL_INTERRUPT` | `INTERRUPT/ABORT signal` | External termination (wall-time policy, user kill, or host reclamation); not numerical non-convergence |

`exception_files` retains the raw `description`/`details`/`phases` for review. The criteria are evidence, not a general causal diagnosis.

## 2b. One-Click Classification: triage

Manually piecing together `.dat`, `.msg`, and `.exception` is error-prone. Use `triage --workdir <job directory> --job <job name>` (MCP: `abaqus_triage_job`) to classify the evidence into **one** `root_cause`; it only reads files, does not modify the model, and does not restart jobs. `status` also automatically carries the same `triage` for managed jobs.

| root_cause | Triggering Evidence | confidence |
|---|---|---|
| `HOST_SANDBOX_DEFECT` | `PART_MAP_HANDOFF`/`FAIL_FAST_INJECTED_HOST` exceptions; or access violation + injection detected | HIGH/MEDIUM |
| `EXTERNAL_INTERRUPT` | `.exception` reports ABORT/INTERRUPT signal | HIGH |
| `MODEL_INPUT_ERROR` | `.dat` has `***ERROR` | HIGH |
| `LICENSE_UNAVAILABLE` | license-related text appears in logs | MEDIUM |
| `NUMERICAL_CONVERGENCE` | minimum increment / too many increments / negative eigenvalues / excessive distortion | MEDIUM |
| `SOLVER_CRASH_UNATTRIBUTED` | access violation but no injection detected in the current process | MEDIUM |
| `SUSPECTED_HOST_SANDBOX` | injection + abort marker present, but no clear solver evidence | LOW |
| `NO_FAILURE_EVIDENCE` | completion marker present; do not treat rc0/completion as a peak | LOW |
| `UNDETERMINED` | no decisive evidence; an empty ODB alone cannot explain the cause | LOW |

Priority: explicit solver exception > `.dat` input error > license/numerical markers > injection suspicion > undetermined. Each result carries `basis`, `evidence_summary`, and `recommended_action`. This is heuristic classification; it does not prove the model is correct.

Real samples: `JOB_ALPHA` → `HOST_SANDBOX_DEFECT` / HIGH; `JOB_BETA` → `EXTERNAL_INTERRUPT` / HIGH.

## 3. Key Points for Invocation under Injection/Isolation Hosts (Empirical Observations)

The following are empirically observed phenomena on Abaqus + injection-sandbox hosts; use these for troubleshooting when encountering similar symptoms; specific manifestations vary by version and host:

1. **Absolute-path `input=` may fail under `cmd /d /s /c` wrapping**: the solver reports `could not be located: <absolute path>.inp` even though the file exists in the agent's view. You can first `cd`/`cwd` to the job directory and retry with the relative filename `input=<job>.inp`. This is an invocation-path issue; do not modify the INP content.
2. **`.prt` handoff failure is a manifestation of process-level FS isolation**: `pre.exe` writes the part-map file, but another child process (`standard.exe`) cannot read it in the isolated view, manifesting as `PART_MAP_HANDOFF`. It is unrelated to scratch location, cpus, or the model; if an input known to succeed reports the same error again on the same host with the same method, that disproves a "model problem."
3. **`scratch` must exist in advance**: a nonexistent scratch subdirectory causes the launcher to reject directly; this is a separate matter from isolation, so rule it out first.
4. **Hand the real solve to a host without injection**: use the user's local terminal, or a direct MCP connection without injection, to execute `submit`. Injection-bearing hosts are suitable for `plan`/input audit/`probe` of existing ODBs (`abaqus python` reading ODB usually works because it does not start the solver child-process chain).
5. **Do not treat a launcher return of 0 or a `.dat` with no errors as a successful solve**: rely on `terminal_evidence`'s completion marker + ODB frames/SDEG evidence.

## 4. Capability Boundaries

- This document provides no general method to "shut down the host sandbox" or "bypass injection"; that belongs to host configuration and is not determined by this skill.
- After upgrading this skill's code, the sealed hashes of historical `RUNNING`/`SUPERVISOR_FAILED` records will not match the new code; these stale records already require reconciliation and must not be directly treated as resumable jobs.
- Injection detection covers only the current python process; if the solver is started via a different chain (a different parent process), verification must be performed separately on that chain.
