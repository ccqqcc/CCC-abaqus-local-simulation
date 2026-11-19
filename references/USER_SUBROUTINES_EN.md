> English version. [中文版](USER_SUBROUTINES.md)



# User Subroutines: Invocation, Compilation, Interface, and Acceptance

## 1. First distinguish procedure from entry point

| Solver / Purpose | Common Entry Point | Key Difference |
|---|---|---|
| Standard solid / material | UMAT | Returns stress/state/consistent tangent; calls involve iterative trials and rollback |
| Explicit material | VUMAT | Block interface; precision/array/layout must match; not simply renaming UMAT |
| Standard user interface | UINTER | Local normal/tangent signs, contact pairing, properties, and Jacobian/state are important |
| Explicit user interface | VUINTER and version-corresponding interfaces | Block/precision/argument ABI differs from Standard; check the version manual first |
| Built-in CDP / cohesive contact | No `user` argument | No Fortran user code needed; do not insert an empty user just to make a call |

Historically V11 used COH3D8 UMAT; Stage4 and 6C0 used UINTER; early Explicit exploration used VUINTER. This package does not include those research laws/source code, and does not imply that they have been validated against the current material.

## 2. Actual submission method

```text
abaqus.bat job=UINTER_X input=UINTER_X.inp user=uinter.f90 cpus=2 memory=3000mb scratch=<separate-scratch> interactive ask_delete=OFF
```

At startup Abaqus invokes the compiler/linker to build the user library, then calls the interface in the solver. Python orchestration does not replace Fortran material integration. A single successful link does not prove correctness for every loading/STATEV.

Add the absolute path of `user_subroutine` to the package request, and list its Fortran INCLUDE files/header files/dependent libraries in `additional_files`. Include the relevant files and the job-local env in the hash. Installation-level/site-level environments also have inheritance effects that require on-site verification and documentation; auditing a single env is not closure.

## 3. Compiler/ABI facts verified in the example environment

- Abaqus2023 installation root: `<ABAQUS_INSTALL>`.
- Intel ifx: `<PYTHON_HOME>/pkgs/ifx_impl_win-64-2025.3.1-intel_761/Library/bin/ifx.exe`.
- MSVC x64 link: `C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/link.exe`.
- The job-local env puts the correct Intel Fortran/compiler runtime first, then the old PATH, to prevent the old Abaqus runtime from taking precedence.
- The old `ifort.bat` was an adapter forwarding to ifx; one cannot claim from the file name that classic ifort is installed.

What a typical job-local configuration does: prefix PATH with VS x64/ifx/Intel runtime; add to LIB the ifx, runtime, compiler shared, VS x64, and Windows SDK um/ucrt paths; `compile_fortran` uses `ifx /c /fpp /extend-source /DABQ_WIN86_64 /DABQ_FORTRAN /iface:cref /recursive /Qauto ... /include:%I ... %P`. These flags are a historical adaptation for this host, not a cross-machine general template, nor do they guarantee that Intel2025 is in Abaqus2023's official support matrix.

When migrating, first check the supported compilers, Windows SDK, MSVC, Intel precision, and runtime libraries for that Abaqus version. Do not modify the system-global PATH/ABAQUS environment to fix a single case; prefer adding and auditing job-local settings. The job-local env is itself executable Python and must be treated as trusted code; never run an env of unknown origin.

## 4. Validation layers and historical failures

1. Version/compiler discoverable: a path existing does not mean it can run.
2. Official verify/smoke: compile, link, load. Historically the classic detection was SKIPPED but the official uinternx actually passed; these two facts are not contradictory.
3. Single material point/patch: normal tension, shear, compression-shear, open/close recontact, rotation, different directions; scope is based on the current interface, with no unbounded large suite.
4. Properties echo: count/ordering/actual values. Abaqus property data lines usually have a column limit; in this project 12 items were once erroneously placed on a single line, and became correct only after changing to 8+4.
5. Local finiteness/boundary protection: NaN can precede unpaired; `ierr=0` cannot override a non-finite state.
6. Numerical Jacobian/tangent: a correct elastic tangent does not mean a correct nonlinear tangent; finite differences must also consider step size/branch, not merely posting a very small error.
7. Trial and rollback: globally non-accepted trial calls must not permanently accumulate damage/history or be written as accepted history.
8. ABI/precision: an Explicit single/double mismatch once corrupted properties such as Kn. The wrapper and core, the compilation type, and the runtime `double=` must be consistent.
9. Actual structural benchmark: total reaction force, local signs/normal, BC/loading path, energy, and bulk/interface crack initiation. Passing the patch gate does not mean passing the paper benchmark or the C50 solid.

This project corrected the local normal displacement/stress signs: `g1=-RDISP1` and the returned normal stress sign should be converted consistently according to the adopted paper and Abaqus conventions; this specific formula must not be treated as a general rule for all UINTERs. Local D/T directions and global X/Y/Z must be drawn and verified in practice, not inferred from the job name.

## 5. How to diagnose compilation or runtime failures

First, layer the diagnosis:

- launcher not found: not a Fortran law problem.
- ifort/ifx not found, linker/SDK missing: environment.
- unresolved externals/ABI: interface/compilation precision/naming.
- runtime DLL load failure: PATH and runtime libraries.
- properties already wrong on first return: interface/data line/precision; do not sweep physical parameters.
- initial tangent fine but local return non-finite: law algorithm/protection.
- patch clean but macro step-cutting: boundary/contact tracking/localization/instability/material coupling needs isolation.

Do not assert that the entire current environment is broken based on a single status from a generic verify, and do not immediately reinstall the system or change material strength because one production job failed. Prioritize saving the actual compilation stdout, env, source hash, and a minimal reproduction; do not fill unknown constitutive values into the user file.
