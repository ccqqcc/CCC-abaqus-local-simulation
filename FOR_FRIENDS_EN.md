> English version. [中文版](FOR_FRIENDS.md)



# abaqus-local-simulation: A Friend's Quick-Start Guide

This is a bridge package that wraps local Abaqus invocation into a "Skill + command line + local MCP". It does **not** include the Abaqus solver, license, models, or ODBs; these must be installed independently on your own machine.

## 0. First check whether it will work for you

- Requires **Windows + Abaqus installed** (the example environment is Abaqus 2023; other versions require you to verify keywords/ABI yourself).
- Requires **Python 3.9+** (any CPython; read-only ODB uses Abaqus's bundled Python, orchestration uses ordinary Python).
- Only "able to run command line" is required; configure MCP only if you want to connect an AI client.
- Check whether you are inside an **agent with injection/sandbox**: run `doctor`; if `solve_readiness.verdict = BLOCKED_BY_AGENT_INJECTION`, this host can only do audit/post-processing, and real solves must be run from an ordinary local terminal.

## 1. Get the code

```powershell
git clone https://github.com/<OWNER>/abaqus-local-simulation.git
cd abaqus-local-simulation
```

If you don't know git, just click the green **Code → Download ZIP** on the GitHub page and extract it.

## 2. Three steps to complete local configuration (do not use the repository's local_config.json directly)

That file is a path example and must be replaced with your own:

```powershell
$py = '<PYTHON_EXE>'          # replace with your Python
$bridge = '.\scripts\abaqus_agent.py'

# 1) Generate a config skeleton for your machine (auto-find abaqus.bat / compiler / compute capacity / auto-select a non-system drive for scratch)
& $py $bridge init-config --output 'D:\my_project\agent_config.json'

# 2) Preflight: result must be READY or USABLE_WITH_WARNINGS
& $py $bridge --config 'D:\my_project\agent_config.json' validate-config --query-release

# 3) Manually create the directory pointed to by scratch_roots in the config (must exist beforehand)
```

When the preflight shows `BLOCKED`, follow each item's `action` to fix the config/change the host—**do not change materials or mesh to accommodate the environment**.

**Important: do not put the working directory or scratch on the system drive (usually the C drive).** A single Abaqus nonlinear analysis can generate tens of GB of temporary files; putting them on the C drive can fill the system partition, slow the solve, and even trigger parallel timeouts. `init-config` automatically picks the non-system physical drive with the most free space; if it picks the wrong drive, manually change `scratch_roots` to a data drive such as D/E. Both the preflight and the submission plan block system-drive paths—do not enable `allow_scratch_on_system_drive=true` for convenience.

## 3. Everyday usage

```powershell
# View environment and host verdict
& $py $bridge --config '<config>' doctor

# Audit an INP and generate a sealed plan (performs no analysis)
& $py $bridge --config '<config>' plan --request '<request.json>'

# Submit: requires your explicit authorization + the token returned by plan
& $py $bridge --config '<config>' submit --request '<request.json>' --plan-token '<token>' --authorize --authorization-note 'I approve this job/resources/stop policy'

# View status (includes triage root-cause classification)
& $py $bridge --config '<config>' status --job-id '<32-char-id>'

# Attribute a failure
& $py $bridge --config '<config>' triage --workdir '<job-dir>' --job '<job-name>'

# Read an ODB read-only
& $py $bridge --config '<config>' probe --request '<odb_request.json>'
```

## 4. Connecting an AI client (optional)

For a client that supports local stdio MCP, import `assets/mcp_client.local.example.json`, and replace the python path and `mcp_server.py` path inside it with absolute paths on your machine. There are 10 read-only/controlled tools in total; no arbitrary shell and no network listener.

Common order: `abaqus_host_compat` → `abaqus_validate_config` → `abaqus_doctor` → `abaqus_plan_job` → (human approval) → `abaqus_submit_job` → `abaqus_job_status` / `abaqus_triage_job`.

If the client supports Skills, just put the entire directory into its skills directory and have it read `SKILL.md`.

## 5. Boundaries and rules (important)

- `submit` requires your explicit authorization and note; the token is bound to exact input/resource hashes; changing any input requires redoing the plan.
- The package does not automatically change your physical model, does not automatically restart, and does not misjudge a candidate peak as a valid peak.
- A sandbox-injected host **cannot actually run a solve**: it shows up as `.dat` with zero errors but zero ODB frames, or `PART_MAP_HANDOFF`. In that case, switch to an injection-free local terminal.
- Passing the preflight ≠ successful license checkout; one authorized real datacheck verification is still required.
- For result interpretation, see `references/ABAQUS_CALLING_HANDBOOK_EN.md`, `TROUBLESHOOTING_EN.md`, `AGENT_HOST_SANDBOX_EN.md`, `HOST_COMPATIBILITY_EN.md`.

For questions, first look at `VALIDATION_REPORT.md` and `tests/test_bridge.py`, which state which capabilities were actually verified and which are only simulated tests.
