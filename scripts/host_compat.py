"""Portable host detection for the Abaqus bridge. Stdlib only, strictly read-only.

Answers "what is on THIS machine" without launching Abaqus, writing config or
starting any solver. Every detector returns a structured value (or None) on
failure so an agent can report a gap instead of crashing on a different device.
The orchestrating Python is 3.9+; Abaqus's own Python never imports this module.
"""
from __future__ import annotations

import ctypes
import glob
import os
import re
import shutil
from pathlib import Path

LAUNCHER_NAMES = ('abaqus.bat', 'abaqus.exe', 'abaqus')
POWERSHELL_NAMES = ('powershell.exe', 'pwsh.exe', 'powershell', 'pwsh')
COMPILER_NAMES = ('ifx', 'ifort', 'link', 'clang', 'gcc')
RELEASE_RE = re.compile(r'(?i)\b(?:abaqus|version)\s+([12]\d{3})(?:\.([A-Za-z0-9]+))?')


def find_powershell():
    """Absolute PowerShell path or None. Prefers Windows PowerShell 5.1."""
    for name in POWERSHELL_NAMES:
        found = shutil.which(name)
        if found:
            try:
                return str(Path(found).resolve())
            except OSError:
                return found
    if os.name == 'nt':
        for raw in (r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                    r'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'):
            if Path(raw).is_file():
                return raw
    return None


def find_abaqus_launchers():
    """Discover command launchers from env vars, PATH and common install roots.

    Returns [{path, source, exists}], de-duplicated case-insensitively. Nothing
    is executed: a launcher is only reported if it exists on disk.
    """
    found = {}

    def add(raw, source):
        if not raw:
            return
        try:
            path = Path(str(raw))
            if not path.is_absolute():
                resolved = shutil.which(str(path))
                if not resolved:
                    return
                path = Path(resolved)
            path = path.resolve()
        except (OSError, RuntimeError, ValueError):
            return
        if path.is_file():
            found.setdefault(str(path).lower(), dict(path=str(path), source=source, exists=True))

    for key in ('ABAQUS_BAT', 'ABAQUS_COMMAND', 'ABAQUS_HOME', 'SIMULIA_HOME'):
        raw = os.environ.get(key)
        if not raw:
            continue
        base = Path(raw)
        for name in LAUNCHER_NAMES:
            add(base / 'Commands' / name, 'env:' + key)
            add(base / name, 'env:' + key)
    for name in LAUNCHER_NAMES:
        add(shutil.which(name), 'PATH')

    if os.name == 'nt':
        patterns = []
        for drive in ('C:', 'D:', 'E:'):
            for name in LAUNCHER_NAMES:
                patterns.append(drive + '/SIMULIA/Commands/' + name)
                patterns.append(drive + '/Program Files/Dassault Systemes/SimulationServices/V6R*/win_b64/Commands/' + name)
        for pattern in patterns:
            for raw in glob.glob(pattern):
                add(raw, 'common-install')
    return sorted(found.values(), key=lambda row: (not row['source'].startswith('env:'), row['path'].lower()))


def find_compilers():
    """Discover linker/Fortran compilers from PATH and common VS installs."""
    found = {}

    def add(raw, name, source):
        if not raw:
            return
        try:
            path = Path(str(raw)).resolve()
        except (OSError, RuntimeError, ValueError):
            return
        if path.is_file():
            found.setdefault(str(path).lower(), dict(path=str(path), name=name, source=source, exists=True))

    for name in COMPILER_NAMES:
        add(shutil.which(name), name, 'PATH')
    if os.name == 'nt':
        for root in (r'C:\Program Files (x86)\Microsoft Visual Studio',
                     r'C:\Program Files\Microsoft Visual Studio'):
            for pattern in (root + r'\*\BuildTools\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe',
                            root + r'\*\Community\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe',
                            root + r'\*\Professional\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe',
                            root + r'\*\Enterprise\VC\Tools\MSVC\*\bin\Hostx64\x64\link.exe'):
                for raw in glob.glob(pattern):
                    add(raw, 'link', 'common-install')
    return sorted(found.values(), key=lambda row: (row['source'] != 'PATH', row['path'].lower()))


def memory_bytes():
    """Total physical memory, via OS API without PowerShell; None if unknown."""
    if os.name != 'nt':
        try:
            return int(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'))
        except (AttributeError, ValueError, OSError):
            return None
    try:
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD),
                        ('ullTotalPhys', wintypes.ULARGE_INTEGER),
                        ('ullAvailPhys', wintypes.ULARGE_INTEGER),
                        ('ullTotalPageFile', wintypes.ULARGE_INTEGER),
                        ('ullAvailPageFile', wintypes.ULARGE_INTEGER),
                        ('ullTotalVirtual', wintypes.ULARGE_INTEGER),
                        ('ullAvailVirtual', wintypes.ULARGE_INTEGER),
                        ('ullAvailExtendedVirtual', wintypes.ULARGE_INTEGER)]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        if kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    except Exception:
        return None
    return None


def system_drive():
    """Absolute root of the Windows system drive, e.g. 'c:\\'; None off Windows.

    Abaqus scratch must not live here: large scratch files can fill the system
    partition, and concurrent scratch IO competes with the OS and can trigger
    MPI timeouts in parallel Standard/Explicit jobs.
    """
    if os.name != 'nt':
        return None
    raw = os.environ.get('SystemDrive')
    if raw and len(raw) >= 2:
        return os.path.normcase(os.path.abspath(raw[:2] + os.sep))
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        ctypes.windll.kernel32.GetSystemWindowsDirectoryW(buffer, 260)
        if buffer.value:
            drive = os.path.splitdrive(buffer.value)[0] or 'C:'
            return os.path.normcase(os.path.abspath(drive + os.sep))
    except Exception:
        pass
    return None


def on_system_drive(path):
    """True when `path` is on the Windows system drive. False off Windows or
    when the system drive cannot be determined (never blocks by guesswork)."""
    system = system_drive()
    if not system:
        return False
    candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
    return candidate == system or candidate.startswith(system)


def data_drives():
    """Fixed, non-system Windows drives sorted by free space (largest first).

    Only DRIVE_FIXED is accepted: network/mapped/removable drives are excluded
    because scratch needs low-latency random IO. Returns [] off Windows.
    """
    if os.name != 'nt':
        return []
    import ctypes
    rows = []
    system = system_drive() or ''
    for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
        root = letter + ':' + os.sep
        if not os.path.isdir(root):
            continue
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        except Exception:
            continue
        if drive_type != 3:  # DRIVE_FIXED
            continue
        if os.path.normcase(root) == system:
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        rows.append(dict(path=root, free_bytes=usage.free, total_bytes=usage.total))
    rows.sort(key=lambda row: (-row['free_bytes'], row['path']))
    return rows


def normalize_drive(token):
    """Normalize 'D', 'D:', 'd:\\' or 'D:/foo' to a comparable 'd:\\' root."""
    text = os.fspath(token).strip()
    drive = os.path.splitdrive(text)[0]
    if not drive and len(text) >= 1 and text[0].isalpha():
        drive = text[0] + ':'
    if not drive:
        return ''
    return os.path.normcase(drive + os.sep)


def suggest_scratch_root(base_dir, folder='CJC_ABAQUS_SCRATCH', preferred=()):
    """Recommend a scratch root on a fixed non-system drive.

    If `preferred` gives drive letters (e.g. ['D:']), the first matching fixed
    non-system drive wins; otherwise the largest free fixed drive is used.
    This keeps a per-machine preference without hard-coding a drive letter into
    the portable skill.

    Returns (path, on_system). on_system=True means no suitable data drive was
    found and the fallback (base/scratch) is itself on the system drive; the
    caller must surface that as a warning/blocking condition.
    """
    drives = data_drives()
    for token in preferred or ():
        wanted = normalize_drive(token)
        if not wanted:
            continue
        for row in drives:
            if os.path.normcase(row['path']).startswith(wanted):
                return str(Path(row['path']) / folder), False
    if drives:
        return str(Path(drives[0]['path']) / folder), False
    fallback = str(Path(base_dir).resolve() / 'scratch')
    return fallback, on_system_drive(fallback)


def hardware_summary():
    """Always-structured hardware fallback, independent of PowerShell."""
    logical = os.cpu_count() or 1
    total = memory_bytes()
    return dict(physical_cores=logical, logical_processors=logical, ram_bytes=total,
        last_boot=None, source='os.cpu_count',
        memory_source='GlobalMemoryStatusEx' if total is not None else 'unavailable',
        note='physical_cores falls back to logical count without CIM/WMI; treat as an upper bound')


def parse_release(text):
    """Extract an Abaqus release from `abaqus information=release` output."""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    for line in lines:
        match = RELEASE_RE.search(line)
        if match:
            version = match.group(1) + ('.' + match.group(2) if match.group(2) else '')
            return dict(version=version, matched_line=line[:200], raw_lines=lines[-40:])
    return dict(version=None, matched_line=None, raw_lines=lines[-40:])


def default_limits():
    """Safe capacity defaults for an unconfigured machine (leave headroom)."""
    logical = os.cpu_count() or 2
    total = memory_bytes()
    return dict(
        max_total_cpus=max(1, logical - 1),
        max_concurrent=max(1, min(8, logical // 4)),
        max_total_memory_mb=int(total * 0.85 / 1048576) if total else 4096,
        source='auto-detected; leave at least one logical processor and 15% RAM free')


def suggest_config(base_dir, preferred_scratch_drives=()):
    """Generate a device-appropriate config skeleton. Never overwrites a file.

    `preferred_scratch_drives` is an ordered list of drive letters for THIS
    machine (e.g. ['D:']); it is saved into the config so the preference is
    explicit and auditable, not a hidden default of the portable skill.
    """
    base = Path(base_dir).resolve()
    launchers = find_abaqus_launchers()
    preferred = list(preferred_scratch_drives or ())
    scratch, scratch_on_system = suggest_scratch_root(base, preferred=preferred)
    drives = data_drives()
    limits = default_limits()
    note = ('launcher is empty when no Abaqus command was found: set it manually; '
            'scratch directory must be created before planning a job; '
            'review allowed_roots before use.')
    if scratch_on_system:
        note += (' WARNING: no fixed non-system drive was found, so scratch falls back to the SYSTEM DRIVE. '
                 'This is unsafe for real solves (system partition fill-up + scratch/OS IO contention); '
                 'add a data drive or set scratch_roots to a non-system path before submitting.')
    else:
        note += (' scratch auto-selected on a fixed non-system drive: keep it there; '
                 'never move job work/scratch onto the system drive.')
    return dict(
        abaqus_launcher=launchers[0]['path'] if launchers else '',
        allowed_roots=[str(base), str(Path(scratch).parent)],
        registry_dir=str(base / 'agent_integrations' / 'abaqus_runtime'),
        scratch_roots=[scratch],
        preferred_scratch_drives=[normalize_drive(row).rstrip(os.sep) for row in preferred if normalize_drive(row)],
        candidate_data_drives=[row['path'] for row in drives],
        system_drive=system_drive(),
        scratch_on_system_drive=scratch_on_system,
        allow_scratch_on_system_drive=False,
        min_free_disk_bytes=8 * 1024 ** 3,
        probe_timeout_seconds=90,
        compiler_candidates=[row['path'] for row in find_compilers()],
        **limits,
        note=note.strip())


def same_path(a, b):
    """Windows-safe path equality (drive letter and separator case-insensitive)."""
    return os.path.normcase(os.path.abspath(os.fspath(a))) == os.path.normcase(os.path.abspath(os.fspath(b)))


def path_is_within(path, root):
    """True when `path` equals `root` or lies under it, case-insensitively."""
    candidate, anchor = os.path.normcase(os.path.abspath(os.fspath(path))), os.path.normcase(os.path.abspath(os.fspath(root)))
    return candidate == anchor or candidate.startswith(anchor.rstrip(os.sep) + os.sep)
