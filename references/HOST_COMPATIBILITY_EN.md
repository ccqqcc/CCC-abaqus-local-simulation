> English version. [中文版](HOST_COMPATIBILITY.md)



# Cross-Device Compatibility and Migration (Detection, Degradation, Configuration Generation)

This document explains how this package adapts to **different Windows machines**: different Abaqus installation paths/versions, different PowerShell versions, different CPU/memory/disk layouts, and different path case conventions. All detection is read-only; it does not start the solver, does not modify existing configurations, and does not prove license checkout.

The original verification environment is Windows + Abaqus 2023. Other versions/installation forms can only be confirmed on the target machine using `doctor --query-release` and one authorized input verification; keywords, contact algorithms, or subroutine ABI must not be assumed to be fully identical.

## 1. What Is Automatically Detected

| Detection Item | Entry Point | Source and Order |
|---|---|---|
| PowerShell | `doctor.compat.powershell`, `abaqus_host_compat` | `powershell.exe` → `pwsh.exe` → `powershell`/`pwsh` in PATH → standard Windows system directories |
| Abaqus launcher | `doctor.compat.launcher_candidates` | Environment variables `ABAQUS_BAT`/`ABAQUS_COMMAND`/`ABAQUS_HOME`/`SIMULIA_HOME` → PATH → `SIMULIA/Commands` and `SimulationServices/V6R*/.../Commands` on drives C/D/E |
| Fortran/linker | `doctor.compat.compilers` | `ifx`/`ifort`/`link`/`clang`/`gcc` in PATH → `Hostx64/x64/link.exe` of common VS BuildTools/Community/Professional/Enterprise |
| Hardware | `doctor.hardware`, `hardware_degraded` | Prefer CIM/WMI (via PowerShell); when unavailable, fall back to `os.cpu_count` + `GlobalMemoryStatusEx`, labeling `source` |
| Abaqus version | `release_query.parsed.version` of `doctor --query-release` | Parse `abaqus information=release` output; on parse failure return a structured null value, do not exit with an error |

`launcher_candidates` is only **discovery**; it does not switch automatically. The active launcher is always `abaqus_launcher` in the configuration; when changing machines, check the candidates first, then update the configuration.

## 2. One-Click Generation of Target-Machine Configuration

```powershell
$py = '<PYTHON_EXE>'
$bridge = 'C:\path\to\CCC-abaqus-local-simulation\scripts\abaqus_agent.py'
& $py $bridge init-config --output 'D:\new_project\agent_config.json'
```

The generated content consists of **suggested values** and will not overwrite existing files:

- `abaqus_launcher`: the first detected candidate (empty string if none found; must be filled in manually)
- `allowed_roots`: the directory containing the output file (expand as needed to the truly authorized project root)
- `registry_dir`: `agent_integrations/abaqus_runtime` under that directory
- `scratch_roots`: `scratch` under that directory (**must be created in advance**, otherwise the launcher rejects the job)
- `max_total_cpus` / `max_concurrent` / `max_total_memory_mb`: derived from local hardware, reserving at least 1 logical core and 15% of memory
- `compiler_candidates`: absolute paths of compilers found in PATH/common installation locations

After generation, proceed in order: `doctor` → `validate-config --query-release` → create scratch → `plan`. If any step does not match, fix the configuration first; do not modify the physical model to accommodate the environment.

## 2a. Work Directory and scratch Must Never Be on the System Drive (Mandatory Policy)

This is a hard rule repeatedly verified through extensive engineering practice; this package implements it as a **code-level interception**, not merely a documentation reminder:

- **Why problems occur**: nonlinear analysis generates tens to hundreds of GB of temporary files. Having scratch default to the C drive fills up the system partition, causing freezes, crashes, and interrupted jobs that must be restarted; concurrent reads/writes on the system drive also compete with the OS for IO, slowing the solve and even triggering MPI communication timeouts during parallel jobs. A common consensus in community experience is that "80% of large-model computation crashes are caused not by insufficient memory but by scratch IO throughput hitting its ceiling."
- **Correct approach**: point scratch to a **physical fixed disk (DRIVE_FIXED) that is not the system drive**, preferring high-speed SSD/NVMe, using an absolute path; one independent empty subdirectory per job; do not use network/mapped/removable drives (low-latency random IO is destroyed by network latency).
- **Experience with a three-drive split**: the C drive holds only the system and software; the D/data drive holds projects, scratch, and computation output; an archive drive holds completed results as cold data. This package does not mandate specific drive letters, only "non-system drive + fixed drive."

This package's implementation:

| Location | Behavior |
|---|---|
| `init-config` | Automatically detect the system drive (`system_drive()`), list fixed data drives (`data_drives()`), and select `scratch_roots` on the non-system drive with the most free space (`ABAQUS_SCRATCH`). Use `--prefer-drive D:` (multiple values can be comma-separated) to specify local preferred drive letters; in that case selection follows priority order rather than free-space size, and `preferred_scratch_drives` is written into the configuration for auditing. If no data drive is available, a clear warning is given in `note` |
| `validate-config` | Adds a `scratch_disk_policy` check; when scratch is on the system drive, `scratch_roots` is judged **FAIL** (unless explicitly overridden), and the system drive and candidate data drives are listed |
| `plan` | Hard interception before submission: if work or scratch is on the system drive, reject directly with repair guidance |
| Preferred-drive audit | `scratch_disk_policy` records `preferred_scratch_drives` and whether actual scratch is on that drive; if a preferred drive is configured but not used, it is marked **WARN**, prompting correction rather than silently ignoring |
| Explicit override | Allowed only when `allow_scratch_on_system_drive=true` in the configuration (requires explicit user approval); in that case the check is marked WARN/INFO to leave a trace |

### Drive-Letter Preference Example (Illustrative Only)

Some users set the **D drive** as the preferred drive for work tasks; in that case explicitly write `preferred_scratch_drives: ["D:"]` in the configuration, and scratch will be placed on that drive. Drive-letter preferences are **written only in the personal configuration** and are not used as a general default—other machines can specify them explicitly with `init-config --prefer-drive`, or rely on the default automatic selection of the physical drive with the most free space. The configuration examples shipped with this package contain no drive-letter preference.

Note: `allow_scratch_on_system_drive` is an escape hatch reserved for test fixtures and special environments, not a routine option. Enabling it means accepting the risks of a filled system drive and IO contention; do not use it for real production jobs.

Related diagnostic functions: `host_compat.system_drive()`, `on_system_drive(path)`, `data_drives()`, `suggest_scratch_root(base)`; their results can all be observed from the `compat` information of the `abaqus_host_compat` MCP tool.

## 2b. Pre-Submission Configuration Check: validate-config

```powershell
& $py $bridge validate-config
& $py $bridge validate-config --query-release   # additionally query the Abaqus version
```

MCP equivalent tool: `abaqus_validate_config` (optional `query_release` boolean parameter).

This is a **read-only** check: it creates no files and submits no jobs. By default no external process is started; only `--query-release` runs `abaqus information=release`, and the working directory is an automatically cleaned temporary directory, leaving no logs in the project.

The ten checks and their judgments:

| Check | FAIL Condition | WARN Condition |
|---|---|---|
| `config_keys` | Missing required keys | — |
| `launcher` | Not found | Extension is not bat/cmd/exe |
| `allowed_roots` | Directory does not exist | — |
| `registry` | Parent directory does not exist or is not writable | — |
| `scratch_roots` | Does not exist or is not writable | Outside `allowed_roots` |
| `capacity` | `auto` parse failure / illegal value | Exceeds logical core count or physical memory |
| `free_disk` | Free space below the minimum | No scratch to measure |
| `compilers` | — | Configured but none exist |
| `powershell` | — | Not found (hardware/process snapshot degraded) |
| `host_injection` | Injected DLL such as `tsbx.dll` detected | — |
| `abaqus_release` (optional) | Launcher missing, cannot query | Non-zero return code / version cannot be parsed / not the verified 2023 |

Top-level `verdict`: any FAIL → `BLOCKED`; only WARN → `USABLE_WITH_WARNINGS`; all PASS → `READY`. `usable` is the boolean `verdict != BLOCKED`; each check carries `detail` and `action` (repair suggestion).

Note that `os.access` is a **static writability judgment**, not an actual write test; passing the check does not replace one authorized real datacheck. When an injection FAIL is consistent with `solve_readiness=BLOCKED_BY_AGENT_INJECTION`, the real solve must be moved to a host without injection.

## 3. auto Capacity Values

The three capacity keys in the configuration file can be integers, the string `"auto"`, or omitted. The backend parses them in `Backend.limits()`, and the `capacity.limits` returned by `plan` shows the **actually effective values**:

```json
{
  "max_total_cpus": "auto",
  "max_concurrent": "auto",
  "max_total_memory_mb": "auto"
}
```

The derivation rules are in `host_compat.default_limits()`: `cpus = max(1, logical cores - 1)`, `concurrent = max(1, min(8, logical cores//4))`, `memory = total memory×0.85`. These are **safe upper-bound suggestions**, not performance promises; real jobs still require the user to authorize specific cpus/memory according to model size.

Another optional key is `preferred_scratch_drives` (e.g. `["D:"]`), expressing the **local** drive-letter preference. It does not change capacity, only where `init-config` selects scratch; `validate-config`'s `scratch_disk_policy` audits whether scratch really is on that drive. Generator commands:

```powershell
& $py $bridge init-config --output '<config>' --prefer-drive 'D:'        # single drive
& $py $bridge init-config --output '<config>' --prefer-drive 'D:,E:'     # fallback in order
```

## 4. Path Compatibility

Comparison between `allowed_roots` and job paths uses `os.path.normcase`, so on Windows differences in drive-letter case, slash direction, and trailing separators do not cause legitimate paths to be misjudged as out-of-bounds. `path_is_within` also prevents prefix traps such as `/data/project` mistakenly including `/data/project_other`.

Relative paths are still **rejected**; command arguments containing `& | < > ^ % !` quotes or newlines are still rejected by `safe_argument`; this is an anti-injection design and is not relaxed when changing machines.

## 5. Degradation Behavior

| Missing Item | Behavior |
|---|---|
| PowerShell completely unavailable | `doctor.hardware` falls back to the OS API and sets `hardware_degraded=true`; when the process snapshot is unavailable, `capacity()` rejects submission rather than guessing the existing solver |
| Abaqus launcher not found | `init-config` generates an empty launcher; `doctor.solve_readiness` gives `NO_LAUNCHER`; submission is rejected |
| Compiler not found | `compiler_candidates` is empty; subroutine jobs require the user to confirm the toolchain themselves; it will not pretend compilation is possible |
| Version cannot be parsed | `release_query.parsed.version=null`; no inference of keyword/ABI compatibility |
| Non-Windows | hardware/process/injection detection returns structured unavailability; `solve_readiness` is `UNSUPPORTED_HOST`; no attempt to drive Abaqus with a Unix shell |

## 6. Boundaries

- Detection does not modify environment variables, install software, replace configurations, or start `pre.exe`/`standard.exe`/`explicit.exe`.
- `init-config` writes a file only when the target path does not exist; if it already exists, an error is reported and it is not overwritten.
- Detecting a candidate does not mean the license is available, version keywords are compatible, or subroutine ABI matches; these still require separate verification on the target machine.
- This document does not change the physical/material/acceptance contract, nor does it relax any authorization or hash-freezing rules.

## 7. Reference Experience (External Sources, Technical Consensus Only)

The following sources support the scratch disk policy in §2a. This package adopts only the technical consensus related to IO/disk layout, not their product promotion content:

- Analysis of Abaqus environment files and scratch configuration (IO isolation and MPI timeouts, scratch IOPS as a parallel bottleneck): https://tsight.io/articles/11909097?lang=zh
- Temporary file path location and C drive space cleanup (switch to a non-system drive, estimate space before computation, distinguish manual/automatic cleanup): https://www.gofarlic.com/techDocumentDetail?documentId=53715
- "no enough disk" diagnosis (relative paths are unreliable, avoid network storage for scratch, job-level override + environment-level hardening): https://ask.csdn.net/questions/9249221
- Three steps to change Abaqus temporary paths and system drive risks (create a data-drive directory, `scratch='D:/...'`, unified management): https://www.saifanbox.com/news/356.html

These are community/vendor experience, not an official Abaqus SLA; this package turns the mechanically verifiable parts (system drive determination, fixed-drive filtering, absolute paths, independent directory per job) into interception rules.
