> English version. [中文版](FOR_AI_AGENT.md)



# abaqus-local-simulation — Complete Integration and Execution Instructions for AI Agents

> This document is written for **AI agents** to read, not a human-facing introduction.
> Your user will send it to you along with the repository URL. Following this document, you must
> complete installation, configuration, and health checks from scratch on **your own Windows machine**,
> and, after obtaining authorization, run the first Abaqus job end to end.
>
> Do not ask the human "what should I do next" at any point — this document covers everything. The only times you must stop and wait for the human are the authorization checkpoints listed in §0.3.

---

## 0. Before you begin: goals, prohibitions, authorization checkpoints

### 0.1 Your goal

Complete four things in order:

1. Obtain the code and confirm the local machine has Python 3.9+, Abaqus, and a usable launcher.
2. Use `init-config` to generate a configuration for **this machine**, and use `validate-config` to pass the health check with a verdict of `READY` or `USABLE_WITH_WARNINGS`.
3. Choose one integration method (CLI / local stdio MCP / Skill) and get the read-only capabilities (`doctor`, `probe`) working.
4. After explicit human authorization, run a real job through `plan → submit → status → probe` and report the results truthfully.

### 0.2 Hard prohibitions (stop immediately and report to the human if any is violated)

- **Never** call `submit` or `terminate` without explicit authorization. `authorize=true` is merely a record of human authorization made by the caller, not identity authentication; do not check it yourself on the human's behalf.
- **Never** modify the physical content of the source INP (material parameters, geometry, boundary conditions, contact, mesh) to make the solver run. If a change is required, it must be done in a separate, independent attempt with the change explained, and must not overwrite the original job.
- **Never** treat a candidate peak, `candidate_RF`, an end-point maximum, or a plateau segment as a valid peak; `PEAK_STABLE_PROVISIONAL` defaults to `usable_peak=false`.
- **Never** back-calculate material parameters from a target strength and then claim "validation successful".
- **Never** delete `.lck` files, clean up unknown scratch, `taskkill` solvers not managed by this package, or take over historical queues.
- **Never** claim "solve succeeded" inside an injected sandbox host. A launcher return code of 0, zero errors in `.dat`, and the existence of output files are not evidence of success.
- **Never** claim the license has been verified — `doctor` explicitly states `license_availability=UNVERIFIED`; only a real, authorized job can verify it.
- **Never** treat a raw field average or a single-point ratio as an area/volume-weighted conclusion.
- **Never** mix Standard and Explicit results; the same INP behaves differently under the two solvers.
- **Never** modify `assets/local_config.json` and treat that as "configured" — it is a path example; you must generate your own configuration.
- **Never** place a job's working directory or scratch on the **system drive** (C: on Windows): tens of GB of temporary files can fill the system partition, and IO contention on the system drive can slow the solve or even trigger MPI timeouts. This package blocks this in both `validate-config` and `plan`; do not open `allow_scratch_on_system_drive=true` to bypass it unless the human has explicitly approved in writing and accepted the risk. Scratch must be an absolute path on a non-system physical drive, with one separate empty subdirectory per job; do not use network or mapped drives.

### 0.3 Three checkpoints where you must stop and wait for the human's nod

| Checkpoint | What you need from the human | What you may do only after you have it |
|---|---|---|
| Submit a job | Explicit approval of "this job name, these cpus/memory, these stopping strategies" | Call `submit` with `plan_token`, `--authorize`, and a factual `--authorization-note` |
| Terminate a job | Stop authorization for **this one** managed job | Call `terminate` |
| Enable automatic stopping | Explicit permission to set `terminate_at_walltime` or `stop_after_confirmed_peak` to true | Set them to true in the request |

Apart from these, do not repeatedly interrupt the human over technical details; read the docs first, probe first, diagnose first.

---

## 1. Obtain the code and inventory the local machine

### 1.1 Confirm Python

```powershell
Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
python --version
```

Requires **CPython 3.9 or higher**. If `python` points to a Windows Store placeholder (the version command opens the Store), use either of the following instead:

```powershell
py -3 --version
# Or use the absolute path of Anaconda / an installed Python directly, e.g.:
<PYTHON_EXE> --version
```

Note the usable absolute path; below it is referred to as `$PY`. **Use this absolute path for all subsequent commands** — do not rely on PATH.

### 1.2 Obtain the code

```powershell
$ROOT = '<PROJECT_ROOT>\abaqus-local-simulation'   # Replace with where you intend to put it; the path must not contain & | < > ^ % ! or quotes
git clone https://github.com/<OWNER>/abaqus-local-simulation.git $ROOT
```

If you do not know how to use git, download from the GitHub page via **Code → Download ZIP** and extract it; the result is the same.

Enter the directory:

```powershell
Set-Location $ROOT
Get-ChildItem
```

Confirm at least these entries exist: `LICENSE`, `README.md`, `SKILL.md`, `FOR_FRIENDS.md`, `FOR_AI_AGENT.md`, and the directories `assets/`, `references/`, `scripts/`, `tests/`, `validation/`.

### 1.3 Integrity self-check

```powershell
$need = @(
 'scripts\abaqus_agent.py','scripts\mcp_server.py','scripts\job_worker.py',
 'scripts\host_compat.py','scripts\odb_probe.py','scripts\history_peak.py','scripts\build_package.py',
 'SKILL.md','README.md','references\ABAQUS_CALLING_HANDBOOK.md',
 'references\HOST_COMPATIBILITY.md','references\AGENT_HOST_SANDBOX.md'
)
$missing = $need | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "Missing files: $($missing -join ', ')" }
Write-Output "FILE_CHECK_OK count=$($need.Count)"
```

If any file is missing, re-download it; do not reconstruct it from memory.

### 1.4 Confirm Abaqus exists

No need to find it manually — the skill will auto-detect it. But first confirm the machine actually has Abaqus installed: a typical launcher looks like `<ABAQUS_COMMANDS>\abaqus.bat`, though the actual location varies by installation. If it is absent, this package cannot work — report this truthfully to the human.

---

## 2. Read the docs in order (do not skip)

| Order | File | What you should get from it |
|---|---|---|
| 1 | `SKILL.md` | Main entry point, 9 invariants, minimal operation loop, interface description |
| 2 | `README_EN.md` | Capability table, path examples, migration points, acceptance scope |
| 3 | `references/HOST_COMPATIBILITY_EN.md` | How to configure on a different machine, `auto` capacity rules, degradation behavior, **`validate-config` ten-item verdict table** |
| 4 | `references/ABAQUS_CALLING_HANDBOOK_EN.md` §1–8 | Complete local calling workflow, exact command forms, material/contact/output card cautions |
| 5 | Ibid., §9–11 | Peak, energy, and damage evidence rules — required reading before any strength/damage conclusion |
| 6 | `references/AGENT_HOST_SANDBOX_EN.md` | If you yourself run inside an injected/isolated sandbox, read this first |
| 7 | `references/TROUBLESHOOTING_EN.md` | When something goes wrong, look it up by symptom; no need to read it all upfront |
| 8 | `references/USER_SUBROUTINES_EN.md` | Read only when using UMAT/UINTER/VUMAT/VUINTER; compiler ABI cannot be copied across versions |

Read everything before taking action. In particular, the peak rules in §5 determine whether you can later say "valid peak".

---

## 3. Generate the local configuration

### 3.1 Define path variables

```powershell
$PY     = '<PYTHON_EXE>'                        # Absolute path obtained in §1.1
$ROOT   = '<PROJECT_ROOT>\abaqus-local-simulation'       # The directory from §1.2
$BRIDGE = Join-Path $ROOT 'scripts\abaqus_agent.py'
$CFG    = '<PROJECT_ROOT>\agent_config.json'                 # An absolute path of your choosing; do not place it in the repository
$SCRATCH = '<PROJECT_ROOT>\scratch'                          # Must be on a physical non-system drive (not C:); if this machine has a fixed preference, you can add --prefer-drive D: in init-config
```

All paths must be **absolute** and must not contain `& | < > ^ % !`, quotes, or newlines. Paths containing these characters will be rejected by the security validation; change the path, do not disable the validation.

### 3.2 Generate the config skeleton

```powershell
& $PY $BRIDGE init-config --output $CFG
# If this machine has a clear drive-letter preference (e.g., work always goes on D:), specify it explicitly; do not treat a particular drive letter as a universal default:
# & $PY $BRIDGE init-config --output $CFG --prefer-drive 'D:'
```

This command will:

- Auto-discover `abaqus.bat` from environment variables, PATH, and common install locations on drives C/D/E;
- Discover compilers from PATH and common Visual Studio install locations;
- Derive safe capacity from the local logical core count and physical memory (leaving at least 1 core and 15% memory);
- Generate suggested values for `allowed_roots`, `registry_dir`, and `scratch_roots`.

It will **not overwrite** an existing file; if the target already exists it will error — first confirm whether it was generated by you previously.

### 3.3 Check and modify the config as needed

```powershell
Get-Content $CFG
```

Check each item:

| Field | Correct approach |
|---|---|
| `abaqus_launcher` | Must point to an actually existing `abaqus.bat` / `abaqus.exe`. If it is an empty string, auto-detection failed — fill it in manually. |
| `allowed_roots` | Change to the project root directories you are **actually authorized to read and write**. All INP/include/ODB/work/scratch paths must fall within these roots. |
| `registry_dir` | This package's own job-record directory; do not point it at historical queue files. |
| `scratch_roots` | Change to the scratch root you intend to use (e.g., `$SCRATCH`). This directory **must already exist**, otherwise the launcher will reject the job outright. **It must be on a physical, fixed, non-system drive**; setting it to the system drive will be rejected by both the health check and `plan`. |
| `preferred_scratch_drives` | Optional, e.g., `["D:"]`, expressing **this machine's** scratch drive-letter preference; `init-config --prefer-drive` writes it automatically. The health check audits whether scratch actually lands on that drive. The drive preference is determined by your machine's actual situation, not a universal default. |
| `allow_scratch_on_system_drive` | Defaults to `false`; leave it unchanged. Only change to `true` if the human has explicitly approved in writing and accepted the risk of filling the system drive, and do not use it for real cases. |
| `max_total_cpus` / `max_total_memory_mb` / `max_concurrent` | Integers or `"auto"`. The `capacity.limits` returned by `plan` shows the actually effective values. |
| `min_free_disk_bytes` | Protection lower bound, default 8 GiB. |
| `compiler_candidates` | Only matters when using user subroutines; can be left empty if Fortran is not used. |

**Create the scratch directory** (mandatory, cannot be skipped):

```powershell
New-Item -ItemType Directory -Force -Path $SCRATCH | Out-Null
```

Each individual job must also have its own separate empty subdirectory under the scratch root, e.g., `$SCRATCH\JOB01`; do not share one among multiple jobs.

---

## 4. Pre-submission health check (must pass before proceeding)

```powershell
& $PY $BRIDGE --config $CFG validate-config --query-release
```

This is a **read-only** health check: it creates no project files, submits no jobs, and starts no solver. `--query-release` runs `abaqus information=release` to query the version in an auto-cleaned temporary directory.

### 4.1 Verdict

| `verdict` | Meaning | Your action |
|---|---|---|
| `READY` | All checks passed | Continue to §5 |
| `USABLE_WITH_WARNINGS` | Warnings but no fatal items | Read the `action` of each item; continue once you confirm the warnings are acceptable; if not acceptable, fix first |
| `BLOCKED` | At least one FAIL | **Stop.** Fix each item per the table below, then re-run the health check. Do not modify the model to accommodate the environment. |

### 4.2 Common FAILs and fixes

| Check | Meaning | Fix |
|---|---|---|
| `launcher` | Launcher does not exist or has an unusual extension | Use `doctor`'s `compat.launcher_candidates` to find the real path and put it back in the config |
| `allowed_roots` | Directory does not exist | Create the directory, or change to an actually existing authorized root |
| `registry` | Parent directory missing/not writable | Create the parent directory or grant write permission |
| `scratch_roots` | Directory missing/not writable; or on the system drive | Create the directory (must already exist); if on the system drive, move to a non-system data drive — do not enable `allow_scratch_on_system_drive` to bypass |
| `scratch_disk_policy` | Never FAILs; INFO reports the system drive and candidate data drives | Follow the hint to confirm scratch is on a data drive |
| `capacity` | `auto` resolution failed or illegal value | Change the three capacity keys to integers or `"auto"` |
| `free_disk` | Available space below the lower bound | Free up space; do not lower `min_free_disk_bytes` without authorization |
| `host_injection` | Injected DLL such as `tsbx.dll` detected | **Change hosts**: use an injection-free local terminal for the real solve; the current host can only do auditing and ODB post-processing |

Clear boundary: passing the health check ≠ successful license checkout ≠ passing datacheck. These are three different pieces of evidence.

### 4.3 Additional probe (optional but recommended)

```powershell
& $PY $BRIDGE --config $CFG doctor
```

Focus on three fields:

- `solve_readiness.verdict`: if it is `BLOCKED_BY_AGENT_INJECTION`, the current host cannot run a real solve;
- `compat.launcher_candidates` / `compat.compilers`: confirm the auto-discovery results;
- `release_query.parsed.version` (when `--query-release` is added): the example validation environment is `2023`; for other versions you must verify keywords and ABI yourself.

---

## 5. Choose an integration method

### 5.1 Method A: pure command line (most robust; get this working first)

All commands take the form `& $PY $BRIDGE --config $CFG <command>`. You have already used `init-config` / `validate-config` / `doctor`; the rest are:

| Command | Purpose | Key parameters |
|---|---|---|
| `plan` | Freeze input hashes, generate a plan token, **no solving** | `--request <request.json>` |
| `submit` | Submit one managed job | `--request` `--plan-token` `--authorize` `--authorization-note` |
| `status` | Query status, includes triage root-cause fields | `--job-id <32-char id>` |
| `terminate` | Stop **this one** managed job | `--job-id` `--authorize` `--authorization-note` |
| `restart-audit` | List restart file inventory (not status verification) | `--directory` `--job` [--solver] |
| `probe` | Read-only ODB inventory / peak | `--request <odb_request.json>` |
| `triage` | Classify the root cause of a failed job | `--workdir <job directory>` `--job <job name>` |

Use `--help` at any time to check exact parameters:

```powershell
& $PY $BRIDGE --help
& $PY $BRIDGE plan --help
```

### 5.2 Method B: local stdio MCP (for AI clients)

Use the contents of `assets/mcp_client.local.example.json` as a template, replacing with your absolute paths:

```json
{
  "mcpServers": {
    "abaqus-local-simulation": {
      "command": "<PYTHON_EXE>",
      "args": [
        "D:\\AI_ABAQUS\\abaqus-local-simulation\\scripts\\mcp_server.py",
        "D:\\AI_ABAQUS\\agent_config.json"
      ]
    }
  }
}
```

Import this configuration into a client that supports **local stdio MCP**. Connection sequence:

```
initialize → notifications/initialized → tools/list → abaqus_doctor
```

There are **10 tools** in total:

| Tool | Read-only / controlled |
|---|---|
| `abaqus_doctor` | Read-only |
| `abaqus_plan_job` | Read-only, no solving |
| `abaqus_submit_job` | Controlled, requires authorization parameters |
| `abaqus_job_status` | Read-only |
| `abaqus_terminate_job` | Controlled, requires stop authorization |
| `abaqus_restart_audit` | Read-only |
| `abaqus_probe_odb` | Read-only; writes a new audit JSON, does not modify the ODB |
| `abaqus_triage_job` | Read-only |
| `abaqus_host_compat` | Read-only; run first when changing machines |
| `abaqus_validate_config` | Read-only; mandatory before submission |


There is **no** arbitrary shell tool and no network listener. This means: even if your AI client has no command-line access, you can still use these tools for configuration health checks and ODB analysis; but a real solve still requires local authorization.

### 5.3 Method C: install as a Skill

If your AI client supports Skills, place the entire `abaqus-local-simulation` directory into its skills directory, then instruct it to read `SKILL.md`. All three entry points share the same backend, so there is no issue of "one agent reports RUNNING while another computes from a stale cache".

---

## 6. Run the first real job

This step requires the human to provide: a valid INP (and all its `*INCLUDE` dependencies), plus the submission authorization from §0.3.

### 6.1 Prepare the request file

Copy `assets/job_request.example.json` and fill in the fields:

| Field | Description |
|---|---|
| `job` | Starts with an ASCII letter, at most 64 characters, containing only alphanumerics, `_`, and `-`. **Use a unique name**; do not reuse a historical job name. |
| `input` | Absolute path of the INP, must be within `allowed_roots`. |
| `workdir` | A dedicated empty directory; do not point to an old results directory. |
| `scratch` | A separate empty subdirectory under `scratch_roots`; must already exist. |
| `solver` | `standard` or `explicit`, defaults to `standard`. |
| `operation` | `analysis` or `datacheck`. **For the first run, `datacheck` is recommended** to validate the input cards — it is not model validation. |
| `cpus` / `memory_mb` | Fill in according to the capacity limits in §3.3; do not exceed them. |
| `additional_files` | List of external `FILE=` dependencies, Fortran includes, header files, etc. `*INCLUDE` is discovered recursively automatically, but these are not. |
| `user_subroutine` | Absolute path of the user subroutine (if used). Compiler compatibility must be verified separately. |
| `oldjob` / `restart_state_verified` / `restart_evidence` | Fill in only when using `*RESTART, READ` with verified state. An ODB is not a restart state. |
| `walltime_limit_seconds` | Wall-time budget. |
| `terminate_at_walltime` / `stop_after_confirmed_peak` | Default false; to change to true you must first obtain the authorization from §0.3. |
| `probe` | Optional real-time probe request (step / history_regions / axis). |

### 6.2 Audit the plan

```powershell
& $PY $BRIDGE --config $CFG plan --request '<request.json>'
```

In the return value, focus on:

- `sealed`: frozen input/include/code/environment hashes;
- `command_args` and `command_preview`: the commands that will actually be executed;
- `capacity`: includes `limits`, showing the effective CPU/memory/concurrency caps;
- `host_readiness`: the host verdict before submission;
- `plan_token`: needed for the next step; it binds all of the above.

**This step produces no solve files.** Read each item before deciding whether to submit.

If `host_readiness.verdict` is `BLOCKED_BY_AGENT_INJECTION`, change hosts first — do not submit.

### 6.3 Submit (requires authorization)

After obtaining explicit human approval of "this job / resources / stopping strategy":

```powershell
& $PY $BRIDGE --config $CFG submit --request '<request.json>' --plan-token '<token>' --authorize --authorization-note 'Human has approved this job name, cpus/memory, and the stopping strategy in the request'
```

Notes:

- The token is not a password; it is a hash of the plan contents. If any of the input, includes, user code, backend code, or config changes, you must redo `plan`.
- One job gets one persistent record and one background worker. Do not submit the same job twice.
- When an "unknown live solver" is encountered, this package refuses submission — do not try to work around it.

### 6.4 Monitoring

```powershell
& $PY $BRIDGE --config $CFG status --job-id '<32-char id>'
```

`status` compares the PID creation time with the original logs and returns:

- `observed_state`: the real current state; `STALE_RECORD_NEEDS_RECONCILIATION` or `ORPHANED_LAUNCHER` means manual reconciliation is needed, not a reason to resubmit;
- `terminal`: tails of the raw `.log/.msg/.sta/.dat` + `exception_kinds`;
- `triage`: automatic root-cause classification (`root_cause` / `confidence` / `basis` / `recommended_action`).

**Do not** assume the job is cancelled just because the client exited. The worker is an independent process.

### 6.5 Classify on failure

```powershell
& $PY $BRIDGE --config $CFG triage --workdir '<job directory>' --job '<job name>'
```

This command can also analyze **historical jobs** (as long as the path is within `allowed_roots`). Root-cause classes:

| `root_cause` | Meaning | Response |
|---|---|---|
| `HOST_SANDBOX_DEFECT` | Injection/process isolation/`.prt` handoff broken | Change to an injection-free host; **do not modify material or mesh** |
| `EXTERNAL_INTERRUPT` | External ABORT/INTERRUPT | Find out who stopped it; it is not numerical non-convergence |
| `MODEL_INPUT_ERROR` | `.dat` contains `***ERROR` | Fix the input cards and start a new datacheck |
| `NUMERICAL_CONVERGENCE` | Too few/too many increments, negative eigenvalue, excessive distortion | Check loading/contact/mesh/stabilization; do not modify the original model |
| `LICENSE_UNAVAILABLE` | License problem appears in logs | Verify the license separately |
| `SOLVER_CRASH_UNATTRIBUTED` | Access violation with no injection detected | Check `.exception` and subroutine ABI |
| `SUSPECTED_HOST_SANDBOX` | Injection + abort but insufficient evidence | First reproduce on an injection-free host |
| `NO_FAILURE_EVIDENCE` | Completion marker present | Do not treat rc0/completion as a peak |
| `UNDETERMINED` | No decisive evidence | Inspect the raw logs manually; an empty ODB cannot explain the cause |

---

## 7. Rules for reading ODB and drawing conclusions

### 7.1 Inventory first, then peak

```powershell
# Write odb_request.json, first use inventory mode
& $PY $BRIDGE --config $CFG probe --request '<odb_request.json>'
```

The request must at least give the absolute path of `odb`. Inventory returns the real `steps`, `history_regions`, field names, and field keys.

**Do not guess region names.** Common traps: `historyRegions` is a Repository in Abaqus Python 2.7 and requires `.keys()`; energy regions look like `Assembly ASSEMBLY`; loading points look like `Node SPECIMEN-1.9001`.

### 7.2 Hard requirements for peak mode

- You must specify a `step`, `history_regions`, and `axis` that **exist exactly**.
- With multiple loading nodes, RF3 must be **signed-summed first, then have its amplitude taken**; do not take a single node or sum absolute values.
- Only paired, finite RF/U points support peak evidence; end points, candidate maxima, and `candidate_RF` are diagnostic only.
- `PEAK_STABLE_PROVISIONAL` defaults to `usable_peak=false`; using it requires an explicit usage policy from the human first.
- Check the `ALLKE/ALLAE/ALLSD` energy gates and field time offsets; if something is missing, write `missing` — do not fill it in by assumption.
- Variables that are not requested do not appear in the ODB (e.g., SDEG must be explicitly output). Cohesive `STATUS=1` means **not damaged**, which is not sufficient evidence of "not cracked"; look at `SDEG`.

### 7.3 Conclusions you **cannot** draw

- Do not say "target achieved" — unless there is a real valid peak + energy gates + a human-confirmed target definition.
- Do not describe a standard-part/single-point field average as area-weighted damage.
- Do not directly treat a Standard peak as an Explicit prediction, or vice versa.
- Do not infer "no contact force/damage" from "no CPRESS/SDEG" — first look at all field keys and output requests.

---

## 8. If you yourself run inside an injected/isolated sandbox

Some AI hosts inject a DLL (such as `tsbx.dll`) into every child process and give each child process an independent filesystem view. The symptoms are highly misleading:

- Zero errors in `.dat`, a normal `END OF USER INPUT PROCESSING`, and a correct PROBLEM SIZE;
- but the launcher reports `Analysis Input File Processor exited with an error`, and the ODB has **zero frames**;
- or it reports `could not be located: <absolute path>.inp` or `part map file ... does not exist / corrupt`.

Determination and handling:

1. Use `doctor` to look at `solve_readiness.verdict` and `host_injection.suspects`;
2. Use `triage` on the failed job to look at `exception_kinds` (`PART_MAP_HANDOFF` / `FAIL_FAST_INJECTED_HOST` are host evidence, not model problems);
3. Conclusion: the current host can **only** do `doctor` / `plan` / input auditing / `probe` of existing ODBs;
4. Hand the real solve over to an **injection-free host machine's ordinary terminal** — i.e., have the human run it in their own terminal; do not try to bypass it yourself.

Absolutely do not modify material, mesh, or contact parameters to "fix the model" because of these errors.

---

## 9. Troubleshooting decision tree (check in order, do not skip)

| Symptom | Check first | Forbidden action |
|---|---|---|
| `validate-config` is BLOCKED | The `action` of each item | Do not submit; do not modify the model |
| Submission rejected, says unknown solver | Existing solver processes and job ownership | Do not assume idle cores; do not take over |
| Cache shows RUNNING but no process | PID creation time, system boot time, STA/ODB modification times | Do not heartbeat indefinitely; do not auto-resubmit |
| Launcher returns 0 but no results | Actual contents of `.log/.dat`, probe JSON schema | Do not treat rc0 as success |
| `.lck` exists | Whether the original job / PID / ODB is still writing | Do not delete the lock to unblock |
| Input processor fails | Each `.dat` ERROR, keywords/data columns/IDs/sets/OP/materials | Do not "fix syntax" by changing strength |
| RF abnormally small/large | Loaded area, units, RP/node sets, sumRF, BC location | A single node is not the total force; keep N/MPa/tonne-density separate |
| Standard keeps cutting back | MSG minimum vs maximum increments, STA accepted trend, localstate/eigenvalues | Do not mix the two terminal causes; end-point max is not a peak |
| X=Y does not change with Ks/strength | slip/traction/QUADSCRT/SDEG, bulk, activation path | Stop parameter sweeping if the parameter is not active |
| Python2 TypeError opening ODB | Whether the path is unicode, filesystem encoding | Fix the read interface; do not declare the model physically INVALID |
| Cannot find CPRESS/SDEG | All field keys, contact suffixes, cohesive elements vs contact vs UINTER | Do not fabricate variables |
| Incomplete info after changing machines | `doctor.hardware_degraded`, `compat.powershell`, `launcher_candidates` | Detection failure ≠ model problem |

For deeper attribute classification, see `references/TROUBLESHOOTING_EN.md`.

---

## 10. Completion report format

After everything is done (or if it fails midway), output a **structured report** to the human, containing at least:

1. **Local machine and config**: Python path, Abaqus version, launcher path, absolute config file path, `validate-config` verdict and counts of each item.
2. **Integration method**: which of CLI / MCP / Skill you chose, and why.
3. **Job status**: job name, operation, whether plan_token was generated, whether authorization was obtained, job_id, observed_state.
4. **Evidence**: `terminal` completion/abort markers, `triage.root_cause`, frame count from ODB inventory, peak status (`PEAK_VALID` / `PEAK_STABLE_PROVISIONAL` / `NO_CONFIRMED_PEAK`) and `usable_peak`.
5. **What could not be verified**: license checkout, subroutine ABI, keyword compatibility of other versions — state these explicitly; do not gloss over them.
6. **Next-step recommendations**: give them only when supported by evidence; do not use "try again" as a substitute for diagnosis.

If any step fails, the report must state which step failed, what the raw evidence was, and what you ruled out. A non-zero return code from an abnormal script and a JSON error do not equal "physical model failure".

---

## 11. The whole rulebook in one sentence

> Health-check before planning; authorize before submitting;
> Separate evidence into host and model; separate peaks into candidate and valid;
> Do not modify the source model to accommodate the solver; do not treat zero errors as success.

The skill version this document corresponds to: take `SKILL.md` and `README.md` in the repository as authoritative; if the two conflict, the actual behavior of the code (the behavior covered by `tests/test_bridge.py`) is authoritative.
