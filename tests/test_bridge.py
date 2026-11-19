"""Behavioral tests: never start Abaqus analyses; mocked submit uses only temp files."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import abaqus_agent as bridge
from history_peak import evaluate
import mcp_server
import job_worker


class Peaks(unittest.TestCase):
    def curve(self, values, displacements=None, times=None):
        times = times or list(range(len(values)))
        displacements = displacements or list(range(len(values)))
        return evaluate(list(zip(times, values)), list(zip(times, displacements)))

    def test_endpoint_never_peak(self):
        result = self.curve([0, 1, 2, 3, 4])
        self.assertEqual(result['peak_status'], 'NO_CONFIRMED_PEAK')
        self.assertIsNone(result['RF_peak'])
        self.assertEqual(result['candidate_RF'], 4)

    def test_strict_five_percent(self):
        result = self.curve([0, 80, 100, 99, 97, 94])
        self.assertEqual(result['peak_status'], 'PEAK_VALID')
        self.assertTrue(result['strict_confirmed'])

    def test_screen_two_not_strict(self):
        result = self.curve([0, 80, 100, 99, 98.5, 97])
        self.assertEqual(result['peak_status'], 'SCREEN_PEAK_VALID')
        self.assertFalse(result['strict_confirmed'])

    def test_stable_thirty(self):
        result = self.curve([0, 80, 100] + [100 - .02 * i for i in range(1, 36)])
        self.assertEqual(result['peak_status'], 'PEAK_STABLE_PROVISIONAL')
        self.assertEqual(result['RF_peak'], 100)

    def test_stable_needs_thirty(self):
        result = self.curve([0, 80, 100] + [99.99 - .02 * i for i in range(29)])
        self.assertEqual(result['peak_status'], 'NO_CONFIRMED_PEAK')

    def test_stable_needs_half_percent(self):
        result = self.curve([0, 80, 100] + [100 - .001 * i for i in range(1, 36)])
        self.assertEqual(result['peak_status'], 'NO_CONFIRMED_PEAK')

    def test_postpeak_response_not_peak_lower_bound(self):
        result = self.curve([0, 80, 100, 90, 70, 60])
        self.assertEqual(result['RF_peak'], 100)
        self.assertNotIn('peak_lower_bound', result)

    def test_higher_new_endpoint_invalidates_old_peak(self):
        result = self.curve([0, 80, 100, 90, 80, 101])
        self.assertIsNone(result['RF_peak'])
        self.assertEqual(result['candidate_RF'], 101)

    def test_no_displacement_progress(self):
        result = self.curve([0, 80, 100, 99, 97, 90], [0, 1, 2, 2, 2, 2])
        self.assertEqual(result['peak_status'], 'NO_CONFIRMED_PEAK')

    def test_duplicate_points_invalid(self):
        result = self.curve([0, 80, 100, 99, 97, 90], times=[0, 1, 2, 3, 3, 4])
        self.assertEqual(result['peak_status'], 'INVALID_HISTORY')

    def test_unpaired_points_invalid(self):
        result = evaluate([(0, 0), (1, 100), (2, 90)], [(0, 0), (1, 1), (3, 3)])
        self.assertEqual(result['peak_status'], 'INVALID_HISTORY')

    def test_nonfinite_rejected(self):
        result = self.curve([0, 80, 100, 99, 97, float('nan'), 90])
        self.assertEqual(result['peak_status'], 'INVALID_HISTORY')
        self.assertFalse(result['usable_peak'])

    def test_unordered_time_rejected(self):
        result = self.curve([0, 80, 100, 99, 97, 90], times=[0, 1, 2, 4, 3, 5])
        self.assertEqual(result['peak_status'], 'INVALID_HISTORY')

    def test_bad_rule_order_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([(0, 0)], [(0, 0)], {'screen_drop': .1, 'confirmed_drop': .05})


class Plans(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='abaqus_bridge_test_')
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'; self.work.mkdir()
        self.scratch_root = self.root / 'scratch'; self.scratch_root.mkdir()
        self.launcher = self.root / 'abaqus.bat'; self.launcher.write_text('@echo off\n')
        self.inp = self.work / 'MODEL.inp'
        self.inp.write_text('*HEADING\nTEST FIXTURE ONLY\n*INCLUDE, INPUT=material.inc\n*STEP\n*STATIC\n.01,1,1e-6,.1\n*END STEP\n')
        (self.work / 'material.inc').write_text('*MATERIAL, NAME=TEST\n*ELASTIC\n1000,.2\n')
        self.config = self.root / 'config.json'
        bridge.atomic_json(self.config, dict(abaqus_launcher=str(self.launcher), allowed_roots=[str(self.root)],
            registry_dir=str(self.root / 'registry'), scratch_roots=[str(self.scratch_root)], max_total_cpus=8,
            max_concurrent=4, max_total_memory_mb=8192, min_free_disk_bytes=0, probe_timeout_seconds=30,
            allow_scratch_on_system_drive=True))  # tests use a temp dir on C:; real jobs must opt in explicitly
        self.backend = bridge.Backend(self.config)
        self.request = dict(job='TEST_X', input=str(self.inp), workdir=str(self.work),
            scratch=str(self.scratch_root / 'TEST_X'), solver='standard', cpus=2, memory_mb=1024)
        self.process_patch = patch('abaqus_agent.process_snapshot', return_value=[])
        self.process_patch.start()

    def tearDown(self):
        self.process_patch.stop()
        self.temp.cleanup()

    def test_plan_reads_only(self):
        before = set(self.root.rglob('*'))
        plan = self.backend.plan(self.request)
        self.assertEqual(before, set(self.root.rglob('*')))
        self.assertEqual(len(plan['sealed']['dependencies']), 2)
        self.assertEqual(len(plan['plan_token']), 64)

    def test_material_mutation_changes_token(self):
        a = self.backend.plan(self.request)['plan_token']
        (self.work / 'material.inc').write_text('*MATERIAL,NAME=OTHER\n')
        b = self.backend.plan(self.request)['plan_token']
        self.assertNotEqual(a, b)

    def test_odb_overwrite_rejected(self):
        (self.work / 'TEST_X.odb').write_bytes(b'legacy result')
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)

    def test_stale_lock_not_deleted(self):
        path = self.work / 'TEST_X.lck'; path.write_text('legacy lock')
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)
        self.assertTrue(path.exists())

    def test_scratch_nonempty_rejected(self):
        path = Path(self.request['scratch']); path.mkdir(); (path / 'unknown').write_text('keep')
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)
        self.assertEqual((path / 'unknown').read_text(), 'keep')

    def test_outside_roots_rejected(self):
        with self.assertRaises(bridge.AgentError): self.backend.allowed(self.root.parent / 'outside.inp')

    def test_relative_path_rejected(self):
        with self.assertRaises(bridge.AgentError): self.backend.allowed('relative.inp')

    def test_bad_job_shell_injection(self):
        for name in ['JOB & whoami', '../JOB', 'Z*', '0JOB', 'JOB%PATH%']:
            with self.subTest(name=name), self.assertRaises(bridge.AgentError):
                self.backend.plan(dict(self.request, job=name))

    def test_command_metacharacters_rejected(self):
        for value in ['path&bad', 'path|bad', 'path%PATH%', 'path\nwrong', 'a"b']:
            with self.subTest(value=value), self.assertRaises(bridge.AgentError): bridge.safe_argument(value)

    def test_all_windows_arguments_quoted(self):
        if os.name != 'nt': self.skipTest('Windows command form')
        command = bridge.windows_command(['C:/Program Files/Tool (x86)/abaqus.bat', 'job=TEST_X'])
        self.assertIn('"C:/Program Files/Tool (x86)/abaqus.bat" "job=TEST_X"', command)

    def test_cyclic_include_rejected(self):
        (self.work / 'material.inc').write_text('*INCLUDE, INPUT=MODEL.inp\n')
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)

    def test_include_escape_rejected(self):
        self.inp.write_text('*INCLUDE,INPUT=' + str(self.root.parent / 'outside.inc'))
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)

    def test_missing_include_rejected(self):
        self.inp.write_text('*INCLUDE,INPUT=missing.inc')
        with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)

    def test_explicit_solver_mismatch_rejected(self):
        with self.assertRaises(bridge.AgentError): self.backend.plan(dict(self.request, solver='explicit'))

    def test_explicit_command_precision_domains(self):
        self.inp.write_text('*STEP\n*DYNAMIC, EXPLICIT\n, .02\n*END STEP\n')
        plan = self.backend.plan(dict(self.request, solver='explicit', cpus=4))
        self.assertIn('double=both', plan['command_args'])
        self.assertIn('domains=4', plan['command_args'])

    def test_datacheck_supported_without_executing(self):
        plan = self.backend.plan(dict(self.request, operation='datacheck'))
        self.assertIn('datacheck', plan['command_args'])

    def test_bad_cpus_rejected(self):
        for count in [True, 2.5, '2', 0, 9]:
            with self.subTest(count=count), self.assertRaises(bridge.AgentError):
                self.backend.plan(dict(self.request, cpus=count))

    def test_unknown_live_solver_blocks(self):
        with patch('abaqus_agent.process_snapshot', return_value=[{'Name':'standard.exe','ProcessId':123,'CommandLine':'unknown original job'}]):
            with self.assertRaises(bridge.AgentError): self.backend.plan(self.request)

    def test_no_submit_without_authorization(self):
        plan = self.backend.plan(self.request)
        with patch('abaqus_agent.subprocess.Popen') as process:
            with self.assertRaises(bridge.AgentError): self.backend.submit(self.request, plan['plan_token'])
            process.assert_not_called()

    def test_changed_plan_never_launches(self):
        plan = self.backend.plan(self.request)
        self.inp.write_text(self.inp.read_text() + '**changed\n')
        with patch('abaqus_agent.subprocess.Popen') as process:
            with self.assertRaises(bridge.AgentError): self.backend.submit(self.request, plan['plan_token'], True, 'test mocked submit only')
            process.assert_not_called()

    def test_mocked_submit_writes_only_own_registry(self):
        if os.name != 'nt': self.skipTest('Windows submit')
        plan = self.backend.plan(self.request)
        with patch('abaqus_agent.subprocess.Popen') as process:
            result = self.backend.submit(self.request, plan['plan_token'], True, 'TEST MOCK ONLY NO ANALYSIS')
            process.assert_called_once()
        record = bridge.read_json(result['record'])
        self.assertEqual(record['state'], 'RESERVED')
        self.assertFalse((self.work / 'TEST_X.odb').exists())

    def test_restart_inventory_not_verification(self):
        for ext in ('.res','.mdl','.stt','.prt','.odb'): (self.work / ('OLD' + ext)).write_bytes(b'fixture')
        audit = self.backend.inspect_restart(str(self.work), 'OLD')
        self.assertTrue(audit['restart_files_present'])
        self.assertFalse(audit['restart_state_verified'])
        self.assertIsNone(audit['restart_increment'])

    def test_missing_restart_state_not_submitted(self):
        self.inp.write_text('*RESTART, READ\n')
        with self.assertRaises(bridge.AgentError): self.backend.plan(dict(self.request, oldjob=str(self.work / 'OLD')))

    def test_pid_reuse_not_running(self):
        self.backend.registry.mkdir()
        job_id = 'a' * 32
        bridge.atomic_json(self.backend.registry / ('job-' + job_id + '.json'),
            dict(id=job_id, request=self.request, state='RUNNING', finished=False,
                 worker_pid=100, worker_identity=1, launcher_pid=101, launcher_identity=2,
                 submitted_epoch=0))
        with patch('abaqus_agent.process_identity', return_value=999):
            status = self.backend.status(job_id)
        self.assertEqual(status['observed_state'], 'STALE_RECORD_NEEDS_RECONCILIATION')

    def test_unknown_job_cannot_be_terminated(self):
        with self.assertRaises(bridge.AgentError): self.backend.terminate('b' * 32, True, 'scope test')

    def test_probe_errors_are_not_success(self):
        odb = self.work / 'ORIGINAL.odb'; odb.write_bytes(b'not opened: mock')
        def fake_run(command, **kwargs):
            destination = sorted(self.backend.registry.glob('*-request.json'))[-1]
            output = destination.with_name(destination.name.replace('-request.json', '-result.json'))
            bridge.atomic_json(output, {'error':'unicode TypeError','peak_status':'ODB_PROBE_ERROR'})
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with patch('abaqus_agent.subprocess.run', side_effect=fake_run):
            with self.assertRaises(bridge.AgentError): self.backend.probe_odb({'odb': str(odb), 'mode':'inventory'})
        self.assertEqual(odb.read_bytes(), b'not opened: mock')

    def test_provisional_not_automatically_usable(self):
        odb = self.work / 'ORIGINAL.odb'; odb.write_bytes(b'mock')
        def fake_run(command, **kwargs):
            source = sorted(self.backend.registry.glob('*-request.json'))[-1]
            bridge.atomic_json(source.with_name(source.name.replace('-request.json','-result.json')),
                {'peak_status':'PEAK_STABLE_PROVISIONAL','usable_peak':True,'RF_peak':100})
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with patch('abaqus_agent.subprocess.run', side_effect=fake_run):
            result = self.backend.probe_odb({'odb':str(odb),'mode':'peak'})
        self.assertFalse(result['usable_peak'])

    def test_tools_reject_unknown_extra_arguments(self):
        with self.assertRaises(ValueError): mcp_server.validate_arguments('abaqus_doctor', {'shell':'whoami'})


class Workers(unittest.TestCase):
    def setUp(self):
        Plans.setUp(self)

    def tearDown(self):
        Plans.tearDown(self)

    def prepare(self, updates=None):
        self.request.update(updates or {})
        plan = self.backend.plan(self.request)
        path = self.backend.registry / ('job-' + 'c' * 32 + '.json')
        bridge.atomic_json(path, dict(id='c'*32, request=plan['sealed']['request'], sealed=plan['sealed'],
            state='RESERVED', finished=False, config_path=str(self.config), command_args=plan['command_args'],
            submitted_epoch=0))
        return path

    def fake_launcher_process(self):
        process = MagicMock(pid=os.getpid(), returncode=0)
        process.poll.side_effect = [None, 0]
        return process

    def test_current_windows_process_identity(self):
        self.assertIsNotNone(bridge.process_identity(os.getpid()))
        self.assertEqual(bridge.process_identity(os.getpid()), bridge.process_identity(os.getpid()))

    def test_mocked_worker_finishes_with_raw_marker(self):
        path = self.prepare()
        (self.work/'TEST_X.log').write_text('ANALYSIS COMPLETED\n')
        with patch('job_worker.subprocess.Popen', return_value=self.fake_launcher_process()), patch('job_worker.time.sleep'):
            row = job_worker.supervise(path)
        self.assertEqual(row['state'], 'COMPLETED')
        self.assertTrue(row['finished'])
        self.assertFalse((self.work/'TEST_X.odb').exists())

    def test_datacheck_error_not_masked_by_completed_launcher(self):
        path = self.prepare({'operation':'datacheck'})
        (self.work/'TEST_X.log').write_text('COMPLETED SUCCESSFULLY\n')
        (self.work/'TEST_X.dat').write_text('***ERROR: TEST INPUT INVALID\n')
        with patch('job_worker.subprocess.Popen', return_value=self.fake_launcher_process()), patch('job_worker.time.sleep'):
            row = job_worker.supervise(path)
        self.assertEqual(row['state'], 'INPUT_CHECK_FAILED')

    def test_input_changed_after_submit_blocks_worker(self):
        path = self.prepare()
        self.inp.write_text('*HEADING\nMUTATION\n')
        with patch('job_worker.subprocess.Popen') as process:
            with self.assertRaises(bridge.AgentError): job_worker.supervise(path)
            process.assert_not_called()

    def test_walltime_with_authority_requests_exact_job_only(self):
        path = self.prepare({'terminate_at_walltime':True})
        stopped = subprocess.CompletedProcess([], 0, b'job stopped mock', b'')
        with patch('job_worker.subprocess.Popen', return_value=self.fake_launcher_process()), patch('job_worker.time.sleep'), \
             patch('job_worker.time.time', side_effect=[0,6000,6001]), patch('job_worker.subprocess.run', return_value=stopped) as call:
            row = job_worker.supervise(path)
        self.assertEqual(row['stop_request']['reason'], 'AUTHORIZED_WALLTIME_LIMIT')
        self.assertIn('job=TEST_X', str(call.call_args))
        self.assertNotIn('taskkill', str(call.call_args))

    def test_walltime_without_authority_never_terminates(self):
        path = self.prepare({'terminate_at_walltime':False})
        with patch('job_worker.subprocess.Popen', return_value=self.fake_launcher_process()), patch('job_worker.time.sleep'), \
             patch('job_worker.time.time', side_effect=[0,6000,6001]), patch('job_worker.subprocess.run') as call:
            row = job_worker.supervise(path)
        call.assert_not_called()
        self.assertEqual(row['attention'], 'WALLTIME_LIMIT_REACHED_NO_TERMINATION_AUTHORITY')


class Triage(unittest.TestCase):
    def setUp(self):
        Plans.setUp(self)

    def tearDown(self):
        Plans.tearDown(self)

    def evidence(self, **updates):
        base = dict(exception_kinds=[], dat_error_lines=[], numerical_markers={},
                    abort_marker=True, completion_marker=False)
        base.update(updates)
        return base

    def test_part_map_exception_is_high_confidence_host_defect(self):
        result = bridge.triage_failure(
            self.evidence(exception_kinds=['PART_MAP_HANDOFF']),
            {'suspect_dlls': ['tsbx.dll']})
        self.assertEqual(result['root_cause'], 'HOST_SANDBOX_DEFECT')
        self.assertEqual(result['confidence'], 'HIGH')
        self.assertIn('without agent injection', result['recommended_action'])

    def test_dat_error_wins_over_generic_abort(self):
        result = bridge.triage_failure(self.evidence(dat_error_lines=['***ERROR: BAD MATERIAL']), {})
        self.assertEqual(result['root_cause'], 'MODEL_INPUT_ERROR')
        self.assertEqual(result['confidence'], 'HIGH')

    def test_external_interrupt_is_not_blamed_on_model(self):
        result = bridge.triage_failure(self.evidence(exception_kinds=['EXTERNAL_INTERRUPT']), {})
        self.assertEqual(result['root_cause'], 'EXTERNAL_INTERRUPT')

    def test_numerical_marker_classification(self):
        result = bridge.triage_failure(
            self.evidence(numerical_markers={'TOO MANY INCREMENTS': True}), {})
        self.assertEqual(result['root_cause'], 'NUMERICAL_CONVERGENCE')

    def test_completion_marker_never_becomes_failure(self):
        result = bridge.triage_failure(
            self.evidence(abort_marker=False, completion_marker=True), {})
        self.assertEqual(result['root_cause'], 'NO_FAILURE_EVIDENCE')

    def test_injection_suspicion_stays_low_confidence(self):
        result = bridge.triage_failure(self.evidence(), {'suspect_dlls': ['tsbx.dll']})
        self.assertEqual(result['root_cause'], 'SUSPECTED_HOST_SANDBOX')
        self.assertEqual(result['confidence'], 'LOW')

    def test_solve_readiness_blocks_injected_host(self):
        ready = bridge.solve_readiness(True, {'suspects': ['tsbx.dll']}, 'Windows')
        self.assertEqual(ready['verdict'], 'BLOCKED_BY_AGENT_INJECTION')
        self.assertFalse(ready['suitable'])

    def test_solve_readiness_ready_but_license_unverified(self):
        ready = bridge.solve_readiness(True, {'suspects': []}, 'Windows')
        self.assertEqual(ready['verdict'], 'READY_LICENSE_UNVERIFIED')
        self.assertTrue(ready['suitable'])
        self.assertIn('license', ready['recommendation'].lower())

    def test_backend_triage_reads_real_exception_file(self):
        (self.work/'TEST_X.00.1.exception').write_text(
            '<Exception><Description>ABAQUS/Standard rank 0 exited with exception</Description>'
            '<Details>The part map file is corrupt, does not exist, or cannot be opened.</Details>'
            '<Phase>std</Phase></Exception>')
        (self.work/'TEST_X.log').write_text('ABAQUS/STANDARD ANALYSIS EXITED WITH AN ERROR\n')
        result = self.backend.triage(str(self.work), 'TEST_X')
        self.assertEqual(result['job'], 'TEST_X')
        self.assertEqual(result['root_cause']['root_cause'], 'HOST_SANDBOX_DEFECT')
        self.assertEqual(result['root_cause']['confidence'], 'HIGH')
        self.assertIn('host_readiness', result)

    def test_status_carries_triage_without_extra_call(self):
        plan = self.backend.plan(self.request)
        self.backend.registry.mkdir(parents=True, exist_ok=True)
        record = self.backend.registry / ('job-' + 'a' * 32 + '.json')
        bridge.atomic_json(record, dict(id='a' * 32, request=plan['sealed']['request'],
            sealed=plan['sealed'], state='RESERVED', finished=False,
            config_path=str(self.config), command_args=plan['command_args'], submitted_epoch=0))
        status = self.backend.status('a' * 32)
        self.assertIn('triage', status)
        self.assertIn('root_cause', status['triage'])


class Compat(unittest.TestCase):
    def setUp(self):
        Plans.setUp(self)

    def tearDown(self):
        Plans.tearDown(self)

    def test_release_parsing(self):
        parsed = bridge.host_compat.parse_release('Abaqus License Manager\nAbaqus 2024\nBuild 2024.HF3')
        self.assertEqual(parsed['version'], '2024')

    def test_release_failure_is_structured(self):
        parsed = bridge.host_compat.parse_release('nothing useful here')
        self.assertIsNone(parsed['version'])
        self.assertIn('raw_lines', parsed)

    def test_windows_path_equality_ignores_case(self):
        if os.name != 'nt':
            self.skipTest('Windows path semantics')
        self.assertTrue(bridge.host_compat.same_path(self.work, str(self.work).upper()))
        self.assertTrue(bridge.host_compat.path_is_within(self.work, str(self.root).upper()))
        self.assertFalse(bridge.host_compat.path_is_within(str(self.root) + '_other', str(self.root)))

    def test_limits_accept_auto_and_reject_garbage(self):
        raw = json.loads(self.config.read_text(encoding='utf-8'))
        raw['max_total_cpus'] = 'auto'
        bridge.atomic_json(self.config, raw)
        self.assertGreaterEqual(bridge.Backend(self.config).limits()['max_total_cpus'], 1)
        raw['max_concurrent'] = 'garbage'
        bridge.atomic_json(self.config, raw)
        with self.assertRaises(bridge.AgentError):
            bridge.Backend(self.config)

    def test_init_config_creates_then_refuses_overwrite(self):
        target = self.root / 'generated' / 'config.json'
        result = self.backend.init_config(str(target))
        self.assertTrue(result['created'])
        self.assertTrue(target.is_file())
        with self.assertRaises(bridge.AgentError):
            self.backend.init_config(str(target))

    def test_suggest_config_shape(self):
        config = bridge.host_compat.suggest_config(self.root)
        self.assertIn(str(self.root.resolve()), config['allowed_roots'])
        self.assertIn('max_total_cpus', config)
        self.assertIn('scratch_roots', config)
        self.assertIn('system_drive', config)
        self.assertIn('candidate_data_drives', config)
        self.assertFalse(config['allow_scratch_on_system_drive'])
        # auto-selected scratch must never be on the system drive when a data drive exists
        self.assertFalse(config['scratch_on_system_drive'] or config['scratch_roots'][0].startswith(
            (config['system_drive'] or '\x00').lower()), 'auto scratch landed on the system drive')

    def test_system_drive_detection(self):
        system = bridge.host_compat.system_drive()
        self.assertTrue(system)
        self.assertTrue(bridge.host_compat.on_system_drive(system))
        self.assertTrue(bridge.host_compat.on_system_drive(str(Path(system) / 'Users' / 'someone' / 'job')))
        self.assertFalse(bridge.host_compat.on_system_drive('D:\\some_data_drive\\scratch'))

    def test_suggest_scratch_root_prefers_data_drive(self):
        path, on_system = bridge.host_compat.suggest_scratch_root(self.root)
        self.assertFalse(on_system)
        self.assertTrue(path)
        self.assertNotEqual(Path(path).parent, self.root.resolve())

    def test_preferred_drive_overrides_largest_free_drive(self):
        drives = bridge.host_compat.data_drives()
        if len(drives) < 2:
            self.skipTest('need at least two fixed data drives')
        largest = drives[0]['path']
        other = drives[1]['path']
        self.assertNotEqual(largest, other)
        path, on_system = bridge.host_compat.suggest_scratch_root(
            self.root, preferred=[other])
        self.assertFalse(on_system)
        self.assertTrue(path.lower().startswith(other.lower()))

    def test_suggest_config_records_preferred_drives(self):
        drives = bridge.host_compat.data_drives()
        if not drives:
            self.skipTest('need a fixed data drive')
        wanted = drives[0]['path'][:2]
        config = bridge.host_compat.suggest_config(self.root, [wanted])
        self.assertEqual(config['preferred_scratch_drives'], [wanted.lower()])
        self.assertTrue(config['scratch_roots'][0].lower().startswith(wanted.lower()))

    def test_init_config_accepts_prefer_drive(self):
        drives = bridge.host_compat.data_drives()
        if not drives:
            self.skipTest('need a fixed data drive')
        target = self.root / 'preferred_config.json'
        result = self.backend.init_config(str(target), drives[0]['path'][:2])
        self.assertTrue(result['suggestion']['scratch_roots'][0].lower().startswith(
            drives[0]['path'][:2].lower()))

    def test_hardware_summary_is_structured(self):
        hardware = bridge.host_compat.hardware_summary()
        self.assertGreaterEqual(hardware['logical_processors'], 1)
        self.assertIn('memory_source', hardware)

    def test_doctor_exposes_compat_discovery(self):
        report = self.backend.doctor()
        self.assertIn('compat', report)
        self.assertIn('launcher_candidates', report['compat'])
        self.assertIn('hardware_degraded', report)

    def test_mcp_host_compat_tool(self):
        result = mcp_server.call_tool(self.backend, 'abaqus_host_compat', {})
        self.assertIn('launcher_candidates', result)
        self.assertIn('default_limits', result)


class ConfigPreflight(unittest.TestCase):
    def setUp(self):
        Plans.setUp(self)
        self.no_inject = patch('abaqus_agent.injected_modules',
            return_value={'supported': True, 'modules': [], 'suspects': []})
        self.no_inject.start()

    def tearDown(self):
        self.no_inject.stop()
        Plans.tearDown(self)

    def report(self, **kwargs):
        return self.backend.validate_config(**kwargs)

    def test_healthy_config_is_ready(self):
        result = self.report()
        self.assertEqual(result['verdict'], 'READY')
        self.assertTrue(result['usable'])
        self.assertEqual(result['counts']['fail'], 0)

    def test_missing_launcher_is_blocking(self):
        self.launcher.unlink()
        result = self.report()
        self.assertEqual(result['verdict'], 'BLOCKED')
        check = next(row for row in result['checks'] if row['check'] == 'launcher')
        self.assertEqual(check['status'], 'FAIL')

    def test_missing_scratch_is_blocking(self):
        raw = json.loads(self.config.read_text(encoding='utf-8'))
        raw['scratch_roots'] = [str(self.root / 'never_created_scratch')]
        bridge.atomic_json(self.config, raw)
        result = bridge.Backend(self.config).validate_config()
        self.assertEqual(result['verdict'], 'BLOCKED')
        check = next(row for row in result['checks'] if row['check'] == 'scratch_roots')
        self.assertEqual(check['status'], 'FAIL')

    def test_host_injection_blocks_preflight(self):
        self.no_inject.stop()
        self.no_inject = patch('abaqus_agent.injected_modules',
            return_value={'supported': True, 'modules': ['tsbx.dll'], 'suspects': ['tsbx.dll']})
        self.no_inject.start()
        result = self.report()
        self.assertEqual(result['verdict'], 'BLOCKED')
        self.assertFalse(result['usable'])

    def test_default_preflight_starts_no_process(self):
        with patch('abaqus_agent.subprocess.run') as run:
            self.report()
        run.assert_not_called()

    def test_preflight_creates_no_files(self):
        before = {str(path) for path in self.root.rglob('*')}
        self.report()
        after = {str(path) for path in self.root.rglob('*')}
        self.assertEqual(before, after)

    def test_plan_rejects_system_drive_scratch_without_override(self):
        raw = json.loads(self.config.read_text(encoding='utf-8'))
        raw.pop('allow_scratch_on_system_drive', None)
        bridge.atomic_json(self.config, raw)
        backend = bridge.Backend(self.config)
        with self.assertRaises(bridge.AgentError) as ctx:
            backend.plan(self.request)
        self.assertIn('system drive', str(ctx.exception))

    def test_plan_accepts_system_drive_scratch_with_explicit_override(self):
        plan = self.backend.plan(self.request)
        self.assertTrue(plan['sealed']['request']['scratch'])

    def test_validate_warns_when_scratch_off_preferred_drive(self):
        drives = bridge.host_compat.data_drives()
        if len(drives) < 2:
            self.skipTest('need at least two fixed data drives')
        current = self.scratch_root.resolve().drive
        other = next((row['path'][:2] for row in drives
                      if row['path'][:2].lower() != current.lower()), None)
        if not other:
            self.skipTest('no alternative drive')
        raw = json.loads(self.config.read_text(encoding='utf-8'))
        raw['preferred_scratch_drives'] = [other]
        raw.pop('allow_scratch_on_system_drive', None)
        bridge.atomic_json(self.config, raw)
        result = bridge.Backend(self.config).validate_config()
        policy = next(row for row in result['checks'] if row['check'] == 'scratch_disk_policy')
        self.assertEqual(policy['status'], 'WARN')
        self.assertFalse(policy['detail']['scratch_on_preferred_drive'])

    def test_validate_flags_system_drive_without_override(self):
        raw = json.loads(self.config.read_text(encoding='utf-8'))
        raw.pop('allow_scratch_on_system_drive', None)
        bridge.atomic_json(self.config, raw)
        result = bridge.Backend(self.config).validate_config()
        check = next(row for row in result['checks'] if row['check'] == 'scratch_roots')
        self.assertEqual(check['status'], 'FAIL')
        detail_text = str(check['detail'])
        self.assertIn('SYSTEM DRIVE', detail_text)
        self.assertTrue(all(row.get('on_system_drive') for row in check['detail']))
        policy = next(row for row in result['checks'] if row['check'] == 'scratch_disk_policy')
        self.assertEqual(policy['status'], 'INFO')

    def test_release_query_is_optional_and_warns_on_bad_launcher(self):
        result = self.report(query_release=True)
        self.assertIsNotNone(result['release'])
        self.assertIn('abaqus_release', {row['check'] for row in result['checks']})

    def test_mcp_validate_tool(self):
        result = mcp_server.call_tool(self.backend, 'abaqus_validate_config', {})
        self.assertTrue(result['usable'])
        self.assertIn('checks', result)


class MCPProtocol(unittest.TestCase):
    def test_stdio_lifecycle_tools_and_guard(self):
        messages = [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'independent-test-client','version':'1'}}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'abaqus_submit_job','arguments':{'request':{},'plan_token':'bad','authorize':False,'authorization_note':''}}},
            {'jsonrpc':'2.0','id':4,'method':'ping'},
            {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'abaqus_doctor','arguments':{'shell':'not permitted'}}},
            {'jsonrpc':'2.0','id':6,'method':'resources/list'},
            {'jsonrpc':'2.0','id':7,'method':'resources/read','params':{'uri':'abaqus://handbook'}},
            {'jsonrpc':'2.0','id':8,'method':'resources/read','params':{'uri':'file:///C:/Windows/secret'}}
        ]
        process = subprocess.run([sys.executable, str(SCRIPTS / 'mcp_server.py')],
            input=''.join(json.dumps(m) + '\n' for m in messages), text=True, encoding='utf-8',
            capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        output = [json.loads(row) for row in process.stdout.splitlines()]
        self.assertEqual(len(output), 8)
        self.assertEqual(output[0]['result']['protocolVersion'], '2025-06-18')
        tool_names = {t['name'] for t in output[1]['result']['tools']}
        self.assertEqual(len(tool_names), 10)
        self.assertIn('abaqus_triage_job', tool_names)
        self.assertIn('abaqus_host_compat', tool_names)
        self.assertIn('abaqus_validate_config', tool_names)
        self.assertTrue(output[2]['result']['isError'])
        self.assertEqual(output[3]['result'], {})
        self.assertTrue(output[4]['result']['isError'])
        resources = output[5]['result']['resources']
        self.assertEqual(len(resources), 5)
        self.assertIn('abaqus://agent-host', {r['uri'] for r in resources})
        self.assertIn('abaqus://host-compat', {r['uri'] for r in resources})
        self.assertEqual(output[6]['result']['contents'][0]['mimeType'], 'text/markdown')
        self.assertGreater(len(output[6]['result']['contents'][0]['text']), 1000)
        self.assertIn('error', output[7])


if __name__ == '__main__':
    unittest.main(verbosity=2)
