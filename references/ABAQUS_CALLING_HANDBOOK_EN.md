> English version. [中文版](ABAQUS_CALLING_HANDBOOK.md)



# Complete Abaqus Calling Handbook: From Job Contract to Acceptable ODB Evidence

This handbook is written based on the actual runner, Fortran environment, and common input/post-processing errors. It summarizes "how to call" and does not treat historically failed models as calibration templates that can be freely reused. Public official documentation links use the currently accessible 2025 version; support in the version you use must still be verified against that version's documentation, datacheck, and run logs.

## 1. Calling Architecture and the Two Pythons

Actual chain:

```text
User task / real material / geometry / BC / acceptance criteria
          ↓ external Python3, or CAE noGUI construction
INP + recursive include + user source + job-local abaqus_v6.env
          ↓ datacheck / input, unit, and topology audit
external Python3 queue → abaqus.bat → input processor → Standard/Explicit
          ↓ solver_stdout + .log/.msg/.sta/.dat + .odb
abaqus.bat python odb_probe.py → odbAccess(readOnly=True)
          ↓ paired history, field, energy, peak qualification
per-job evidence → reproducible summary → physical/numerical/mechanism acceptance → report
```

External Python3 handles file preparation, hashing, concurrency, time budgeting, status, and reporting; the `odbAccess` of Abaqus2023 cannot be imported directly with ordinary anaconda Python. Abaqus2023 ships Python2.7 for reading ODBs; scripts must not use f-strings/pathlib/type annotations. Newer versions may use Python3; check the version first and do not mechanically apply old syntax.

`abaqus python` is generally suitable for odbAccess, text/math, and post-processing. When using `mdb` for modeling or CAE/Viewer for plotting, the corresponding `cae noGUI`/`viewer noGUI` entry points and available licenses are required; a successful ODB read does not imply that a CAE or analysis license is available.

## 2. Define the Contract Before Calling

At minimum, clarify:

1. Project location, source inputs, and the source of geometry/material/interface/BC/loading/units.
2. Whether this run is a read-only diagnosis, modeling, datacheck, submission, restart, or stop; prohibited scope-expansion actions.
3. Allowed new job names/count/directions/parameter points, reuse conditions, and maximum number of recoveries.
4. Which physical quantities are locked and which purely numerical controls may vary; the load path or damage dissipation must not be changed under the guise of "numerical controls."
5. CPUs/job, maximum concurrency, total memory, scratch, disk protection, estimated wall time; whether there is stop authorization on timeout.
6. What counts as a valid result: formal peak, screening peak, provisional, no peak, anomaly; which field/energy/spatial mechanisms are required.
7. Whether each stage runs naturally, whether post-peak stopping is allowed, and when the decision must return to the user.

When real material/interface parameters are unavailable, a clearly labeled mechanism screen or synthetic plumbing test is permissible, but it cannot be claimed as an experimental reproduction of the current specimen. A target peak value cannot replace a complete CDP curve or geometric ground truth.

## 3. Environment, Version, Licenses, and Resources

A typical installation contains:

```text
<ABAQUS_LAUNCHER>
<ABAQUS_LAUNCHER>
<ABAQUS_INSTALL>\win_b64
<PYTHON_EXE>
```

`abaqus.bat` forwards to `abq2023.bat`. Use absolute paths when calling; do not mistake another version in PATH for the version running in this project.

Example for reading the version (run in a fresh audit directory):

```powershell
& '<ABAQUS_LAUNCHER>' information=release
```

This may generate information/log files, so do not set the working directory to a frozen historical job. It does not run an FE analysis, nor does it prove that a solver license is currently available for checkout.

Licenses: first determine whether the site uses FLEXnet or DSLS, and check with the legitimate status-query command in its administrator/installation manual. The common FLEXnet entry is `abaqus licensing lmstat -a`; this does not apply to all DSLS sites. Do not bypass licensing, do not automatically modify license server addresses, and do not treat a license wait as a material convergence failure. Server/user information in the output must not be leaked in external packages. The doctor of this package explicitly retains `license_availability=UNVERIFIED`.

CPU/RAM capacity budgets are always based on the physical cores and available memory actually measured on the current machine, not doubled by logical threads; reserved capacity in package configuration for registered jobs does not mean the OS actually has constant available memory. Concurrency is also constrained by license, disk space, NUMA, and log/ODB I/O. On site, first check for existing solvers; an old queue must not be assumed nonexistent. On site, first check for existing solvers; an old queue must not be assumed nonexistent.

## 4. Model Construction and Dependency Audit

### 4.1 Two Practical Approaches

1. Build new input text from audited INP / real facets, making it easy to preserve material includes and exact nodes/facets.
2. A CAE Python script creates mdb/model/job and writes the input, and runs it if necessary; the historical V11 uses:

```text
abaqus cae noGUI=main.py -- --run --analyze --calibrate
```

These are parameters of the historical script only; `--calibrate` must not be copied onto other main.py scripts. Modeling scripts for new tasks should run in an authorized new directory, with their write and submission behavior made explicit. Using a CAE script does not mean a visible window must be opened.

### 4.2 Checks Required After Construction

- Coordinate/loading axes, units, specimen dimensions, load-bearing area/test formula; in N-mm-MPa-tonne the density cannot use the raw kg/m³ value.
- Unique node/element labels, existing sets, the number of data columns per keyword line, and a valid material-definition order.
- Whether the interface double nodes are independent; shared nodes would bypass the intended cohesive jump.
- Only the interface count and orientations approved by the user, with no leftover IFJ/vertical interfaces.
- When refining a faceted mesh, preserve the source facets, platform, topology, and normals; do not regenerate an analytic sine and then call it pure h-refinement.
- Check platen contact and interlayer contact separately; do not mix μ_platen with μ_interlayer.
- Locating constraints must not allow rigid-body motion nor over-constrain; MONO/TIE/elastic baselines are used to identify end-face constraint contamination.
- CDP plastic strain conversion, material source hash/line-by-line table; the name C50 does not mean a 50MPa peak in the input table.
- step/procedure/loading ramp/output/numerical controls; mass scaling must not be quietly introduced in Explicit either.

The package's `plan` recursively audits `*INCLUDE, INPUT=` and hashes INP/include/user/job-local env and `additional_files`. `FILE=` dependencies, Fortran INCLUDE files, distribution tables, shared dynamic libraries, and installation-level global env are not guaranteed to be discovered automatically; the agent must list them explicitly or create a separate trusted audit. Circular includes, missing files, out-of-bounds paths, and existing job outputs will block the plan.

## 5. Input Checking and Formal Submission

Actual datacheck pattern:

```text
abaqus.bat job=CHECK_MODEL_X input=MODEL_X.inp cpus=2 memory=2048mb scratch=<separate check scratch> datacheck interactive ask_delete=OFF
```

Keep separate CHECK names/directories; do not generate an ODB for the formal job first and then overwrite it with the same name. Check the DAT for ERRORs, keyword support, and material/contact/element statistics; return code 0 is only launcher/program-level information. Passing syntax does not mean the physical model is correct.

Ordinary Standard:

```powershell
& '<ABAQUS_LAUNCHER>' job=MY_X input=MY_X.inp cpus=2 memory=2048mb scratch=<SCRATCH_ROOT>\MY_X interactive ask_delete=OFF
```

Standard/Explicit is determined by the procedure in the INP, not by the job name. When `input=` may be omitted it generally defaults to an INP of the same name, but this package still explicitly passes the audited absolute path.

Explicit:

```text
abaqus.bat job=MY_EXPLICIT_X input=MY_EXPLICIT_X.inp cpus=8 memory=2048mb scratch=<separate scratch> interactive ask_delete=OFF double=both parallel=domain domains=8
```

`double=both` and the domain settings are the racing configuration used by this project; not all tasks require 8 CPUs. For a 2-CPU screen use domains=2; domains must not be left at 8 without verifying support. The Explicit input must contain a genuine `*DYNAMIC, EXPLICIT` with corresponding density/time/output; a Standard deck cannot be turned into Explicit merely by changing launcher parameters.

`interactive` keeps the launcher's lifecycle synchronized with the analysis, making it easier for the worker to capture the return code; it does not require GUI interaction. `ask_delete=OFF` disables the delete prompt; it does not provide "no-overwrite" protection. The package additionally rejects existing `.odb/.lck/.res/...`; do not disable this check.

Windows .bat goes through cmd.exe; spaces, quotes, and metacharacters can easily corrupt commands. This package's parameters do not accept arbitrary extra command strings; arguments are validated one by one and an explicit BAT wrapper is used with the window hidden. Do not concatenate untrusted shell text or delete results with wildcards.

## 6. Per-Job Directories, Background Workers, and Status

Recommended layout:

```text
AUTHORIZED_PROJECT/jobs/MY_X/
  MY_X.inp
  common_material.inp
  common_interface.inp
  user.f90                 if needed
  abaqus_v6.env            audited local config, if needed
  MY_X.log/.dat/.msg/.sta/.odb/...
<SCRATCH_ROOT>/MY_X/
registry/job-<managed-id>.json
registry/worker-<managed-id>.log
registry/probe-<unique-id>-result.json
```

`submit` generates solver files only in the approved job directory; the registry does not point to a historical queue. A separate worker monitors its own launcher; closing the MCP client does not automatically stop it. The worker records the PID and Windows creation time so that after PID reuse it will not mistake another process for itself.

Status meanings:

- `RESERVED/STARTING/RUNNING`: launcher and live-process-level status, not the presence of a valid peak.
- `STOP_REQUESTED`: termination has been requested; it cannot be said to have stopped.
- `COMPLETED`: the log has a completion marker; ODB acceptance is still required.
- `ABORTED`: the analysis terminated; an ODB previously showing a reliable post-peak drop may still constitute peak evidence.
- `ENDED_UNCONFIRMED`: the launcher exited but no clear completion/termination fact was found; log reconciliation is needed.
- `STALE_RECORD_NEEDS_RECONCILIATION`: the record is not reconciled and no matching live process exists; it cannot continue to be called RUNNING.
- `ORPHANED_LAUNCHER/SUPERVISOR_FAILED_LAUNCHER_MAY_BE_RUNNING`: monitoring contact lost, but the solver may still exist; do not automatically resubmit.

A worker timeout requests Abaqus termination only when `terminate_at_walltime=true`; otherwise it flags attention and continues read-only observation. `stop_after_confirmed_peak=true` requires a probe with an explicit region; stop only after strict confirmation and qualified quality. Both switches are false by default, so tasks that were "never interrupt natural runs" will not be rewritten by this package.

This package has no Windows auto-start service. After a host reboot, first check processes, STA/ODB times, and job files to distinguish a natural finish from an unexpected interruption, then decide on recovery authorization. Do not treat "the MCP can restart" as "the solver can restart automatically."

## 7. Throughput, Queue, and Output

First run short benchmarks close to the real scale and compare jobs/hour rather than only single-job time; one 8-core job being faster does not mean 8×4 gives higher throughput. The optimal layout differs by machine; macro-damage models require re-comparison with short cases close to the real scale.

The queue only allows a pre-authorized list; new parameters are not automatically expanded from results. Submit per job via MCP, or have an external queue fill slots by status/capacity. All live races/jobs count toward total CPU and memory; do not start 16×2 immediately while a 4×8 race has not finished. Probe/update each job as soon as it completes; do not wait for the whole batch.

This general-purpose package handles capacity protection and the per-job worker; it does not include this project's A–μ ranking/automatic Y-filling; such physical decisions should be written in a separate stage-specific controller. Do not copy an old controller and carry over its aliases, schema, stage permissions, or cache.

Use the genuinely fastest disk for scratch, separate per job, with reserved protection space. Drive H is a 970PRO NVMe on this machine, which does not mean drive H is equally fast on other machines. The 8GiB disk protection floor is a local screening choice and must be adjusted on migration; ODB and user traces may be the main bottleneck.

Scratch disk selection and cleanup (engineering consensus, not specific to this machine):

- **Never place it on the system drive**: temporary files for large nonlinear analyses can reach tens to hundreds of GB; filling the C drive causes freezes/crashes/recomputation; concurrent reads/writes on the system drive compete with the OS for IO, and parallel jobs may trigger MPI communication timeouts. This package forcibly blocks system-drive work/scratch in `validate-config`/`plan`.
- **Prefer a high-speed SSD/NVMe on a non-system physical disk (DRIVE_FIXED)**, using absolute paths; do not use network/mapped/removable drives, since temporary files need low-latency random IO. The empirical three-disk division of labor is: the C drive holds only the system and software, the data disk holds projects and scratch, and the archive disk holds completed results.
- **One separate empty subdirectory per job**, explicitly specified at submission with `scratch=<job-specific directory>`; do not let multiple jobs share one scratch; `ask_delete=OFF` prevents temporary files from being automatically deleted after a computation interruption, losing diagnostic information.
- **Clean up regularly but only your own**: after confirming a job ended normally and has no restart need, clean up expired scratch registered by this package; do not globally clear the scratch root or delete directories of unknown jobs. The directory pointed to by the `scratch` parameter holds only temporary files; do not keep final ODBs in scratch long-term.
- When parallel efficiency is low, first check scratch IOPS/throughput and remaining disk space before considering changes to `cpus`/`mp_mode`; frequent disk seeking or system stutter usually means the IO path was chosen wrongly.

High-frequency history RF/U; at minimum ALLKE/ALLIE for Explicit, and ALLAE/ALLVD/ALLSD/ALLCD/ALLDMD/ETOTAL when necessary. Low-frequency fields select damage, stress, plasticity, and interface contact; do not output all fields every increment. When low-frequency fields do not coincide with the history peak, report the time offset; necessary exact peak frames should be planned before the run, not fabricated in post-processing.

## 8. Restart and Recovery

Standard generally needs `.res/.mdl/.stt/.prt/.odb`, etc.; Explicit may additionally have `.abq/.pac/.sel`, with differences by analysis/version. First check that a restart write request was made, that the files are actually non-empty, version/precision/model consistency, and which increment actually saved the restart state. The last frame of the ODB does not mean that increment is restartable. [Official restart documentation](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEANLRefMap/simaanl-c-restart.htm).

The package's `restart-audit` only produces a checklist, with `restart_state_verified=false`; the mere existence of files is not automatically written as TRUE. `oldjob` is the absolute-path stem of the original job, without .res; the new job must have a different name, contain `*RESTART, READ`, and have the state/increment confirmed by independent evidence. The original state is a read-only object; the ODB/INP are not modified.

```text
abaqus.bat job=MY_X_RESTART input=MY_X_RESTART.inp oldjob=<original job absolute-path stem> ...
```

Without state, a from-scratch run can only serve as an explicitly approved recovery copy; geometry/material/interface/BC/loading remain locked, and only permitted numerical controls may be adjusted. Smaller initial/minimum increments do not guarantee crossing a peak; Riks, implicit dynamic, stabilization, and Explicit each have different assumptions and require a user contract. The number of recoveries is capped; there is no infinite retry and no upgrading provisional to final.

This package does not automatically move *.res files to a new directory, nor copy unknown restart families; still less should an inconsistent state snapshot be created while the original job is running.

## 9. ODB Selection, Reaction Forces, and Peaks

Actual entry point:

```text
abaqus.bat python scripts/odb_probe.py request.json result.json
```

Inside Abaqus Python, use `openOdb(path=...,readOnly=True)` and close it in a finally block. Some versions of Abaqus Python may throw a TypeError for a unicode path; adapt to the filesystem encoding if necessary; Chinese paths still require actual confirmation, and it is recommended that model/script technical paths use ASCII with Chinese kept in the report.

First inventory all steps, historyRegions, and field keys; explicitly specify the loading RP. If using a top node set: the RF of each node must be at the same time and with the same displacement definition, sum with signs first and then take the magnitude; when displacements are inconsistent, do not average blindly. The bottom locating RP is not the loading RP. In the old Material3 example the single-node 5727N differs hugely from the top total 215726N, showing that automatically selecting the maximum U or a single node cannot replace a loadpath audit.

Units and strength formulas are determined by the test: 40³ axial compression N/1600=MPa; 100³ is N/10000; splitting and flexure have other formulas. The general probe outputs only force/displacement, deliberately not dividing by 1600 automatically.

Default monotonic compression peak rules, configurable:

| Status | Curve Evidence | Usage Boundary |
|---|---|---|
| PEAK_VALID | global history maximum is not the endpoint; ≥3 post points; continuously increasing displacement; drop ≥5%; no non-finite/duplicate/mismatch | quality/energy/mechanism gates still required; does not mean the job completed the whole step |
| SCREEN_PEAK_VALID | equally clean, drop ≥2% | fast screening only; must not masquerade as the strict 5% |
| PEAK_STABLE_PROVISIONAL | ≥30 post-peak points, no higher point, increasing displacement, negative slope in the later segment, drop ≥0.5% | returns morphological evidence, but `usable_peak=false` until there is an explicit provisional usage policy |
| NO_CONFIRMED_PEAK | endpoint is the maximum or drop support is missing | candidate_RF retained as diagnostic, RF_peak empty |
| INVALID_HISTORY / INVALID_QUALITY | non-finite, duplicate, mismatch, energy/sign/field anomaly | does not enter the ratio table; not called physically invalid |

History points must be accepted results, not from Newton trial/iteration traces. The package checks time duplication/mismatch, but cannot infer solely from history that all local state is correct. Cyclic, unload–reload, or non-monotonic tests require dedicated algorithms; the current general probe is not used for these peak definitions.

The postpeak minimum is a descending response, not a peak lower bound. [min postpeak, candidate peak] will no longer be used to create an uncertainty interval. Changes to peak thresholds must be versioned; historical results must not be retroactively modified.

## 10. Energy, Quasi-Static, and Cross-Solver Comparability

Explicit quasi-static commonly uses ALLKE/ALLIE<5%, preferably <2%, but this is a screening rule, not a mathematically sufficient condition for all models. At minimum check the peak time and global maximum over the load-bearing segment; startup zero energy needs sensible handling and 0/0 must not be filled with 0. The probe computes ratios at points where RF≥20% of candidate, including postpeak; energy is only time-interpolated, force is not interpolated to manufacture a peak, and there is no out-of-range extrapolation.

ALLAE checks hourglass/artificial strain; ALLVD checks dissipation but does not replace ALLCD; stabilized Standard requires ALLSD/ALLIE to be small and not contaminate the loadpath. If a required energy has no output, keep it missing/invalid; it must not be substituted by another quantity. The peak difference between two available loading rates is usually an important check; in this project E1/E2 is about 0.93%, yet tail-segment damage dissipation is still not automatically verified.

The same C50 input card includes CDPviscosity=1e-5 in Standard; the [official keyword](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKEYRefMap/simakey-r-concretedamagedplasticity.htm) states this parameter is ignored in Explicit. Standard small-sliding contact pair and Explicit general contact are also not equivalent. Therefore Explicit X cannot be directly combined with old Standard Y/Z to pass XYZ; a complete comparison requires the same solution contract.

## 11. Fields, Damage Location, and Mechanism Attribution

Real field names may carry a contact pair suffix; the absence of a bare CPRESS name does not mean the ODB has no pressure. SDEG (element cohesive), CSDMG (surface cohesive), UINTERκ/history variables, and bulk DAMAGEC/DAMAGET/PEEQ are not equivalent to one another. When STATEV cannot be output, report the missing item/trace limitation; do not fabricate an "interface SDEG".

The general probe gives the actual near-peak frame, offset, field min/max/mean/P95, and non-finite counts. Its statistics count by output point, not area/volume; different integration points/duplicate locations must not be mixed into geometric proportions. Area fractions for SDEG>0.1/0.5 and QUADSCRT≥1 must use source facet area/integration weights and de-duplicated mapping; first-damage U/Upeak requires time resolution and a damage definition, with a bracket reported if necessary.

Damage location comparisons should be at the same parent facet/geometric part/region level; fine meshes are not required to match element by element; new failure bands, anomalous localization, and shifts in bulk/interface dominance must be identified separately. A change in the maximum DAMAGEC/PEEQ value does not mean the damage region changed, nor should it be ignored.

Interlayer pressure p, total shear, cohesive shear, and friction stress/slip must be distinguished. A frictional contribution cannot be forced from total CSHEAR alone; `total-(1-D)Ks*CSLIP` may be distorted without verification of the elastic/plastic slip decomposition and Coulomb capacity. In this project even Y with D=0 still produces a residual, so it is formally limited to MECHANISM_ATTRIBUTION_LIMITED. The [official cohesive contact](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEITNRefMap/simaitn-c-cohesivebehavior.htm) distinguishes compressive normal contact, damaged cohesive, and frictional contributions.

## 12. Safety, Acceptance, and Handover

- `submit`/`terminate` require direct human authorization; passing true from the client does not constitute safety certification; the local MCP must not be exposed to the network or given to arbitrary users.
- No automatic retry/recovery/calibration; do not modify old queues, move old state, or delete unknown lck/scratch.
- Accurate job termination: `abaqus terminate job=MY_X`. If it fails, first investigate that job rather than killing all standard.exe/explicit.exe; this package provides no taskkill fallback.
- LOG/DAT/MSG/STA/ODB carry launch/input/convergence/accepted progress/scientific evidence respectively; launcher 0, DatacheckPASS, ODB existence, and a final file name are not model acceptance.
- The final deliverable lists source hashes, commands, controls/resources, job terminal status, peak qualification, energy, field gaps, original paths, and prohibited claims.
- Keep implementation gate, numerical gate, method screen, and experimental validation separate; maintain data boundaries when real material/topology is missing.

This package is an independent implementation and does not take over any historical project's scripts or job queues.
