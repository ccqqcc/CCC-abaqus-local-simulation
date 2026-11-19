> English version. [中文版](TROUBLESHOOTING.md)



# Fault Diagnosis and Limited Recovery

| Symptom | Required Evidence | Forbidden Shortcuts / Reusable Rules |
|---|---|---|
| No solver process but cache RUNNING | PID creation time, system boot, STA/ODB modification times, raw end marker | No infinite heartbeat, no automatic resubmission; first classify as STALE/ORPHANED |
| launcher returns 0 but no results | stdout/.log/.dat/probe JSON actual schema | Not a success; post-processing errors require non-zero exit and preservation of the exception |
| `.lck` exists | Whether the original job/PID/ODB is still being written, file owner/phase authorization | Do not delete the lock to unblock, and never clear scratch globally |
| input processor failure | DAT ERROR line by line, keywords/data columns/IDs/sets/OP options/materials | Do not "fix syntax" by changing physical strength; first do minimal input verification |
| RF very small / very large | Load-bearing area, units, RP/node sets, sumRF, BC location | A single node is not the total force; keep N/MPa/ton-density separate |
| X=Y unaffected by Ks/strength changes | slip/traction/QUADSCRT/SDEG, bulk, activation path | If a parameter is not active, stop the sweep first; do not drive strength down to noise level |
| Standard keeps cutting back | MSG minimum vs maximum increments, STA accepted trend, localstate/eigenvalues | Do not conflate the two categories of terminal cause; endpoint max is not a peak; limited recovery/solver diversion |
| Zero points after candidate | accepted RF/U raw history | `NO_CONFIRMED_PEAK`; do not classify directly by feasible window/target |
| trace/ierr0 but accepted is abnormal | NaN/inf, unpaired, properties, equilibrium/energy | ierr0 does not mean the constitutive return is reliable; trace trials cannot count as accepted |
| Python2 TypeError when opening ODB | whether path is unicode, filesystem encoding, version | Fix the read interface; do not judge the model as INVALID physics; exceptions must be non-zero |
| String Expected as dictionary Key | whether step/history/energy region in JSON is unicode | In some versions the repository key also needs conversion to a native string, not just the ODB path |
| CPRESS/SDEG not found | all field keys, contact suffixes, cohesive elements vs contact vs UINTER | Do not fabricate variables; do not claim pressure does not exist based merely on a missing bare key |
| fine mesh changes the ratio | whether facet geometry/platform/topology changed simultaneously | Separate geometry reconstruction from pure h-refinement |
| tied model too strong / PEEQ near 0 | MONO/TIE/internal DOF/Poisson, theoretical constraint upper bound | Even close to target, end-face locking may occur; do not adjust material to compensate |
| Explicit has a peak but kinetic energy/dissipation high | KE/IE at peak time vs full load-bearing segment, AE/VD/CD, loading speed/mass scaling | Peak decline is not a sufficient condition for quasi-static; missing energy is still missing |
| friction share exceeds capacity | pressure sign, total shear, damage, slip definition, μp and complete transfer law | Without independent components, `MECHANISM_ATTRIBUTION_LIMITED` |
| source file unchanged but solver differs | CDP viscosity semantics, contact algorithm, precision, ramp/time | Consistent hash does not mean consistent effective numerical implementation |
| input files with the same name but different results | material/geometry/BC/ramp/solver/precision/output/source hash | Do not reuse by name; do not mix Standard and Explicit XYZ |
| worker or MCP crash | managed record, worker/launcher identity, solver logs | Do not assume client exit cancels the job; do not automatically retry |
| `.dat` zero errors but solve fails / ODB has zero frames | single `root_cause` given by `triage --workdir <dir> --job <name>`; before submission check `doctor.solve_readiness.verdict`; raw evidence is `*.exception` Details/Phase | Host injection/process isolation takes priority over model suspicion; see AGENT_HOST_SANDBOX.md; do not modify materials/mesh to "fix" a host problem |
| `could not be located: <absolute path>.inp` but the file exists in the agent's view | host injection, command `cmd /d /s /c` wrapping, whether cwd is the job directory | First try the relative path `input=<job>.inp` + cwd; if a known-to-succeed input reports the same error with the same method, it is a host problem, not an INP error |
| `part map file does not exist/corrupt` (`PART_MAP_HANDOFF`) | exception `Phase=std`, whether pre/standard are view-isolated, whether scratch was created in advance | `.prt` handoff break ≠ model error; move the real solve to a host without injection; do not delete scratch / modify the model |
| `submission.lock` leftover | only check the PID/creation time inside the registry lock and whether writing is in progress | Do not delete automatically; after manually confirming no submission process exists, you may restore your own registry; do not touch the solver lock |
| After changing machines, doctor information is incomplete / hardware reports error | `doctor.hardware_degraded`, `doctor.compat.powershell`, `launcher_candidates`, `release_query.parsed.version` | Hardware falls back to the OS API without pretending to be CIM; first verify with `init-config --output <new config>`; detection failure ≠ model problem; see HOST_COMPATIBILITY.md |
| Before submission, unsure whether the configuration is usable | `verdict` and each `action` of `validate-config` / `abaqus_validate_config` | If BLOCKED, fix configuration/host first, then `plan`; the check is read-only, writes no files, and does not replace one authorized real datacheck |
| `plan` reports work/scratch on system drive | `system_drive`/`data_drives` of `scratch_disk_policy`, `on_system_drive` of `scratch_roots` | Move scratch/work to a non-system physical drive; do not enable `allow_scratch_on_system_drive` to bypass; C-drive temporary files will fill the system partition and trigger IO contention/MPI timeouts |
| Parallel runs slow / disk seeking noise / crash mid-computation | scratch free space and throughput, whether on system or network drive, whether each job has an independent empty directory | Check scratch IOPS and space first; do not change cpus/mp_mode first; use only non-system fixed drives, absolute paths, one per job; after confirming completion, clear only your own expired scratch |
| Windows path case/slashes cause out-of-bounds false positives | `normcase` results of `allowed_roots` and the actual path | Comparison already ignores case and slash direction; relative paths and cmd metacharacters are still rejected; do not relax safety checks |

## Limited Numerical Recovery Contract

Before user approval: only diagnose and propose numerical options; do not implement. After approval: independent attempt name, same physical-model hash, change list, budget, maximum number of attempts, termination conditions. Depending on the task, consider smaller initial/min increment, more increments, line search, very small stabilization, or another solver; these do not guarantee equivalence; check energy/rate/BC.

When a verifiable restart state exists, continue from the saved stable increment first; without a state, the ODB cannot be treated as a state. Whether restarting or recovering from scratch, do not modify the original job and do not erase the fact of natural termination.

Reaching the retry limit / no peak: `NUMERICALLY_INCONCLUSIVE`, do not write `NOT_EFFECTIVE`. Rejecting the physical route requires valid results or evidence of the correct necessary conditions. When the user explicitly forbids a third attempt, there is no "one more try" exception.

## Minimal Order for Checking Logs

1. Whether submission succeeded / license wait / compilation failure: stdout and LOG.
2. Whether there is an input error: DAT.
3. accepted progress and final time: STA.
4. Convergence/damage/distortion/terminal cause: MSG (for Explicit also check STA/LOG).
5. Real peak and energy/field: ODB read-only.
6. cache is only an index; close out with raw evidence; do not overwrite raw in return.

This order is a localization logic, not a unification of all phase permissions into "can be stopped." The natural-run contract remains in effect; diagnostic tools must not be used to unilaterally terminate historical jobs.
